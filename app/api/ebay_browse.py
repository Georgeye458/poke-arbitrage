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
        
        # Build search parameters
        params = {
            "q": f"psa 10 {query}",
            "category_ids": self.POKEMON_CATEGORY_ID,
            "filter": "conditions:{NEW},buyingOptions:{FIXED_PRICE}",
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
        
        # Get image
        image = item.get("image", {})
        thumbnail = item.get("thumbnailImages", [{}])[0] if item.get("thumbnailImages") else {}
        
        return {
            "ebay_item_id": item.get("itemId"),
            "title": item.get("title", ""),
            "price_aud": price_aud,
            "original_currency": price_currency,
            "original_price": Decimal(str(price_value)),
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
