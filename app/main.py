"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, Base
from app.routes.opportunities import router as opportunities_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting PokeArbitrage Scanner...")
    logger.info(f"Environment: {settings.environment}")
    
    # Create tables (for development; use Alembic migrations in production)
    if settings.environment == "development":
        Base.metadata.create_all(bind=engine)
        # Search queries are now dynamically created from Cherry listings
    
    yield
    
    # Shutdown
    logger.info("Shutting down PokeArbitrage Scanner...")


# Create FastAPI app
app = FastAPI(
    title="PokeArbitrage Scanner",
    description="Identifies undervalued PSA 10 Pokemon cards on eBay",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routes
app.include_router(opportunities_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": "PokeArbitrage Scanner",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "price_ceiling_aud": settings.price_ceiling_aud,
        "arbitrage_threshold": settings.arbitrage_threshold,
    }


@app.get("/privacy")
async def privacy_policy():
    """Privacy policy page."""
    return {
        "title": "Privacy Policy",
        "app": "PokeArbitrage Scanner",
        "policy": "This application collects no personal data. It only accesses publicly available eBay listing information to identify arbitrage opportunities for PSA 10 Pokemon cards.",
        "contact": "For questions, contact the app administrator.",
    }


@app.get("/auth/callback")
async def auth_callback(code: str = None):
    """OAuth callback endpoint for eBay authentication."""
    return {
        "status": "success",
        "message": "Authentication callback received",
        "code": code,
    }


@app.get("/auth/accepted")
async def auth_accepted():
    """OAuth accepted endpoint."""
    return {"status": "accepted", "message": "eBay authorization was accepted."}


@app.get("/auth/declined")
async def auth_declined():
    """OAuth declined endpoint."""
    return {"status": "declined", "message": "eBay authorization was declined."}
