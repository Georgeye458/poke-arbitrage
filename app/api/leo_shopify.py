"""Leo Games (Shopify) product feed client.

Leo Games is a Shopify store and exposes public JSON endpoints such as:
- /products.json
- /collections/<collection-handle>/products.json

Supports both PSA and CGC graded cards.
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
class LeoProduct:
    product_id: int
    variant_id: int
    title: str
    handle: str
    product_url: str
    image_url: Optional[str]
    price_aud: Decimal
    in_stock: bool
    tags: list[str]
    grader: str  # "PSA" or "CGC"
    grade: int   # e.g., 10


class LeoShopifyClient:
    """Fetches Leo Games products via Shopify public JSON endpoints."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.leo_base_url).rstrip("/") + "/"

    async def fetch_collection_products(
        self,
        collection_handle: str,
        page: int = 1,
        limit: int = 250,
    ) -> list[LeoProduct]:
        """Fetch one page of products from a Shopify collection."""
        url = urljoin(self.base_url, f"collections/{collection_handle}/products.json")
        params = {"limit": min(int(limit), 250), "page": int(page)}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()

        products = data.get("products") or []
        out: list[LeoProduct] = []
        for p in products:
            parsed = self._parse_product(p, collection_handle)
            if parsed:
                out.extend(parsed)
        return out

    def _parse_product(self, p: dict[str, Any], collection_handle: str) -> list[LeoProduct]:
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

        # Determine grader from collection handle or title
        grader, grade = self._detect_grading(title, tags, collection_handle)
        if not grader or grade is None:
            return []

        variants = p.get("variants") or []
        out: list[LeoProduct] = []
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
                LeoProduct(
                    product_id=int(product_id),
                    variant_id=int(variant_id),
                    title=title,
                    handle=handle,
                    product_url=product_url,
                    image_url=image_url,
                    price_aud=price_aud,
                    in_stock=available,
                    tags=tags,
                    grader=grader,
                    grade=grade,
                )
            )

        return out

    def _detect_grading(
        self, title: str, tags: list[str], collection_handle: str
    ) -> tuple[Optional[str], Optional[int]]:
        """Detect grader (PSA/CGC) and grade from title, tags, or collection."""
        t = (title or "").upper()
        
        # Check for PSA grades
        if "PSA 10" in t or "PSA10" in t:
            return "PSA", 10
        if "PSA 9" in t or "PSA9" in t:
            return "PSA", 9
        
        # Check for CGC grades
        if "CGC 10" in t or "CGC10" in t:
            return "CGC", 10
        if "CGC PRISTINE 10" in t:
            return "CGC", 10
        if "CGC 9.5" in t:
            return "CGC", 9  # Treat 9.5 as 9 for simplicity
        if "CGC 9" in t or "CGC9" in t:
            return "CGC", 9

        # Fallback: infer from collection handle
        collection_lower = (collection_handle or "").lower()
        if "psa" in collection_lower:
            # Try to extract grade from title patterns like "PSA 8"
            import re
            match = re.search(r"PSA\s*(\d+)", t)
            if match:
                return "PSA", int(match.group(1))
            return "PSA", None  # Unknown grade
        if "cgc" in collection_lower:
            import re
            match = re.search(r"CGC\s*(?:PRISTINE\s*)?(\d+(?:\.\d+)?)", t)
            if match:
                grade_str = match.group(1)
                grade = int(float(grade_str))  # Convert 9.5 -> 9, 10 -> 10
                return "CGC", grade
            return "CGC", None

        return None, None


leo_shopify = LeoShopifyClient()
