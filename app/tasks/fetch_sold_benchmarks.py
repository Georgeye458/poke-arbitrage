"""Task 2 (new): Fetch sold benchmarks from eBay completed items."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal

import httpx

from app.api.ebay_finding_sold import ebay_finding_sold
from app.config import settings
from app.database import SessionLocal
from app.models import SearchQuery, SoldBenchmark, CherryListing
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
        # Only compute benchmarks for queries that have active Cherry listings.
        queries = (
            db.query(SearchQuery)
            .join(CherryListing, CherryListing.search_query_id == SearchQuery.id)
            .filter(SearchQuery.is_active == True)
            .filter(CherryListing.is_active == True)
            .distinct()
            .all()
        )
        if not queries:
            logger.warning("No active search queries found")
            return {"status": "no_queries", "processed": 0}

        stored = 0
        filtered = 0
        errors = 0
        rate_limited = False

        # Only compute for queries that need refresh (no recent benchmark)
        cutoff_bench = datetime.utcnow()

        # Sort by recency of cherry listing activity (best-effort)
        q_ids = [q.id for q in queries]
        recent_listing = (
            db.query(CherryListing.search_query_id, CherryListing.last_seen_at)
            .filter(CherryListing.search_query_id.in_(q_ids))
            .filter(CherryListing.is_active == True)
            .order_by(CherryListing.last_seen_at.desc())
            .all()
        )
        ordered_ids = []
        seen = set()
        for sid, _ts in recent_listing:
            if sid not in seen:
                ordered_ids.append(sid)
                seen.add(sid)
        for sid in q_ids:
            if sid not in seen:
                ordered_ids.append(sid)
                seen.add(sid)

        max_q = int(getattr(settings, "sold_benchmark_max_queries_per_run", 8) or 8)
        min_age = int(getattr(settings, "sold_benchmark_min_age_hours", 24) or 24)
        recent_cutoff = datetime.utcnow().timestamp() - (min_age * 3600)

        # Map id -> query
        q_by_id = {q.id: q for q in queries}

        processed = 0
        for qid in ordered_ids:
            q = q_by_id.get(qid)
            if not q:
                continue

            # Skip if we have a recent benchmark
            latest = (
                db.query(SoldBenchmark)
                .filter(SoldBenchmark.search_query_id == q.id)
                .order_by(SoldBenchmark.calculated_at.desc())
                .first()
            )
            if latest and latest.calculated_at and latest.calculated_at.timestamp() >= recent_cutoff:
                continue

            processed += 1
            if processed > max_q:
                break

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
            except httpx.HTTPStatusError as e:
                # eBay Finding API often returns 500 with a JSON RateLimiter error body.
                body = ""
                try:
                    body = e.response.text or ""
                except Exception:
                    body = ""
                if "RateLimiter" in body or "exceeded the number of times" in body:
                    logger.error("Rate limited by eBay Finding API; stopping benchmark fetch for now.")
                    rate_limited = True
                    db.rollback()
                    break
                logger.error(f"Error fetching sold benchmark for '{q.card_name}': {e}")
                db.rollback()
                errors += 1
                continue
            except Exception as e:
                logger.error(f"Error fetching sold benchmark for '{q.card_name}': {e}")
                db.rollback()
                errors += 1
                continue

        logger.info(
            f"Task 2 complete: {stored} stored, {filtered} filtered, {errors} errors (rate_limited={rate_limited})"
        )
        return {
            "status": "success",
            "stored": stored,
            "filtered": filtered,
            "errors": errors,
            "rate_limited": rate_limited,
            "processed": processed,
        }

    except Exception as e:
        logger.error(f"Task 2 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()

