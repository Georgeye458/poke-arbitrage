"""Task 2: Fetch market benchmarks from eBay active listings.

Uses the Browse API to fetch active graded card listings and compute median prices
as the market benchmark. Supports both PSA and CGC graded cards.
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal

import httpx

from app.api.ebay_browse import ebay_browse
from app.config import settings
from app.database import SessionLocal
from app.models import SearchQuery, SoldBenchmark, CherryListing, LeoListing
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _is_jp_title(t: str) -> bool:
    t = (t or "").upper()
    return (
        "JAPANESE" in t
        or "JPN" in t
        or " JP " in f" {t} "
        or "JP-" in t
        or "JP_" in t
    )


def _median_dec(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / Decimal("2")


def _get_grader_grade_combinations(db, query_id: int) -> list[tuple[str, int]]:
    """Get all unique (grader, grade) combinations for a query from both stores."""
    combinations = set()
    
    # Check Cherry listings
    cherry_listings = (
        db.query(CherryListing.grader, CherryListing.grade)
        .filter(CherryListing.search_query_id == query_id)
        .filter(CherryListing.is_active == True)
        .distinct()
        .all()
    )
    for grader, grade in cherry_listings:
        combinations.add((grader, grade))
    
    # Check Leo listings
    leo_listings = (
        db.query(LeoListing.grader, LeoListing.grade)
        .filter(LeoListing.search_query_id == query_id)
        .filter(LeoListing.is_active == True)
        .distinct()
        .all()
    )
    for grader, grade in leo_listings:
        combinations.add((grader, grade))
    
    return list(combinations)


@celery_app.task(bind=True, max_retries=3)
def fetch_sold_benchmarks(self):
    """
    For each active SearchQuery, compute a market benchmark (AUD) from eBay active listings.

    Uses the Browse API to fetch active graded card listings and computes the median price
    as the market benchmark.

    Fetches benchmarks for each (grader, grade) combination found in store listings.

    Scope filters:
    - price_floor_aud <= benchmark < price_ceiling_aud
    """
    logger.info("Starting Task 2: Fetch Market Benchmarks (eBay Browse API)")

    db = SessionLocal()
    try:
        # Only compute benchmarks for queries that have active store listings
        cherry_query_ids = (
            db.query(CherryListing.search_query_id)
            .filter(CherryListing.is_active == True)
            .distinct()
            .all()
        )
        leo_query_ids = (
            db.query(LeoListing.search_query_id)
            .filter(LeoListing.is_active == True)
            .distinct()
            .all()
        )
        
        query_ids = set([q[0] for q in cherry_query_ids] + [q[0] for q in leo_query_ids])
        
        if not query_ids:
            logger.warning("No active store listings found")
            return {"status": "no_listings", "processed": 0}

        queries = (
            db.query(SearchQuery)
            .filter(SearchQuery.id.in_(query_ids))
            .filter(SearchQuery.is_active == True)
            .all()
        )

        if not queries:
            logger.warning("No active search queries found")
            return {"status": "no_queries", "processed": 0}

        stored = 0
        filtered = 0
        errors = 0

        max_q = int(getattr(settings, "sold_benchmark_max_queries_per_run", 8) or 8)
        min_age = int(getattr(settings, "sold_benchmark_min_age_hours", 24) or 24)
        recent_cutoff = datetime.utcnow().timestamp() - (min_age * 3600)

        processed = 0
        for q in queries:
            if processed >= max_q:
                break

            # Get all grader/grade combinations for this query
            combinations = _get_grader_grade_combinations(db, q.id)
            if not combinations:
                continue

            for grader, grade in combinations:
                # Skip if we have a recent benchmark for this specific grader/grade
                data_source = f"ebay_browse_{grader}_{grade}"
                latest = (
                    db.query(SoldBenchmark)
                    .filter(SoldBenchmark.search_query_id == q.id)
                    .filter(SoldBenchmark.data_source == data_source)
                    .order_by(SoldBenchmark.calculated_at.desc())
                    .first()
                )
                if latest and latest.calculated_at and latest.calculated_at.timestamp() >= recent_cutoff:
                    continue

                processed += 1
                if processed > max_q:
                    break

                try:
                    # Use card_name for eBay search (includes card number for better matching)
                    # Fall back to query_text if card_name is empty
                    search_query = q.card_name if q.card_name else q.query_text
                    
                    # Fetch active listings from eBay Browse API
                    response = run_async(
                        ebay_browse.search_listings(
                            query=search_query,
                            language=q.language,
                            mode="GRADED",
                            grader=grader,
                            grade=grade,
                            limit=50,
                        )
                    )

                    # Parse listings and extract prices
                    listings = ebay_browse.parse_listings(response)
                    prices: list[Decimal] = []
                    grader_upper = grader.upper()
                    
                    for listing in listings:
                        title = (listing.get("title") or "").upper()
                        
                        # Verify grader in title
                        if grader_upper == "PSA":
                            if f"PSA {grade}" not in title and f"PSA{grade}" not in title:
                                continue
                        elif grader_upper == "CGC":
                            if f"CGC {grade}" not in title and f"CGC{grade}" not in title and f"CGC PRISTINE {grade}" not in title:
                                continue
                        
                        # Enforce language stream separation
                        if (q.language or "EN").upper() == "JP":
                            if not _is_jp_title(listing.get("title", "")):
                                continue
                        else:
                            if _is_jp_title(listing.get("title", "")):
                                continue

                        price = listing.get("price_aud")
                        if price is not None:
                            prices.append(Decimal(price))

                    if not prices:
                        logger.debug(f"No prices found for '{q.card_name}' {grader} {grade}")
                        filtered += 1
                        continue

                    market = _median_dec(prices)
                    if market >= Decimal(str(settings.price_ceiling_aud)) or market < Decimal(
                        str(settings.price_floor_aud)
                    ):
                        filtered += 1
                        continue

                    bench = SoldBenchmark(
                        search_query_id=q.id,
                        market_price=market.quantize(Decimal("0.01")),
                        data_source=data_source,
                        sample_size=len(prices),
                        min_price=min(prices).quantize(Decimal("0.01")),
                        max_price=max(prices).quantize(Decimal("0.01")),
                        calculated_at=datetime.utcnow(),
                    )
                    db.add(bench)
                    db.commit()
                    stored += 1
                    logger.info(f"Stored benchmark for '{q.card_name}' {grader} {grade}: ${market:.2f} (n={len(prices)})")

                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error fetching benchmark for '{q.card_name}' {grader} {grade}: {e}")
                    db.rollback()
                    errors += 1
                    continue
                except Exception as e:
                    logger.error(f"Error fetching benchmark for '{q.card_name}' {grader} {grade}: {e}")
                    db.rollback()
                    errors += 1
                    continue

        logger.info(
            f"Task 2 complete: {stored} stored, {filtered} filtered, {errors} errors"
        )
        return {
            "status": "success",
            "stored": stored,
            "filtered": filtered,
            "errors": errors,
            "processed": processed,
        }

    except Exception as e:
        logger.error(f"Task 2 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()
