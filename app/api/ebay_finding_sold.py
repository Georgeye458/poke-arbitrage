"""eBay Finding API client for sold/completed item comps.

Uses `findCompletedItems` to approximate sold market prices.
Docs: https://developer.ebay.com/devzone/finding/callref/findCompletedItems.html
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_FX_CACHE: dict[tuple[str, str], tuple[float, float]] = {}
_FX_TTL_SECONDS = 60 * 60 * 12  # 12 hours


def _fx_rate(base: str, quote: str) -> Optional[float]:
    base = (base or "").upper()
    quote = (quote or "").upper()
    if not base or not quote or base == quote:
        return 1.0

    key = (base, quote)
    now = time.time()
    cached = _FX_CACHE.get(key)
    if cached and (now - cached[0]) < _FX_TTL_SECONDS:
        return cached[1]

    try:
        resp = httpx.get(
            "https://api.exchangerate.host/latest",
            params={"base": base, "symbols": quote},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"][quote])
        _FX_CACHE[key] = (now, rate)
        return rate
    except Exception as e:
        logger.warning(f"FX conversion failed {base}->{quote}: {e}")
        return None


@dataclass(frozen=True)
class SoldComp:
    title: str
    price_aud: Decimal
    currency: str


class EbayFindingSoldAPI:
    """Client for fetching sold comps using the Finding API."""

    BASE_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
    POKEMON_CATEGORY_ID = "183454"

    async def find_completed_items(
        self,
        query: str,
        language: str = "EN",
        max_results: int = 50,
    ) -> list[SoldComp]:
        if not settings.ebay_app_id:
            raise RuntimeError("EBAY_APP_ID must be set for Finding API sold comps")

        language = (language or "EN").upper()
        keywords = f"pokemon psa 10 {query}"
        if language == "JP":
            keywords = f"{keywords} japanese"

        # Finding API uses name/value itemFilter + nested response arrays.
        params: dict[str, Any] = {
            "OPERATION-NAME": "findCompletedItems",
            "SERVICE-VERSION": "1.13.0",
            "SECURITY-APPNAME": settings.ebay_app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "",
            "categoryId": self.POKEMON_CATEGORY_ID,
            "keywords": keywords,
            "paginationInput.entriesPerPage": min(int(max_results), 100),
            "paginationInput.pageNumber": 1,
            "itemFilter(0).name": "SoldItemsOnly",
            "itemFilter(0).value": "true",
            # Keep it broad: include auctions + BIN. (Sold comps are what we want.)
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(self.BASE_URL, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()

        items = (
            (data.get("findCompletedItemsResponse") or [{}])[0]
            .get("searchResult", [{}])[0]
            .get("item", [])
        )
        if isinstance(items, dict):
            items = [items]

        comps: list[SoldComp] = []
        for item in items or []:
            comp = self._parse_item(item)
            if comp is not None:
                comps.append(comp)

        return comps

    def _parse_item(self, item: dict[str, Any]) -> Optional[SoldComp]:
        title = (item.get("title") or [""])[0] if isinstance(item.get("title"), list) else (item.get("title") or "")
        title = str(title or "").strip()
        if not title:
            return None

        # Prefer convertedCurrentPrice when present.
        selling_status = item.get("sellingStatus") or []
        if isinstance(selling_status, dict):
            selling_status = [selling_status]
        selling_status = selling_status[0] if selling_status else {}

        price_node = selling_status.get("convertedCurrentPrice") or selling_status.get("currentPrice") or {}
        if isinstance(price_node, list):
            price_node = price_node[0] if price_node else {}

        value = price_node.get("__value__") if isinstance(price_node, dict) else None
        currency = price_node.get("@currencyId") if isinstance(price_node, dict) else None

        if value is None:
            return None

        try:
            amount = Decimal(str(value))
        except Exception:
            return None

        cur = (str(currency) if currency else "AUD").upper()
        if cur != "AUD":
            rate = _fx_rate(cur, "AUD")
            if rate is not None:
                amount = Decimal(str(float(amount) * rate))
            else:
                logger.warning(f"Using unconverted sold amount={amount} currency={cur} (FX unavailable)")

        # Round-ish via quantize in DB layer; keep as Decimal here.
        return SoldComp(title=title, price_aud=amount, currency=cur)


ebay_finding_sold = EbayFindingSoldAPI()

