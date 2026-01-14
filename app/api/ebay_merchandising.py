"""eBay Merchandising API client for market benchmark pricing."""

import logging
from decimal import Decimal
from typing import Optional

import httpx

from app.config import settings
from app.api.ebay_auth import ebay_auth

logger = logging.getLogger(__name__)


class EbayMerchandisingAPI:
    """Client for eBay Merchandising API to fetch market benchmark prices."""
    
    # Note: Merchandising API uses a different base URL
    BASE_URL = "https://svcs.ebay.com/MerchandisingService"
    
    # Pokemon Trading Cards category ID
    POKEMON_CATEGORY_ID = "183454"
    
    async def get_most_watched_items(
        self,
        query: str,
        max_results: int = 5,
    ) -> dict:
        """
        Get most watched items for a search query.
        
        This provides market benchmark data based on popular/watched items.
        
        Args:
            query: Search query (e.g., "psa 10 charizard base set")
            max_results: Maximum items to return (default 5)
            
        Returns:
            Dict containing watched item results
        """
        # Merchandising API uses Application ID directly in params
        params = {
            "OPERATION-NAME": "getMostWatchedItems",
            "SERVICE-VERSION": "1.1.0",
            "CONSUMER-ID": settings.ebay_app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "",
            # Prefer AU site/currency conversions (helps keep benchmark in AUD)
            # Note: response items can still be global, but prices are converted.
            "GLOBAL-ID": "EBAY-AU",
            "categoryId": self.POKEMON_CATEGORY_ID,
            "maxResults": max_results,
            # Add "pokemon" to reduce cross-TCG noise (e.g., Yu-Gi-Oh)
            "keywords": f"pokemon psa 10 {query}",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.BASE_URL,
                params=params,
                timeout=30.0,
            )
            
            if response.status_code != 200:
                logger.error(f"Merchandising API error: {response.status_code} - {response.text}")
                raise Exception(f"Merchandising API request failed: {response.text}")
            
            return response.json()
    
    def calculate_market_benchmark(
        self,
        api_response: dict,
        price_ceiling: float = None,
    ) -> Optional[dict]:
        """
        Calculate market benchmark from Merchandising API response.
        
        CRITICAL: Applies the $3,000 AUD price ceiling filter.
        
        Args:
            api_response: Raw API response
            price_ceiling: Maximum allowed price (default from settings)
            
        Returns:
            Dict with market benchmark data, or None if above price ceiling
        """
        if price_ceiling is None:
            price_ceiling = settings.price_ceiling_aud
        
        # Parse items from response
        items = self._extract_items(api_response)
        
        if not items:
            logger.warning("No items found in Merchandising API response")
            return None

        # Filter to PSA 10-ish items (Merchandising results can be noisy)
        psa_items = []
        for item in items:
            title = (item.get("title") or "").upper()
            if "PSA 10" in title or "PSA10" in title:
                psa_items.append(item)

        # If we have any PSA-filtered items, only use those
        if psa_items:
            items = psa_items
        
        # Extract prices
        prices = []
        for item in items:
            price = self._extract_price(item)
            if price is not None:
                prices.append(price)
        
        if not prices:
            logger.warning("No valid prices found in items")
            return None
        
        # Calculate average market price
        avg_price = sum(prices) / len(prices)
        
        # CRITICAL FILTER: Check against price ceiling
        if avg_price >= price_ceiling:
            logger.info(
                f"Card filtered out: avg price ${avg_price:.2f} >= ceiling ${price_ceiling:.2f}"
            )
            return None
        
        return {
            "market_price": Decimal(str(round(avg_price, 2))),
            "sample_size": len(prices),
            "min_price": Decimal(str(round(min(prices), 2))),
            "max_price": Decimal(str(round(max(prices), 2))),
            "data_source": "ebay_merchandising_api",
        }
    
    def _extract_items(self, api_response: dict) -> list:
        """Extract item list from API response."""
        try:
            # Navigate the nested response structure
            result = api_response.get("getMostWatchedItemsResponse", {})
            item_recommendations = result.get("itemRecommendations", {})
            items = item_recommendations.get("item", [])
            
            # Ensure it's a list
            if isinstance(items, dict):
                items = [items]
            
            return items
        except Exception as e:
            logger.error(f"Failed to extract items: {e}")
            return []
    
    def _extract_price(self, item: dict) -> Optional[float]:
        """Extract price from a single item."""
        try:
            # Get current price
            buy_it_now = item.get("buyItNowPrice", {})
            current_price = item.get("currentPrice", {})
            
            # Prefer Buy It Now price
            price_data = buy_it_now if buy_it_now else current_price
            
            if not price_data:
                return None
            
            # Handle different response formats
            if isinstance(price_data, dict):
                value = price_data.get("__value__") or price_data.get("value")
                currency = price_data.get("@currencyId") or price_data.get("currency")
            else:
                value = price_data
                currency = None
            
            if value:
                # If currency is present and not AUD, skip to avoid mixing currencies.
                if currency and str(currency).upper() != "AUD":
                    return None
                return float(value)
            
            return None
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to extract price: {e}")
            return None


# Global client instance
ebay_merchandising = EbayMerchandisingAPI()
