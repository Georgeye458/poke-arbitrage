"""Task 1 (new): Fetch Cherry Collectables PSA10 products (Pokemon singles)."""

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


def _is_cgc10(title: str, tags: list[str]) -> bool:
    """Check if the card is CGC 10 graded."""
    t = (title or "").upper()
    if "CGC 10" in t or "CGC10" in t or "CGC PRISTINE 10" in t:
        return True
    return False


def _detect_grading(title: str, tags: list[str]) -> tuple[str | None, int | None]:
    """Detect grader and grade from title/tags. Returns (grader, grade) or (None, None)."""
    if _is_psa10(title, tags):
        return "PSA", 10
    if _is_cgc10(title, tags):
        return "CGC", 10
    return None, None


def _is_jp_title(title: str) -> bool:
    t = (title or "").upper()
    return (
        "JAPANESE" in t
        or "JPN" in t
        or " JP " in f" {t} "
        or "JP-" in t
        or "JP_" in t
    )


def _derive_query_from_title(title: str) -> tuple[str, str]:
    """Derive (query_text, card_name) from a Cherry product title.

    We strip grading + language noise and keep a stable, searchable identity string.
    """
    t = (title or "").strip()
    u = t.upper()

    # Remove grading/language prefixes commonly present in Cherry titles.
    for needle in ["JAPANESE ", "CHINESE ", "KOREAN "]:
        if u.startswith(needle):
            t = t[len(needle) :].strip()
            u = t.upper()
            break

    # Remove PSA grade prefix like "PSA 10 " / "PSA10 "
    if u.startswith("PSA 10 "):
        t = t[7:].strip()
    elif u.startswith("PSA10 "):
        t = t[6:].strip()

    # Remove trailing inventory numbers (often at end)
    t = re.sub(r"\s+\d{2,}$", "", t).strip()

    # Remove obvious card number patterns like 123/456
    t = re.sub(r"\b\d{1,4}\s*/\s*\d{1,4}\b", "", t).strip()

    # Normalize separators
    query_text = " ".join(_WORD_RE.findall(t.lower()))
    card_name = t[:255] if t else title[:255]
    return query_text[:255], card_name


@celery_app.task(bind=True, max_retries=3)
def fetch_cherry_listings(self):
    """
    Fetch Cherry PSA10 products and match them to in-scope SearchQuery rows.

    Uses per-run replacement semantics:
    - mark all currently-active Cherry listings inactive
    - reactivate/update those seen this run
    """
    logger.info("Starting Task 1: Fetch Cherry Listings (PSA10 only, collection scan)")

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

        # Pull the Pokemon singles collection in pages (with gentle pacing).
        now = datetime.utcnow()
        new_count = 0
        updated_count = 0
        reactivated_count = 0
        matched_count = 0
        created_queries = 0

        collection = settings.cherry_collection_handle
        page = 1
        max_pages = 30  # safety cap
        while page <= max_pages:
            try:
                batch: list[CherryProduct] = run_async(
                    cherry_shopify.fetch_collection_products(collection, page=page)
                )
            except Exception as e:
                # Back off a bit (covers 429s and transient errors)
                logger.warning(f"Cherry page fetch failed page={page}: {e}")
                time.sleep(5)
                continue

            if not batch:
                break

            for prod in batch:
                if settings.cherry_require_in_stock and not prod.in_stock:
                    continue
                
                # Detect grading (PSA 10 or CGC 10)
                grader, grade = _detect_grading(prod.title, prod.tags)
                if not grader or grade != 10:
                    continue

                lang = "JP" if _is_jp_title(prod.title) else "EN"
                query_text, card_name = _derive_query_from_title(prod.title)
                if not query_text:
                    continue

                # Ensure SearchQuery exists for this derived identity.
                sq = (
                    db.query(SearchQuery)
                    .filter(SearchQuery.query_text == query_text)
                    .filter(SearchQuery.language == lang)
                    .first()
                )
                if not sq:
                    sq = SearchQuery(
                        query_text=query_text,
                        card_name=card_name,
                        language=lang,
                        is_active=True,
                    )
                    db.add(sq)
                    db.flush()  # get sq.id
                    created_queries += 1

                matched_count += 1

                existing = (
                    db.query(CherryListing)
                    .filter(CherryListing.product_id == prod.product_id)
                    .filter(CherryListing.variant_id == prod.variant_id)
                    .first()
                )

                if existing:
                    existing.search_query_id = sq.id
                    existing.title = prod.title
                    existing.handle = prod.handle
                    existing.product_url = prod.product_url
                    existing.image_url = prod.image_url
                    existing.price_aud = prod.price_aud
                    existing.in_stock = prod.in_stock
                    existing.language = lang
                    existing.grader = grader
                    existing.grade = grade
                    existing.last_seen_at = now
                    if not existing.is_active:
                        existing.is_active = True
                        reactivated_count += 1
                    updated_count += 1
                else:
                    db.add(
                        CherryListing(
                            search_query_id=sq.id,
                            product_id=prod.product_id,
                            variant_id=prod.variant_id,
                            title=prod.title,
                            handle=prod.handle,
                            product_url=prod.product_url,
                            image_url=prod.image_url,
                            price_aud=Decimal(prod.price_aud),
                            in_stock=prod.in_stock,
                            language=lang,
                            grader=grader,
                            grade=grade,
                            is_active=True,
                            scraped_at=now,
                            last_seen_at=now,
                        )
                    )
                    new_count += 1

            # commit per page to keep transaction small
            db.commit()
            time.sleep(0.25)
            page += 1

        removed_count = max(prev_active - reactivated_count, 0)

        logger.info(
            "Task 1 complete: %s matched, %s new, %s updated, %s removed (new queries=%s)",
            matched_count,
            new_count,
            updated_count,
            removed_count,
            created_queries,
        )

        return {
            "status": "success",
            "matched": matched_count,
            "new_listings": new_count,
            "updated_listings": updated_count,
            "removed_listings": removed_count,
            "new_queries": created_queries,
        }

    except Exception as e:
        logger.error(f"Task 1 failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()

