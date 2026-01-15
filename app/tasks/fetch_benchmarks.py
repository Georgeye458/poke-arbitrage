"""Task 2: Fetch market benchmarks from eBay Merchandising API."""

import asyncio
import logging
from datetime import datetime

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import SearchQuery, MarketBenchmark
from app.api.ebay_merchandising import ebay_merchandising
from app.config import settings

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper to run async code in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3)
def fetch_all_benchmarks(self, listing_mode: str = "PSA10"):
    """
    Task 2: Fetch market value benchmarks for all search queries.
    
    CRITICAL FILTER LOGIC:
    - Calculates average price from Merchandising API response
    - IF average >= $3,000 AUD: DO NOT store (card is above target ceiling)
    - IF average < $3,000 AUD: Store as official market_price
    
    This effectively prunes our watchlist dynamically.
    """
    listing_mode = (listing_mode or "PSA10").upper()
    logger.info(f"Starting Task 2: Fetch Market Benchmarks (mode={listing_mode})")
    
    db = SessionLocal()
    try:
        # Get all active search queries
        queries = db.query(SearchQuery).filter(SearchQuery.is_active == True).all()
        
        if not queries:
            logger.warning("No active search queries found")
            return {"status": "no_queries", "processed": 0}
        
        stored_count = 0
        filtered_count = 0
        error_count = 0
        
        for query in queries:
            try:
                result = run_async(_fetch_query_benchmark(db, query, listing_mode=listing_mode))
                
                if result == "stored":
                    stored_count += 1
                elif result == "filtered":
                    filtered_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Error fetching benchmark for '{query.card_name}': {e}")
                error_count += 1
                continue
        
        logger.info(
            f"Task 2 complete: {stored_count} benchmarks stored, "
            f"{filtered_count} filtered (>$3k), {error_count} errors"
        )
        
        return {
            "status": "success",
            "stored": stored_count,
            "filtered": filtered_count,
            "errors": error_count,
        }
        
    except Exception as e:
        logger.error(f"Task 2 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()


async def _fetch_query_benchmark(db, query: SearchQuery, listing_mode: str) -> str:
    """Fetch benchmark for a single search query."""
    # Fetch from Merchandising API
    api_response = await ebay_merchandising.get_most_watched_items(
        query.query_text,
        language=query.language,
        mode=listing_mode,
    )
    
    # Calculate benchmark with price filter
    benchmark_data = ebay_merchandising.calculate_market_benchmark(
        api_response,
        price_ceiling=settings.price_ceiling_aud,
        price_floor=getattr(settings, "price_floor_aud", 0.0),
        language=query.language,
    )
    
    if benchmark_data is None:
        # Card was filtered out (no data, above ceiling, or below floor)
        logger.info(f"'{query.card_name}' filtered: no valid benchmark / out of scope")
        return "filtered"
    
    # Create new benchmark record
    benchmark = MarketBenchmark(
        search_query_id=query.id,
        market_price=benchmark_data["market_price"],
        data_source=benchmark_data["data_source"],
        sample_size=benchmark_data["sample_size"],
        min_price=benchmark_data["min_price"],
        max_price=benchmark_data["max_price"],
        calculated_at=datetime.utcnow(),
    )
    
    db.add(benchmark)
    db.commit()
    
    logger.info(
        f"'{query.card_name}' benchmark stored: ${benchmark_data['market_price']}"
    )
    return "stored"
