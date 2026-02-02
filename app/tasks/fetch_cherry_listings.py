"""Task 1 (new): Fetch Cherry Collectables PSA10 products and match to in-scope queries."""

import asyncio
import logging
import re
import time
from datetime import datetime
from decimal import Decimal

from app.api.cherry_shopify import cherry_shopify, CherryProduct
from app.config import settings
from app.database import SessionLocal
from app.models import SearchQuery, CherryListing
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(s: str) -> set[str]:
    s = (s or "").lower()
    # Normalize common punctuation variants
    s = s.replace("1st", "first")
    s = s.replace("lv.x", "lvx").replace("lv x", "lvx")
    return set(_WORD_RE.findall(s))


def _is_psa10(title: str, tags: list[str]) -> bool:
    t = (title or "").upper()
    if "PSA 10" in t or "PSA10" in t:
        return True
    # Fallback: tags sometimes include PSA but not grade; keep strict.
    return False


def _is_jp_title(title: str) -> bool:
    t = (title or "").upper()
    return (
        "JAPANESE" in t
        or "JPN" in t
        or " JP " in f" {t} "
        or "JP-" in t
        or "JP_" in t
    )


def _match_score(query_text: str, title: str) -> float:
    qt = _tokens(query_text)
    tt = _tokens(title)
    if not qt or not tt:
        return 0.0

    # Require the main name token to exist (first token of query).
    main = next(iter(qt))
    if main not in tt:
        # try relaxed: any token length>=4 must exist
        long_tokens = [x for x in qt if len(x) >= 4]
        if long_tokens and not any(x in tt for x in long_tokens):
            return 0.0

    matched = len(qt.intersection(tt))
    return matched / max(len(qt), 1)


@celery_app.task(bind=True, max_retries=3)
def fetch_cherry_listings(self):
    """
    Fetch Cherry PSA10 products and match them to in-scope SearchQuery rows.

    Uses per-run replacement semantics:
    - mark all currently-active Cherry listings inactive
    - reactivate/update those seen this run
    """
    logger.info("Starting Task 1: Fetch Cherry Listings (PSA10 only, query-based search)")

    db = SessionLocal()
    try:
        queries = db.query(SearchQuery).filter(SearchQuery.is_active == True).all()
        if not queries:
            logger.warning("No active search queries found")
            return {"status": "no_queries", "processed": 0}

        # Snapshot previously-active listings
        prev_active = db.query(CherryListing).filter(CherryListing.is_active == True).count()
        db.query(CherryListing).filter(CherryListing.is_active == True).update(
            {"is_active": False}, synchronize_session=False
        )

        now = datetime.utcnow()
        new_count = 0
        updated_count = 0
        reactivated_count = 0
        matched_count = 0

        for q in queries:
            lang = (q.language or "EN").upper()
            keywords = f"psa 10 {q.query_text}"
            if lang == "JP":
                keywords = f"{keywords} japanese"

            # Use predictive search first (low request volume).
            try:
                suggestions = run_async(cherry_shopify.search_suggest_products(keywords, limit=8))
            except Exception as e:
                logger.error(f"Cherry search failed for '{q.card_name}': {e}")
                continue

            # For each suggested handle, fetch product JS to get variant ids/prices.
            seen_handles: set[str] = set()
            for s in suggestions:
                handle = (s.get("handle") or "").strip()
                if not handle or handle in seen_handles:
                    continue
                seen_handles.add(handle)

                # gentle pacing to avoid 429s
                time.sleep(0.15)
                try:
                    product_js = run_async(cherry_shopify.fetch_product_js(handle))
                    variants = cherry_shopify.parse_product_js_variants(product_js)
                except Exception as e:
                    logger.debug(f"Cherry product fetch failed handle={handle}: {e}")
                    continue

                # Keep only PSA10 products and (optionally) in-stock variants.
                for prod in variants:
                    if settings.cherry_require_in_stock and not prod.in_stock:
                        continue
                    if not _is_psa10(prod.title, prod.tags):
                        continue
                    # Ensure this actually matches the query text (avoid generic charizard hits).
                    if _match_score(q.query_text, prod.title) < 0.6:
                        continue
                    # Enforce language stream separation.
                    if lang == "JP":
                        if not _is_jp_title(prod.title):
                            continue
                    else:
                        if _is_jp_title(prod.title):
                            continue

                    matched_count += 1

                    existing = (
                        db.query(CherryListing)
                        .filter(CherryListing.product_id == prod.product_id)
                        .filter(CherryListing.variant_id == prod.variant_id)
                        .first()
                    )

                    if existing:
                        existing.search_query_id = q.id
                        existing.title = prod.title
                        existing.handle = prod.handle
                        existing.product_url = prod.product_url
                        existing.image_url = prod.image_url
                        existing.price_aud = prod.price_aud
                        existing.in_stock = prod.in_stock
                        existing.language = lang
                        existing.grader = "PSA"
                        existing.grade = 10
                        existing.last_seen_at = now
                        if not existing.is_active:
                            existing.is_active = True
                            reactivated_count += 1
                        updated_count += 1
                    else:
                        db.add(
                            CherryListing(
                                search_query_id=q.id,
                                product_id=prod.product_id,
                                variant_id=prod.variant_id,
                                title=prod.title,
                                handle=prod.handle,
                                product_url=prod.product_url,
                                image_url=prod.image_url,
                                price_aud=Decimal(prod.price_aud),
                                in_stock=prod.in_stock,
                                language=lang,
                                grader="PSA",
                                grade=10,
                                is_active=True,
                                scraped_at=now,
                                last_seen_at=now,
                            )
                        )
                        new_count += 1

        db.commit()
        removed_count = max(prev_active - reactivated_count, 0)

        logger.info(
            "Task 1 complete: %s matched, %s new, %s updated, %s removed",
            matched_count,
            new_count,
            updated_count,
            removed_count,
        )

        return {
            "status": "success",
            "matched": matched_count,
            "new_listings": new_count,
            "updated_listings": updated_count,
            "removed_listings": removed_count,
        }

    except Exception as e:
        logger.error(f"Task 1 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()

