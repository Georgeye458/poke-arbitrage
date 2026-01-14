"""Task 3: Identify arbitrage opportunities."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import SearchQuery, PSA10Listing, MarketBenchmark, ArbitrageOpportunity
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def identify_all_opportunities(self):
    """
    Task 3: Identify arbitrage opportunities.
    
    For each live listing in psa10_listings:
    - Find corresponding market_price from latest benchmark
    - If no market price exists (filtered out for being >$3k), ignore listing
    - If listing_price < (market_price * 0.85), create arbitrage record
    """
    logger.info("Starting Task 3: Identify Arbitrage Opportunities")
    
    db = SessionLocal()
    try:
        # Get all active search queries
        queries = db.query(SearchQuery).filter(SearchQuery.is_active == True).all()
        
        if not queries:
            logger.warning("No active search queries found")
            return {"status": "no_queries", "processed": 0}
        
        opportunities_found = 0
        listings_checked = 0
        
        for query in queries:
            # Get latest benchmark for this query (within last 2 hours)
            cutoff_time = datetime.utcnow() - timedelta(hours=2)
            latest_benchmark = db.query(MarketBenchmark).filter(
                MarketBenchmark.search_query_id == query.id,
                MarketBenchmark.calculated_at >= cutoff_time,
            ).order_by(MarketBenchmark.calculated_at.desc()).first()
            
            if not latest_benchmark:
                # No valid benchmark (either filtered out or no data)
                logger.debug(f"No recent benchmark for '{query.card_name}', skipping")
                continue
            
            market_price = latest_benchmark.market_price
            threshold_price = market_price * Decimal(str(settings.arbitrage_threshold))
            
            # Get recent listings for this query (seen in last 2 hours)
            listings = db.query(PSA10Listing).filter(
                PSA10Listing.search_query_id == query.id,
                PSA10Listing.last_seen_at >= cutoff_time,
            ).all()
            
            for listing in listings:
                listings_checked += 1
                
                # Check for arbitrage opportunity
                shipping = listing.shipping_cost_aud or Decimal("0")
                total_price = listing.price_aud + shipping
                if total_price < threshold_price:
                    opportunity = _create_or_update_opportunity(
                        db, query, listing, market_price, total_price, shipping
                    )
                    if opportunity:
                        opportunities_found += 1
                        logger.info(
                            f"Opportunity found: {listing.title[:50]}... "
                            f"${total_price} (incl ship) vs ${market_price} market"
                        )
        
        # Mark old opportunities as inactive
        _deactivate_stale_opportunities(db)
        
        db.commit()
        
        logger.info(
            f"Task 3 complete: {opportunities_found} opportunities found, "
            f"{listings_checked} listings checked"
        )
        
        return {
            "status": "success",
            "opportunities_found": opportunities_found,
            "listings_checked": listings_checked,
        }
        
    except Exception as e:
        logger.error(f"Task 3 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()


def _create_or_update_opportunity(
    db,
    query: SearchQuery,
    listing: PSA10Listing,
    market_price: Decimal,
    total_price: Decimal,
    shipping_cost: Decimal,
) -> ArbitrageOpportunity:
    """Create or update an arbitrage opportunity."""
    # Calculate discount and profit
    discount = ((market_price - total_price) / market_price) * 100
    profit = market_price - total_price
    
    # Check if opportunity already exists
    existing = db.query(ArbitrageOpportunity).filter(
        ArbitrageOpportunity.ebay_item_id == listing.ebay_item_id,
        ArbitrageOpportunity.is_active == True,
    ).first()
    
    if existing:
        # Update existing opportunity
        existing.listing_price = total_price
        existing.shipping_cost = shipping_cost
        existing.market_price = market_price
        existing.discount_percentage = discount
        existing.potential_profit = profit
        existing.last_verified_at = datetime.utcnow()
        return existing
    
    # Create new opportunity
    opportunity = ArbitrageOpportunity(
        listing_id=listing.id,
        search_query_id=query.id,
        card_name=query.card_name,
        listing_title=listing.title,
        listing_price=total_price,
        shipping_cost=shipping_cost,
        market_price=market_price,
        discount_percentage=discount,
        potential_profit=profit,
        ebay_item_id=listing.ebay_item_id,
        item_url=listing.item_url,
        image_url=listing.image_url,
        seller_username=listing.seller_username,
        is_active=True,
        discovered_at=datetime.utcnow(),
        last_verified_at=datetime.utcnow(),
    )
    
    db.add(opportunity)
    return opportunity


def _deactivate_stale_opportunities(db):
    """Mark opportunities as inactive if listing is no longer seen."""
    cutoff_time = datetime.utcnow() - timedelta(hours=4)
    
    stale_count = db.query(ArbitrageOpportunity).filter(
        ArbitrageOpportunity.is_active == True,
        ArbitrageOpportunity.last_verified_at < cutoff_time,
    ).update({"is_active": False})
    
    if stale_count > 0:
        logger.info(f"Deactivated {stale_count} stale opportunities")
