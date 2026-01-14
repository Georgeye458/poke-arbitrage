"""
Expand broad buckets into concrete SearchQuery entries by using eBay Browse API ASPECT_REFINEMENTS.

Strategy:
- For each bucket, call Browse search with fieldgroups=ASPECT_REFINEMENTS
- Extract "Card Name" aspect distributions
- Take top N by matchCount (popular ones)
- Insert as SearchQuery rows (JP only by default; EN+JP already tracked elsewhere)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.api.ebay_auth import ebay_auth
from app.config import settings
from app.database import SessionLocal
from app.models import SearchQuery

logger = logging.getLogger(__name__)


POKEMON_CATEGORY_ID = "183454"


@dataclass(frozen=True)
class Bucket:
    key: str
    label: str
    # query keywords used for discovery
    q: str
    # optional extra aspect filters for refinement
    extra_aspects: list[str]
    # query_text template for persisted SearchQuery rows
    query_text_suffix: str
    language: str = "JP"


BUCKETS: list[Bucket] = [
    Bucket(
        key="hidden_fates_shiny_vault",
        label="Hidden Fates Shiny Vault",
        q="pokemon hidden fates shiny vault",
        language="EN",
        extra_aspects=[],
        query_text_suffix="hidden fates shiny vault",
    ),
    Bucket(
        key="ultra_shiny_gx",
        label="Ultra Shiny GX (SM8b)",
        q="pokemon ultra shiny gx sm8b",
        language="JP",
        extra_aspects=[],
        query_text_suffix="ultra shiny gx",
    ),
    Bucket(
        key="tag_team_gx",
        label="TAG TEAM GX",
        q="pokemon tag team gx",
        language="JP",
        extra_aspects=[],
        query_text_suffix="tag team gx",
    ),
    Bucket(
        key="amazing_rare",
        label="Amazing Rare",
        q="pokemon amazing rare",
        language="JP",
        extra_aspects=[],
        query_text_suffix="amazing rare",
    ),
    Bucket(
        key="skyridge_split_earth_holos",
        label="Skyridge / Split Earth holos",
        q="pokemon skyridge split earth holo",
        language="JP",
        extra_aspects=[],
        query_text_suffix="skyridge split earth holo",
    ),
]


def _aspect_distributions(refinement: dict) -> list[dict]:
    return refinement.get("aspectDistributions") or []


def _find_aspect(dist: list[dict], name: str) -> Optional[dict]:
    for a in dist:
        n = a.get("localizedAspectName") or a.get("aspectName")
        if n == name:
            return a
    return None


def _top_values(aspect: dict, limit: int) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for v in (aspect.get("aspectValueDistributions") or []):
        name = v.get("localizedAspectValue") or v.get("aspectValue")
        cnt = int(v.get("matchCount") or 0)
        if name:
            out.append((name, cnt))
    out.sort(key=lambda t: t[1], reverse=True)
    return out[:limit]


async def fetch_refinements(
    *,
    q: str,
    language: str,
    extra_aspects: list[str],
) -> dict[str, Any]:
    token = await ebay_auth.get_client_credentials_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_AU",
        "Content-Type": "application/json",
    }

    language_value = "Japanese" if (language or "JP").upper() == "JP" else "English"

    aspect_parts = [
        f"categoryId:{POKEMON_CATEGORY_ID}",
        f"Language:{{{language_value}}}",
    ]
    if settings.require_psa10_graded:
        aspect_parts.append("Graded:{Yes}")
        aspect_parts.append("Grade:{10}")
    if settings.require_professional_grader_psa:
        aspect_parts.append("Professional Grader:{Professional Sports Authenticator (PSA)}")

    for a in extra_aspects:
        aspect_parts.append(a)

    params = {
        "q": q,
        "category_ids": POKEMON_CATEGORY_ID,
        "filter": "buyingOptions:{FIXED_PRICE}",
        "aspect_filter": ",".join(aspect_parts),
        "fieldgroups": "ASPECT_REFINEMENTS",
        "limit": 50,
        "offset": 0,
    }

    url = f"{settings.ebay_api_base_url}/buy/browse/v1/item_summary/search"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params, timeout=30.0)
        resp.raise_for_status()
        return resp.json()


def upsert_queries(
    *,
    language: str,
    bucket: Bucket,
    card_names: list[str],
) -> tuple[int, int]:
    """
    Returns: (created_count, existing_count)
    """
    db = SessionLocal()
    created = 0
    existing = 0
    try:
        for card in card_names:
            query_text = f"{card} {bucket.query_text_suffix}".strip().lower()
            card_name = f"{card} — {bucket.label}"

            exists = (
                db.query(SearchQuery)
                .filter(SearchQuery.query_text == query_text)
                .filter(SearchQuery.language == language)
                .first()
            )
            if exists:
                existing += 1
                continue

            db.add(
                SearchQuery(
                    query_text=query_text,
                    card_name=card_name,
                    language=language,
                    is_active=True,
                )
            )
            created += 1

        db.commit()
        return created, existing
    finally:
        db.close()


async def main():
    logging.basicConfig(level=logging.INFO)
    top_n = 25

    total_created = 0
    for bucket in BUCKETS:
        logger.info("Expanding bucket: %s", bucket.label)
        language = bucket.language

        # Special handling: "Skyridge / Split Earth" is mixed EN/JP naming on eBay.
        if bucket.key == "skyridge_split_earth_holos":
            data_en = await fetch_refinements(
                q="pokemon skyridge holo",
                language="EN",
                extra_aspects=[],
            )
            data_jp = await fetch_refinements(
                q="pokemon split earth holo",
                language="JP",
                extra_aspects=[],
            )

            def extract_top(d: dict[str, Any]) -> list[tuple[str, int]]:
                ref = d.get("refinement") or {}
                dist = _aspect_distributions(ref)
                cn = _find_aspect(dist, "Card Name")
                if not cn:
                    return []
                return _top_values(cn, 200)

            merged: dict[str, int] = {}
            for name, cnt in extract_top(data_en) + extract_top(data_jp):
                merged[name] = max(merged.get(name, 0), cnt)

            merged_sorted = sorted(merged.items(), key=lambda t: t[1], reverse=True)[:top_n]
            names = [n for (n, _) in merged_sorted]
            created, already = upsert_queries(language="JP", bucket=bucket, card_names=names)
            total_created += created
            logger.info("Bucket %s: created=%s existing=%s", bucket.key, created, already)
            continue

        data = await fetch_refinements(q=bucket.q, language=language, extra_aspects=bucket.extra_aspects)
        refinement = data.get("refinement") or {}
        dists = _aspect_distributions(refinement)

        # If Rarity has "Amazing Rare" for the Amazing Rare bucket, constrain it for better precision.
        if bucket.key == "amazing_rare":
            rarity = _find_aspect(dists, "Rarity")
            if rarity:
                rar_vals = [n for (n, _) in _top_values(rarity, 200)]
                if "Amazing Rare" in rar_vals and "Rarity:{Amazing Rare}" not in bucket.extra_aspects:
                    logger.info("Refining Amazing Rare bucket using Rarity:{Amazing Rare}")
                    data = await fetch_refinements(
                        q=bucket.q, language=language, extra_aspects=["Rarity:{Amazing Rare}"]
                    )
                    refinement = data.get("refinement") or {}
                    dists = _aspect_distributions(refinement)

        # If Speciality has "TAG TEAM" signals, constrain it for the Tag Team bucket.
        if bucket.key == "tag_team_gx":
            spec = _find_aspect(dists, "Speciality")
            if spec:
                spec_vals = [n for (n, _) in _top_values(spec, 200)]
                # values vary, accept any that contains TAG TEAM
                tag_vals = [v for v in spec_vals if "TAG TEAM" in v.upper()]
                if tag_vals:
                    chosen = tag_vals[0]
                    logger.info("Refining TAG TEAM bucket using Speciality:{%s}", chosen)
                    data = await fetch_refinements(
                        q=bucket.q, language=language, extra_aspects=[f"Speciality:{{{chosen}}}"]
                    )
                    refinement = data.get("refinement") or {}
                    dists = _aspect_distributions(refinement)

        card_name_aspect = _find_aspect(dists, "Card Name")
        if not card_name_aspect:
            # Fallback: if Set has a value that matches the bucket keywords, apply it and retry.
            set_aspect = _find_aspect(dists, "Set")
            if set_aspect:
                set_vals = [n for (n, _) in _top_values(set_aspect, 200)]
                wanted = None
                for v in set_vals:
                    if bucket.key == "hidden_fates_shiny_vault" and "HIDDEN FATES" in v.upper():
                        wanted = v
                        break
                if wanted:
                    logger.info("Retrying %s with Set:{%s}", bucket.key, wanted)
                    data = await fetch_refinements(
                        q=bucket.q, language=language, extra_aspects=[f"Set:{{{wanted}}}"]
                    )
                    refinement = data.get("refinement") or {}
                    dists = _aspect_distributions(refinement)
                    card_name_aspect = _find_aspect(dists, "Card Name")

        if not card_name_aspect:
            logger.warning("No 'Card Name' aspect found for bucket %s; skipping", bucket.label)
            continue

        top = _top_values(card_name_aspect, top_n)
        names = [n for (n, _) in top]
        # We store bucket expansions as JP queries by default, except Hidden Fates which is EN.
        store_lang = "EN" if bucket.key == "hidden_fates_shiny_vault" else "JP"
        created, already = upsert_queries(language=store_lang, bucket=bucket, card_names=names)
        total_created += created
        logger.info("Bucket %s: created=%s existing=%s", bucket.key, created, already)

    logger.info("Done. Total created=%s", total_created)


if __name__ == "__main__":
    asyncio.run(main())

