"""Cherry Collectables (Shopify) product feed client.

Cherry is a Shopify store and exposes public JSON endpoints such as:
- /products.json
- /collections/<collection-handle>/products.json
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CherryProduct:
    product_id: int
    variant_id: int
    title: str
    handle: str
    product_url: str
    image_url: Optional[str]
    price_aud: Decimal
    in_stock: bool
    tags: list[str]


class CherryShopifyClient:
    """Fetches Cherry Collectables products via Shopify public JSON endpoints."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.cherry_base_url).rstrip("/") + "/"

    async def fetch_collection_products(
        self,
        collection_handle: str,
        page: int = 1,
        limit: int = 250,
    ) -> list[CherryProduct]:
        """Fetch one page of products from a Shopify collection."""
        url = urljoin(self.base_url, f"collections/{collection_handle}/products.json")
        params = {"limit": min(int(limit), 250), "page": int(page)}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()

        products = data.get("products") or []
        out: list[CherryProduct] = []
        for p in products:
            parsed = self._parse_product(p)
            if parsed:
                out.extend(parsed)
        return out

    async def search_suggest_products(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Use Shopify predictive search to get candidate products.

        Endpoint: /search/suggest.json?q=...&resources[type]=product&resources[limit]=N
        """
        url = urljoin(self.base_url, "search/suggest.json")
        params = {
            "q": query,
            "resources[type]": "product",
            "resources[limit]": min(int(limit), 10),
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            return (resp.json() or {}).get("resources", {}).get("results", {}).get("products", []) or []

    async def fetch_product_js(self, handle: str) -> dict[str, Any]:
        """Fetch a single product JSON via Shopify's /products/<handle>.js endpoint."""
        url = urljoin(self.base_url, f"products/{handle}.js")
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=30.0)
            resp.raise_for_status()
            return resp.json()

    def parse_product_js_variants(self, p: dict[str, Any]) -> list[CherryProduct]:
        """Parse /products/<handle>.js format into CherryProduct variants."""
        product_id = p.get("id")
        title = (p.get("title") or "").strip()
        handle = (p.get("handle") or "").strip()
        tags_raw = p.get("tags") or []
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        else:
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]

        if not product_id or not title or not handle:
            return []

        product_url = urljoin(self.base_url, f"products/{handle}")
        image_url = None
        featured = p.get("featured_image")
        if isinstance(featured, str) and featured:
            image_url = featured
        elif isinstance(featured, dict):
            image_url = featured.get("src") or featured.get("url")

        variants = p.get("variants") or []
        if isinstance(variants, dict):
            variants = [variants]
        if not isinstance(variants, list):
            return []

        out: list[CherryProduct] = []
        for v in variants:
            variant_id = v.get("id")
            price = v.get("price")
            available = bool(v.get("available"))
            if not variant_id or price is None:
                continue
            try:
                price_aud = Decimal(str(price))
            except Exception:
                continue

            out.append(
                CherryProduct(
                    product_id=int(product_id),
                    variant_id=int(variant_id),
                    title=title,
                    handle=handle,
                    product_url=product_url,
                    image_url=image_url,
                    price_aud=price_aud,
                    in_stock=available,
                    tags=tags,
                )
            )

        return out

    def _parse_product(self, p: dict[str, Any]) -> list[CherryProduct]:
        product_id = p.get("id")
        title = (p.get("title") or "").strip()
        handle = (p.get("handle") or "").strip()
        tags_raw = p.get("tags") or []
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        else:
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]

        if not product_id or not title or not handle:
            return []

        product_url = urljoin(self.base_url, f"products/{handle}")
        image_url = None
        images = p.get("images") or []
        if isinstance(images, list) and images:
            image_url = (images[0] or {}).get("src")

        variants = p.get("variants") or []
        out: list[CherryProduct] = []
        if not isinstance(variants, list):
            return []

        for v in variants:
            variant_id = v.get("id")
            price = v.get("price")
            available = bool(v.get("available"))
            if not variant_id or price is None:
                continue
            try:
                price_aud = Decimal(str(price))
            except Exception:
                continue

            out.append(
                CherryProduct(
                    product_id=int(product_id),
                    variant_id=int(variant_id),
                    title=title,
                    handle=handle,
                    product_url=product_url,
                    image_url=image_url,
                    price_aud=price_aud,
                    in_stock=available,
                    tags=tags,
                )
            )

        return out


cherry_shopify = CherryShopifyClient()

