"""Opportunities routes for viewing arbitrage opportunities."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ArbitrageOpportunity

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
