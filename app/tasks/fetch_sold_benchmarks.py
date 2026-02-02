"""Task 2 (new): Fetch sold benchmarks from eBay completed items."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal

from app.api.ebay_finding_sold import ebay_finding_sold
from app.config import settings
from app.database import SessionLocal
from app.models import SearchQuery, SoldBenchmark
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


@celery_app.task(bind=True, max_retries=3)
def fetch_sold_benchmarks(self):
    """
    For each active SearchQuery, compute a sold-price benchmark (AUD) from completed items.

    Scope filters:
    - price_floor_aud <= benchmark < price_ceiling_aud
    """
    logger.info("Starting Task 2: Fetch Sold Benchmarks (eBay completed items)")

    db = SessionLocal()
    try:
        queries = db.query(SearchQuery).filter(SearchQuery.is_active == True).all()
        if not queries:
            logger.warning("No active search queries found")
            return {"status": "no_queries", "processed": 0}

        stored = 0
        filtered = 0
        errors = 0

        for q in queries:
            try:
                comps = run_async(
                    ebay_finding_sold.find_completed_items(
                        query=q.query_text,
                        language=q.language,
                        max_results=settings.sold_comps_max_results,
                    )
                )

                # Keep PSA10-ish results only
                prices: list[Decimal] = []
                for comp in comps:
                    title = (comp.title or "").upper()
                    if "PSA 10" not in title and "PSA10" not in title:
                        continue

                    # Enforce language stream separation
                    if (q.language or "EN").upper() == "JP":
                        if not _is_jp_title(comp.title):
                            continue
                    else:
                        if _is_jp_title(comp.title):
                            continue

                    if comp.price_aud is not None:
                        prices.append(Decimal(comp.price_aud))

                if not prices:
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
                    data_source="ebay_finding_completed",
                    sample_size=len(prices),
                    min_price=min(prices).quantize(Decimal("0.01")),
                    max_price=max(prices).quantize(Decimal("0.01")),
                    calculated_at=datetime.utcnow(),
                )
                db.add(bench)
                db.commit()
                stored += 1
            except Exception as e:
                logger.error(f"Error fetching sold benchmark for '{q.card_name}': {e}")
                db.rollback()
                errors += 1
                continue

        logger.info(f"Task 2 complete: {stored} stored, {filtered} filtered, {errors} errors")
        return {"status": "success", "stored": stored, "filtered": filtered, "errors": errors}

    except Exception as e:
        logger.error(f"Task 2 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()

