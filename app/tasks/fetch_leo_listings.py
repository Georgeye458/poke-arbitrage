"""Task: Fetch Leo Games PSA 10 and CGC 10 graded Pokemon cards."""

import asyncio
import logging
import re
import time
from datetime import datetime
from decimal import Decimal

from app.api.leo_shopify import leo_shopify, LeoProduct
from app.config import settings
from app.database import SessionLocal
from app.models import SearchQuery, LeoListing
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


def _is_jp_title(title: str) -> bool:
    t = (title or "").upper()
    return (
        "JAPANESE" in t
        or "JPN" in t
        or " JP " in f" {t} "
        or "JP-" in t
        or "JP_" in t
        or "(JAPANESE)" in t
    )


def _derive_query_from_title(title: str, grader: str) -> tuple[str, str]:
    """Derive (query_text, card_name) from a Leo Games product title.

    query_text: normalized for internal matching/deduplication
    card_name: preserved with card number for eBay searching
    """
    t = (title or "").strip()
    u = t.upper()

    # Remove year prefixes like "2023 " or "1999 "
    t = re.sub(r"^\d{4}\s+", "", t).strip()
    u = t.upper()

    # Remove grading/language prefixes commonly present in titles.
    for needle in ["JAPANESE ", "CHINESE ", "KOREAN "]:
        if u.startswith(needle):
            t = t[len(needle):].strip()
            u = t.upper()
            break

    # Remove PSA grade patterns like "PSA 10 " / "PSA10 " / "PSA 9"
    t = re.sub(r"\bPSA\s*\d+\b", "", t, flags=re.IGNORECASE).strip()
    # Remove CGC grade patterns like "CGC 10" / "CGC PRISTINE 10" / "CGC 9.5"
    t = re.sub(r"\bCGC\s*(?:PRISTINE\s*)?\d+(?:\.\d+)?\b", "", t, flags=re.IGNORECASE).strip()

    # Remove trailing inventory numbers (often at end)
    t = re.sub(r"\s+\d{2,}$", "", t).strip()

    # card_name keeps the card number for eBay searching
    card_name = t[:255] if t else title[:255]

    # query_text removes card number for internal matching (avoids duplicates)
    query_text_base = re.sub(r"\b\d{1,4}[a-z]?\s*/\s*\d{1,4}\b", "", t, flags=re.IGNORECASE).strip()
    query_text_base = re.sub(r"#\d+", "", query_text_base).strip()
    query_text = " ".join(_WORD_RE.findall(query_text_base.lower()))

    return query_text[:255], card_name


def _is_grade_10(grader: str, grade: int) -> bool:
    """Check if the grade is 10 (or CGC Pristine 10)."""
    return grade == 10


@celery_app.task(bind=True, max_retries=3)
def fetch_leo_listings(self):
    """
    Fetch Leo Games PSA 10 and CGC 10 products and match them to SearchQuery rows.

    Scans both PSA and CGC collections.
    Uses per-run replacement semantics:
    - mark all currently-active Leo listings inactive
    - reactivate/update those seen this run
    """
    logger.info("Starting Task: Fetch Leo Games Listings (PSA 10 + CGC 10)")

    db = SessionLocal()
    try:
        # Snapshot previously-active listings
        prev_active = db.query(LeoListing).filter(LeoListing.is_active == True).count()
        db.query(LeoListing).filter(LeoListing.is_active == True).update(
            {"is_active": False}, synchronize_session=False
        )

        now = datetime.utcnow()
        stats = {
            "new_count": 0,
            "updated_count": 0,
            "reactivated_count": 0,
            "matched_count": 0,
            "created_queries": 0,
        }

        # Collections to scan: (collection_handle, expected_grader)
        collections = [
            (settings.leo_psa_collection_handle, "PSA"),
            (settings.leo_cgc_collection_handle, "CGC"),
        ]

        for collection_handle, expected_grader in collections:
            logger.info(f"Scanning Leo Games collection: {collection_handle}")
            page = 1
            max_pages = 30  # safety cap
            
            while page <= max_pages:
                try:
                    batch: list[LeoProduct] = run_async(
                        leo_shopify.fetch_collection_products(collection_handle, page=page)
                    )
                except Exception as e:
                    logger.warning(f"Leo Games page fetch failed collection={collection_handle} page={page}: {e}")
                    time.sleep(5)
                    continue

                if not batch:
                    break

                for prod in batch:
                    if settings.leo_require_in_stock and not prod.in_stock:
                        continue
                    
                    # Only process grade 10 cards
                    if not _is_grade_10(prod.grader, prod.grade):
                        continue

                    lang = "JP" if _is_jp_title(prod.title) else "EN"
                    query_text, card_name = _derive_query_from_title(prod.title, prod.grader)
                    if not query_text:
                        continue

                    # Ensure SearchQuery exists for this derived identity.
                    # Include grader in query matching for differentiation
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
                        stats["created_queries"] += 1

                    stats["matched_count"] += 1

                    existing = (
                        db.query(LeoListing)
                        .filter(LeoListing.product_id == prod.product_id)
                        .filter(LeoListing.variant_id == prod.variant_id)
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
                        existing.grader = prod.grader
                        existing.grade = prod.grade
                        existing.last_seen_at = now
                        if not existing.is_active:
                            existing.is_active = True
                            stats["reactivated_count"] += 1
                        stats["updated_count"] += 1
                    else:
                        db.add(
                            LeoListing(
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
                                grader=prod.grader,
                                grade=prod.grade,
                                is_active=True,
                                scraped_at=now,
                                last_seen_at=now,
                            )
                        )
                        stats["new_count"] += 1

                # commit per page to keep transaction small
                db.commit()
                time.sleep(0.25)
                page += 1

        removed_count = max(prev_active - stats["reactivated_count"], 0)

        logger.info(
            "Leo Games fetch complete: %s matched, %s new, %s updated, %s removed (new queries=%s)",
            stats["matched_count"],
            stats["new_count"],
            stats["updated_count"],
            removed_count,
            stats["created_queries"],
        )

        return {
            "status": "success",
            "matched": stats["matched_count"],
            "new_listings": stats["new_count"],
            "updated_listings": stats["updated_count"],
            "removed_listings": removed_count,
            "new_queries": stats["created_queries"],
        }

    except Exception as e:
        logger.error(f"Leo Games fetch failed: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()
