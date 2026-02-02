"""Opportunities routes for viewing arbitrage opportunities."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CherryOpportunity
from app.config import settings
from app.tasks.fetch_cherry_listings import fetch_cherry_listings
from app.tasks.fetch_sold_benchmarks import fetch_sold_benchmarks
from app.tasks.identify_cherry_opportunities import identify_cherry_opportunities
from app.tasks.celery_app import celery_app

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
    query = db.query(CherryOpportunity)
    
    if active_only:
        query = query.filter(CherryOpportunity.is_active == True)
    
    # Apply sorting
    if sort == "discount":
        query = query.order_by(CherryOpportunity.discount_percentage.desc())
    elif sort == "profit":
        query = query.order_by(CherryOpportunity.potential_profit.desc())
    elif sort == "price":
        query = query.order_by(CherryOpportunity.store_price.asc())
    else:
        query = query.order_by(CherryOpportunity.discovered_at.desc())
    
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
            "cherry_base_url": settings.cherry_base_url,
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
    query = db.query(CherryOpportunity)
    
    if active_only:
        query = query.filter(CherryOpportunity.is_active == True)
    
    if sort == "discount":
        query = query.order_by(CherryOpportunity.discount_percentage.desc())
    elif sort == "profit":
        query = query.order_by(CherryOpportunity.potential_profit.desc())
    elif sort == "price":
        query = query.order_by(CherryOpportunity.store_price.asc())
    else:
        query = query.order_by(CherryOpportunity.discovered_at.desc())
    
    opportunities = query.limit(limit).all()
    
    return {
        "count": len(opportunities),
        "opportunities": [
            {
                "id": opp.id,
                "card_name": opp.card_name,
                "product_title": opp.product_title,
                "store_price": float(opp.store_price),
                "market_price": float(opp.market_price),
                "discount_percentage": float(opp.discount_percentage),
                "potential_profit": float(opp.potential_profit),
                "product_url": opp.product_url,
                "image_url": opp.image_url,
                "in_stock": opp.in_stock,
                "discovered_at": opp.discovered_at.isoformat(),
                "is_active": opp.is_active,
            }
            for opp in opportunities
        ],
    }


class RunScanRequest(BaseModel):
    # UI-friendly: minimum discount percent (0..50). Example: 10 means "at least 10% off".
    min_discount_pct: float | None = Field(default=None, ge=0.0, le=50.0)
    # Backward compat: threshold multiplier. 0.85 means "15% off".
    arbitrage_threshold: float | None = Field(default=None, ge=0.5, le=1.0)
    # Optional: only consider in-stock Cherry items (default true via settings)
    in_stock_only: bool | None = Field(default=None)
    # Backward-compat from prior UI; ignored in Cherry-vs-sold pipeline
    listing_mode: str | None = Field(default=None)


@router.post("/api/run-scan")
async def run_scan_now(payload: RunScanRequest | None = None):
    """Trigger a manual scan run (Cherry listings -> sold benchmarks -> score)."""
    threshold = payload.arbitrage_threshold if payload else None
    if payload and payload.min_discount_pct is not None:
        # Convert min discount (%) -> multiplier threshold.
        threshold = 1.0 - (float(payload.min_discount_pct) / 100.0)

    # Allow per-run override of in-stock requirement (defaults to settings).
    if payload and payload.in_stock_only is not None:
        # NOTE: settings are read at import time; for per-run toggles we'd pass through kwargs.
        # For now, this is informational; the backend uses settings.cherry_require_in_stock.
        pass

    # Run sequentially via countdowns (simple + reliable)
    scrape = fetch_cherry_listings.apply_async()
    benchmarks = fetch_sold_benchmarks.apply_async(countdown=90)
    score = identify_cherry_opportunities.apply_async(
        kwargs={"arbitrage_threshold": threshold},
        countdown=180,
    )

    return {
        "status": "queued",
        "queued_at": datetime.utcnow().isoformat(),
        "arbitrage_threshold": threshold,
        "tasks": {
            "fetch_cherry_listings": scrape.id,
            "fetch_sold_benchmarks": benchmarks.id,
            "identify_cherry_opportunities": score.id,
        },
    }


@router.get("/api/task-status/{task_id}")
async def task_status(task_id: str):
    """Poll a celery task state (used by the frontend to show scan completion)."""
    res = celery_app.AsyncResult(task_id)
    payload = {"task_id": task_id, "state": res.state, "ready": res.ready()}
    if res.ready():
        # result can be Exception-like; keep it JSON-safe best-effort
        try:
            payload["result"] = res.result
        except Exception:
            payload["result"] = None
    return payload
