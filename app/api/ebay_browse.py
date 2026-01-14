"""eBay Browse API client for fetching active listings."""

import logging
from decimal import Decimal
from typing import Optional
from datetime import datetime

import httpx

from app.config import settings
from app.api.ebay_auth import ebay_auth

logger = logging.getLogger(__name__)


class EbayBrowseAPI:
    """Client for eBay Browse API to fetch active Buy It Now listings."""
    
    BASE_URL = f"{settings.ebay_api_base_url}/buy/browse/v1"
    
    # Pokemon Trading Cards category ID
    POKEMON_CATEGORY_ID = "183454"
    
    async def search_psa10_listings(
        self,
        query: str,
        language: str = "EN",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Search for PSA 10 Pokemon card listings.
        
        Args:
            query: Search query (e.g., "psa 10 charizard base set")
            limit: Maximum results to return (max 200)
            offset: Pagination offset
            
        Returns:
            Dict containing listing results
        """
        access_token = await ebay_auth.get_client_credentials_token()
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_AU",  # Australian marketplace
            "Content-Type": "application/json",
        }

        # Provide buyer location context for shipping estimates (postcode only).
        if settings.destination_country and settings.destination_postcode:
            headers["X-EBAY-C-ENDUSERCTX"] = (
                f"contextualLocation=country={settings.destination_country},zip={settings.destination_postcode}"
            )
        
        # Build search parameters
        language_value = "English" if (language or "EN").upper() == "EN" else "Japanese"

        aspect_parts = [
            f"categoryId:{self.POKEMON_CATEGORY_ID}",
            f"Language:{{{language_value}}}",
        ]

        # Prefer structured filters (aspects) over title parsing.
        # Verified via fieldgroups=ASPECT_REFINEMENTS that these exist for 183454.
        if settings.require_psa10_graded:
            aspect_parts.append("Graded:{Yes}")
            aspect_parts.append("Grade:{10}")
        if settings.require_professional_grader_psa:
            aspect_parts.append("Professional Grader:{Professional Sports Authenticator (PSA)}")

        params = {
            "q": f"psa 10 {query}",
            "category_ids": self.POKEMON_CATEGORY_ID,
            # PSA graded cards are often "USED" – do not constrain condition.
            "filter": "buyingOptions:{FIXED_PRICE}",
            # Best practice: use aspect_filter to separate EN vs JP
            # (Aspect names/values vary by category, but Language is common for cards.)
            "aspect_filter": ",".join(aspect_parts),
            "sort": "price",
            "limit": min(limit, 200),
            "offset": offset,
        }
        
        url = f"{self.BASE_URL}/item_summary/search"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=headers,
                params=params,
                timeout=30.0,
            )
            
            if response.status_code != 200:
                logger.error(f"Browse API error: {response.status_code} - {response.text}")
                raise Exception(f"Browse API request failed: {response.text}")
            
            return response.json()
    
    def parse_listings(self, api_response: dict) -> list[dict]:
        """
        Parse Browse API response into structured listing data.
        
        Args:
            api_response: Raw API response
            
        Returns:
            List of parsed listing dictionaries
        """
        listings = []
        items = api_response.get("itemSummaries", [])
        
        for item in items:
            try:
                listing = self._parse_single_listing(item)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"Failed to parse listing {item.get('itemId')}: {e}")
                continue
        
        return listings
    
    def _parse_single_listing(self, item: dict) -> Optional[dict]:
        """Parse a single listing item."""
        price_info = item.get("price", {})
        converted_price = item.get("itemAffiliateWebUrl") or item.get("itemWebUrl", "")
        
        # Get price in AUD (or convert if needed)
        price_value = price_info.get("value")
        price_currency = price_info.get("currency", "AUD")
        
        if not price_value:
            return None
        
        # Convert to Decimal
        try:
            price_aud = Decimal(str(price_value))
        except (ValueError, TypeError):
            return None
        
        # Get seller info
        seller = item.get("seller", {})
        
        # Shipping cost (best-effort)
        shipping_cost_aud = None
        shipping_options = item.get("shippingOptions") or []
        if isinstance(shipping_options, list) and shipping_options:
            ship_cost = (shipping_options[0] or {}).get("shippingCost") or {}
            try:
                ship_val = ship_cost.get("value")
                ship_cur = (ship_cost.get("currency") or "AUD").upper()
                if ship_val is not None:
                    # With EBAY_AU marketplace + enduserctx, this is typically AUD.
                    shipping_cost_aud = Decimal(str(ship_val))
                    # If currency isn't AUD, we still store the numeric (treated as AUD best-effort).
                    if ship_cur != "AUD":
                        logger.debug(f"Non-AUD shipping currency={ship_cur} for item {item.get('itemId')}")
            except Exception:
                shipping_cost_aud = None

        # Get image
        image = item.get("image", {})
        thumbnail = item.get("thumbnailImages", [{}])[0] if item.get("thumbnailImages") else {}
        
        return {
            "ebay_item_id": item.get("itemId"),
            "title": item.get("title", ""),
            "price_aud": price_aud,
            "original_currency": price_currency,
            "original_price": Decimal(str(price_value)),
            "shipping_cost_aud": shipping_cost_aud,
            "seller_username": seller.get("username"),
            "seller_feedback_score": seller.get("feedbackScore"),
            "item_url": item.get("itemWebUrl", ""),
            "image_url": image.get("imageUrl") or thumbnail.get("imageUrl"),
            "listing_date": self._parse_date(item.get("itemCreationDate")),
        }
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO date string to datetime."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None


# Global client instance
ebay_browse = EbayBrowseAPI()
