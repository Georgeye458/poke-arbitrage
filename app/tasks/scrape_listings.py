"""Task 1: Scrape active listings from eBay Browse API."""

import asyncio
import logging
from datetime import datetime

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import SearchQuery, PSA10Listing
from app.api.ebay_browse import ebay_browse

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
def scrape_all_listings(self):
    """
    Task 1: Scrape active Buy It Now listings for all search queries.
    
    For each active search query:
    - Calls Browse API to fetch PSA 10 listings
    - Parses and stores listings in psa10_listings table
    - Updates last_seen_at for existing listings
    """
    logger.info("Starting Task 1: Scrape Active Listings")
    
    db = SessionLocal()
    try:
        # Get all active search queries
        queries = db.query(SearchQuery).filter(SearchQuery.is_active == True).all()
        
        if not queries:
            logger.warning("No active search queries found")
            return {"status": "no_queries", "processed": 0}
        
        total_listings = 0
        new_listings = 0
        updated_listings = 0
        
        for query in queries:
            try:
                listings_count, new_count, updated_count = run_async(
                    _scrape_query_listings(db, query)
                )
                total_listings += listings_count
                new_listings += new_count
                updated_listings += updated_count
                logger.info(
                    f"Processed '{query.card_name}': {listings_count} listings "
                    f"({new_count} new, {updated_count} updated)"
                )
            except Exception as e:
                logger.error(f"Error scraping '{query.card_name}': {e}")
                continue
        
        logger.info(
            f"Task 1 complete: {total_listings} total listings, "
            f"{new_listings} new, {updated_listings} updated"
        )
        
        return {
            "status": "success",
            "total_listings": total_listings,
            "new_listings": new_listings,
            "updated_listings": updated_listings,
        }
        
    except Exception as e:
        logger.error(f"Task 1 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()


async def _scrape_query_listings(db, query: SearchQuery) -> tuple[int, int, int]:
    """Scrape listings for a single search query."""
    # Fetch listings from eBay
    api_response = await ebay_browse.search_psa10_listings(query.query_text, language=query.language)
    listings = ebay_browse.parse_listings(api_response)
    
    new_count = 0
    updated_count = 0
    
    for listing_data in listings:
        ebay_item_id = listing_data.get("ebay_item_id")
        if not ebay_item_id:
            continue
        
        # Check if listing already exists
        existing = db.query(PSA10Listing).filter(
            PSA10Listing.ebay_item_id == ebay_item_id
        ).first()
        
        if existing:
            # Update last_seen_at
            existing.last_seen_at = datetime.utcnow()
            existing.price_aud = listing_data["price_aud"]
            existing.shipping_cost_aud = listing_data.get("shipping_cost_aud")
            updated_count += 1
        else:
            # Create new listing
            new_listing = PSA10Listing(
                search_query_id=query.id,
                **listing_data,
            )
            db.add(new_listing)
            new_count += 1
    
    db.commit()
    return len(listings), new_count, updated_count
