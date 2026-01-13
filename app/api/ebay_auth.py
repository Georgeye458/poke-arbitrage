"""eBay OAuth authentication handler."""

import base64
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EbayAuth:
    """Handles eBay OAuth2 authentication and token management."""
    
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        
    @property
    def _auth_header(self) -> str:
        """Generate Base64 encoded authorization header."""
        credentials = f"{settings.ebay_app_id}:{settings.ebay_cert_id}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    async def get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        if self._is_token_valid():
            return self._access_token
        
        return await self._refresh_token()
    
    def _is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._access_token or not self._token_expiry:
            return False
        # Refresh 5 minutes before expiry
        return datetime.utcnow() < (self._token_expiry - timedelta(minutes=5))
    
    async def _refresh_token(self) -> str:
        """Refresh the OAuth access token using refresh token."""
        logger.info("Refreshing eBay OAuth access token...")
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": self._auth_header,
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": settings.ebay_refresh_token,
            "scope": "https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/buy.browse",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.ebay_auth_url,
                headers=headers,
                data=data,
                timeout=30.0,
            )
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                raise Exception(f"Failed to refresh eBay token: {response.text}")
            
            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 7200)
            self._token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            
            logger.info(f"Token refreshed successfully, expires in {expires_in}s")
            return self._access_token
    
    async def get_client_credentials_token(self) -> str:
        """Get an application access token using client credentials grant.
        
        This is used for APIs that don't require user consent (like Browse API).
        """
        logger.info("Getting eBay client credentials token...")
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": self._auth_header,
        }
        
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.ebay_auth_url,
                headers=headers,
                data=data,
                timeout=30.0,
            )
            
            if response.status_code != 200:
                logger.error(f"Client credentials token failed: {response.status_code} - {response.text}")
                raise Exception(f"Failed to get eBay client token: {response.text}")
            
            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 7200)
            self._token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            
            logger.info(f"Client token obtained, expires in {expires_in}s")
            return self._access_token


# Global auth instance
ebay_auth = EbayAuth()
