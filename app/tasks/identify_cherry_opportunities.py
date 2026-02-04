"""Task 3 (new): Identify discounts of Cherry PSA10 products vs eBay sold benchmarks."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from app.config import settings
from app.database import SessionLocal
from app.models import (
    SearchQuery,
    CherryListing,
    SoldBenchmark,
    CherryOpportunity,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def identify_cherry_opportunities(self, arbitrage_threshold: float = None):
    """
    For each active CherryListing matched to an in-scope query:
    - find the latest SoldBenchmark for that query
    - compute discount vs market
    - store/update CherryOpportunity
    """
    logger.info("Starting Task 3: Identify Cherry Opportunities")

    db = SessionLocal()
    try:
        threshold = (
            Decimal(str(arbitrage_threshold))
            if arbitrage_threshold is not None
            else Decimal(str(settings.arbitrage_threshold))
        )

        opportunities_found = 0
        listings_checked = 0

        cutoff_bench = datetime.utcnow() - timedelta(hours=24)
        cutoff_listing = datetime.utcnow() - timedelta(hours=24)

        # Get all active Cherry listings
        listings = (
            db.query(CherryListing)
            .filter(CherryListing.is_active == True)
            .filter(CherryListing.last_seen_at >= cutoff_listing)
            .all()
        )

        for listing in listings:
            if settings.cherry_require_in_stock and not listing.in_stock:
                continue
            
            listings_checked += 1
            
            # Find benchmark for this specific grader/grade combination
            data_source = f"ebay_browse_{listing.grader}_{listing.grade}"
            latest = (
                db.query(SoldBenchmark)
                .filter(SoldBenchmark.search_query_id == listing.search_query_id)
                .filter(SoldBenchmark.data_source == data_source)
                .filter(SoldBenchmark.calculated_at >= cutoff_bench)
                .order_by(SoldBenchmark.calculated_at.desc())
                .first()
            )
            
            if not latest:
                continue

            market_price = Decimal(latest.market_price)
            threshold_price = market_price * threshold
            store_price = Decimal(listing.price_aud)

            if store_price < threshold_price:
                query = db.query(SearchQuery).filter(SearchQuery.id == listing.search_query_id).first()
                if query:
                    opp = _create_or_update(db, query, listing, market_price, store_price)
                    if opp:
                        opportunities_found += 1

        _deactivate_stale(db)
        db.commit()

        logger.info(
            f"Task 3 complete: {opportunities_found} opportunities, {listings_checked} listings checked"
        )
        return {
            "status": "success",
            "opportunities_found": opportunities_found,
            "listings_checked": listings_checked,
            "arbitrage_threshold": float(threshold),
        }

    except Exception as e:
        logger.error(f"Task 3 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()


def _create_or_update(
    db,
    query: SearchQuery,
    listing: CherryListing,
    market_price: Decimal,
    store_price: Decimal,
) -> CherryOpportunity:
    discount = ((market_price - store_price) / market_price) * Decimal("100")
    profit = market_price - store_price

    existing = (
        db.query(CherryOpportunity)
        .filter(CherryOpportunity.cherry_listing_id == listing.id)
        .filter(CherryOpportunity.is_active == True)
        .first()
    )

    now = datetime.utcnow()
    if existing:
        existing.card_name = query.card_name
        existing.product_title = listing.title
        existing.store_price = store_price
        existing.market_price = market_price
        existing.discount_percentage = discount
        existing.potential_profit = profit
        existing.product_url = listing.product_url
        existing.image_url = listing.image_url
        existing.in_stock = listing.in_stock
        existing.last_verified_at = now
        return existing

    opp = CherryOpportunity(
        cherry_listing_id=listing.id,
        search_query_id=query.id,
        card_name=query.card_name,
        product_title=listing.title,
        store_price=store_price,
        market_price=market_price,
        discount_percentage=discount,
        potential_profit=profit,
        product_url=listing.product_url,
        image_url=listing.image_url,
        in_stock=listing.in_stock,
        is_active=True,
        discovered_at=now,
        last_verified_at=now,
    )
    db.add(opp)
    return opp


def _deactivate_stale(db):
    cutoff = datetime.utcnow() - timedelta(hours=6)
    stale = (
        db.query(CherryOpportunity)
        .filter(CherryOpportunity.is_active == True)
        .filter(CherryOpportunity.last_verified_at < cutoff)
        .update({"is_active": False})
    )
    if stale:
        logger.info(f"Deactivated {stale} stale cherry opportunities")

    # Deactivate opportunities for listings no longer active
    inactive = (
        db.query(CherryOpportunity)
        .filter(CherryOpportunity.is_active == True)
        .filter(CherryOpportunity.cherry_listing_id == CherryListing.id)
        .filter(CherryListing.is_active == False)
        .update({"is_active": False}, synchronize_session=False)
    )
    if inactive:
        logger.info(f"Deactivated {inactive} opportunities for inactive listings")

