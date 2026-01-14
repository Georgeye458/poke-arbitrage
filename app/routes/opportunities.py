"""Opportunities routes for viewing arbitrage opportunities."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ArbitrageOpportunity
from app.config import settings
from app.tasks.scrape_listings import scrape_all_listings
from app.tasks.fetch_benchmarks import fetch_all_benchmarks
from app.tasks.identify_opportunities import identify_all_opportunities

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/opportunities", response_class=HTMLResponse)
async def view_opportunities(
    request: Request,
    db: Session = Depends(get_db),
    sort: str = "discount",
    active_only: bool = True,
):
    """
    View arbitrage opportunities in HTML format.
    
    Args:
        sort: Sort by 'discount', 'profit', or 'price'
        active_only: Only show active opportunities
    """
    # Build query
    query = db.query(ArbitrageOpportunity)
    
    if active_only:
        query = query.filter(ArbitrageOpportunity.is_active == True)
    
    # Apply sorting
    if sort == "discount":
        query = query.order_by(ArbitrageOpportunity.discount_percentage.desc())
    elif sort == "profit":
        query = query.order_by(ArbitrageOpportunity.potential_profit.desc())
    elif sort == "price":
        query = query.order_by(ArbitrageOpportunity.listing_price.asc())
    else:
        query = query.order_by(ArbitrageOpportunity.discovered_at.desc())
    
    opportunities = query.limit(100).all()
    
    return templates.TemplateResponse(
        "opportunities.html",
        {
            "request": request,
            "opportunities": opportunities,
            "sort": sort,
            "active_only": active_only,
            "count": len(opportunities),
            "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "destination_postcode": settings.destination_postcode,
        },
    )


@router.get("/api/opportunities")
async def get_opportunities_json(
    db: Session = Depends(get_db),
    sort: str = "discount",
    active_only: bool = True,
    limit: int = 50,
):
    """
    Get arbitrage opportunities as JSON.
    
    Args:
        sort: Sort by 'discount', 'profit', or 'price'
        active_only: Only show active opportunities
        limit: Maximum results to return
    """
    query = db.query(ArbitrageOpportunity)
    
    if active_only:
        query = query.filter(ArbitrageOpportunity.is_active == True)
    
    if sort == "discount":
        query = query.order_by(ArbitrageOpportunity.discount_percentage.desc())
    elif sort == "profit":
        query = query.order_by(ArbitrageOpportunity.potential_profit.desc())
    elif sort == "price":
        query = query.order_by(ArbitrageOpportunity.listing_price.asc())
    else:
        query = query.order_by(ArbitrageOpportunity.discovered_at.desc())
    
    opportunities = query.limit(limit).all()
    
    return {
        "count": len(opportunities),
        "opportunities": [
            {
                "id": opp.id,
                "card_name": opp.card_name,
                "listing_title": opp.listing_title,
                "listing_price": float(opp.listing_price),
                "shipping_cost": float(opp.shipping_cost) if opp.shipping_cost is not None else None,
                "market_price": float(opp.market_price),
                "discount_percentage": float(opp.discount_percentage),
                "potential_profit": float(opp.potential_profit),
                "item_url": opp.item_url,
                "image_url": opp.image_url,
                "seller_username": opp.seller_username,
                "discovered_at": opp.discovered_at.isoformat(),
                "is_active": opp.is_active,
            }
            for opp in opportunities
        ],
    }


@router.post("/api/run-scan")
async def run_scan_now():
    """Trigger a manual scan run (scrape -> benchmarks -> score)."""
    # Run sequentially via countdowns (simple + reliable)
    scrape = scrape_all_listings.apply_async()
    benchmarks = fetch_all_benchmarks.apply_async(countdown=75)
    score = identify_all_opportunities.apply_async(countdown=180)

    return {
        "status": "queued",
        "queued_at": datetime.utcnow().isoformat(),
        "tasks": {
            "scrape_all_listings": scrape.id,
            "fetch_all_benchmarks": benchmarks.id,
            "identify_all_opportunities": score.id,
        },
    }
