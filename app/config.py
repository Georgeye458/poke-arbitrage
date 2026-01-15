"""Application configuration settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str = "postgresql://localhost:5432/pokearbitrage"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # eBay API Credentials
    ebay_app_id: str = ""
    ebay_cert_id: str = ""
    ebay_dev_id: str = ""
    ebay_redirect_uri: str = ""
    ebay_refresh_token: str = ""
    # Windows/CLI-safe variant: store token with '^' encoded as '%5E'
    ebay_refresh_token_urlenc: str = ""

    # Destination context for shipping estimates (do not store full address)
    destination_country: str = "AU"
    destination_postcode: str = "2176"

    # Browse filters
    require_psa10_graded: bool = True
    require_professional_grader_psa: bool = True
    
    # eBay API Endpoints
    ebay_api_base_url: str = "https://api.ebay.com"
    ebay_auth_url: str = "https://api.ebay.com/identity/v1/oauth2/token"
    
    # Environment
    environment: str = "development"
    
    # Price ceiling for arbitrage (AUD)
    price_ceiling_aud: float = 3000.0

    # Price floor for cards-in-scope (AUD). Benchmarks below this are ignored.
    price_floor_aud: float = 30.0
    
    # Arbitrage threshold (15% discount = 0.85)
    arbitrage_threshold: float = 0.85
    
    # Task scheduling interval (seconds)
    task_interval_seconds: int = 1800  # 30 minutes
    scheduler_enabled: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
