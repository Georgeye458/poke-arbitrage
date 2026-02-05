"""Opportunities routes for viewing arbitrage opportunities."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import CherryOpportunity, CherryListing, LeoListing, SoldBenchmark, SearchQuery
from app.config import settings
from app.tasks.fetch_cherry_listings import fetch_cherry_listings
from app.tasks.fetch_leo_listings import fetch_leo_listings
from app.tasks.fetch_sold_benchmarks import fetch_sold_benchmarks
from app.tasks.identify_cherry_opportunities import identify_cherry_opportunities
from app.tasks.identify_leo_opportunities import identify_leo_opportunities
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
    # Use force_all=True to process all queries without rate limits
    scrape = fetch_cherry_listings.apply_async()
    benchmarks = fetch_sold_benchmarks.apply_async(kwargs={"force_all": True}, countdown=90)
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


def _get_latest_benchmark(db: Session, search_query_id: int, grader: str, grade: int) -> Optional[SoldBenchmark]:
    """Get the most recent benchmark for a specific query/grader/grade combination."""
    data_source = f"ebay_browse_{grader}_{grade}"
    return (
        db.query(SoldBenchmark)
        .filter(SoldBenchmark.search_query_id == search_query_id)
        .filter(SoldBenchmark.data_source == data_source)
        .order_by(SoldBenchmark.calculated_at.desc())
        .first()
    )


@router.get("/listings", response_class=HTMLResponse)
async def view_all_listings(
    request: Request,
    db: Session = Depends(get_db),
    sort: str = "discount",
    store: str = "all",
    in_stock_only: bool = True,
):
    """
    View ALL listings from both stores with their eBay market comparison.
    Shows all cards regardless of discount threshold.
    
    Args:
        sort: Sort by 'discount', 'price', 'market', or 'name'
        store: Filter by 'all', 'cherry', or 'leo'
        in_stock_only: Only show in-stock items
    """
    cutoff = datetime.utcnow() - timedelta(hours=48)
    listings_data = []
    
    # Get Cherry listings
    if store in ("all", "cherry"):
        cherry_query = (
            db.query(CherryListing)
            .filter(CherryListing.is_active == True)
            .filter(CherryListing.last_seen_at >= cutoff)
        )
        if in_stock_only:
            cherry_query = cherry_query.filter(CherryListing.in_stock == True)
        
        cherry_listings = cherry_query.all()
        
        for listing in cherry_listings:
            query = db.query(SearchQuery).filter(SearchQuery.id == listing.search_query_id).first()
            benchmark = _get_latest_benchmark(db, listing.search_query_id, listing.grader, listing.grade)
            
            store_price = Decimal(listing.price_aud)
            market_price = Decimal(benchmark.market_price) if benchmark else None
            
            if market_price and market_price > 0:
                discount_pct = ((market_price - store_price) / market_price) * Decimal("100")
                potential_profit = market_price - store_price
            else:
                discount_pct = None
                potential_profit = None
            
            listings_data.append({
                "id": listing.id,
                "store": "Cherry",
                "store_color": "#ff6b6b",
                "card_name": query.card_name if query else "Unknown",
                "product_title": listing.title,
                "grader": listing.grader,
                "grade": listing.grade,
                "store_price": float(store_price),
                "market_price": float(market_price) if market_price else None,
                "discount_percentage": float(discount_pct) if discount_pct is not None else None,
                "potential_profit": float(potential_profit) if potential_profit is not None else None,
                "product_url": listing.product_url,
                "image_url": listing.image_url,
                "in_stock": listing.in_stock,
                "benchmark_sample_size": benchmark.sample_size if benchmark else None,
                "benchmark_age_hours": int((datetime.utcnow() - benchmark.calculated_at).total_seconds() / 3600) if benchmark else None,
            })
    
    # Get Leo listings
    if store in ("all", "leo"):
        leo_query = (
            db.query(LeoListing)
            .filter(LeoListing.is_active == True)
            .filter(LeoListing.last_seen_at >= cutoff)
        )
        if in_stock_only:
            leo_query = leo_query.filter(LeoListing.in_stock == True)
        
        leo_listings = leo_query.all()
        
        for listing in leo_listings:
            query = db.query(SearchQuery).filter(SearchQuery.id == listing.search_query_id).first()
            benchmark = _get_latest_benchmark(db, listing.search_query_id, listing.grader, listing.grade)
            
            store_price = Decimal(listing.price_aud)
            market_price = Decimal(benchmark.market_price) if benchmark else None
            
            if market_price and market_price > 0:
                discount_pct = ((market_price - store_price) / market_price) * Decimal("100")
                potential_profit = market_price - store_price
            else:
                discount_pct = None
                potential_profit = None
            
            listings_data.append({
                "id": listing.id,
                "store": "Leo Games",
                "store_color": "#4ecdc4",
                "card_name": query.card_name if query else "Unknown",
                "product_title": listing.title,
                "grader": listing.grader,
                "grade": listing.grade,
                "store_price": float(store_price),
                "market_price": float(market_price) if market_price else None,
                "discount_percentage": float(discount_pct) if discount_pct is not None else None,
                "potential_profit": float(potential_profit) if potential_profit is not None else None,
                "product_url": listing.product_url,
                "image_url": listing.image_url,
                "in_stock": listing.in_stock,
                "benchmark_sample_size": benchmark.sample_size if benchmark else None,
                "benchmark_age_hours": int((datetime.utcnow() - benchmark.calculated_at).total_seconds() / 3600) if benchmark else None,
            })
    
    # Sort listings
    if sort == "discount":
        # Sort by discount descending, None values at end
        listings_data.sort(key=lambda x: (x["discount_percentage"] is None, -(x["discount_percentage"] or 0)))
    elif sort == "price":
        listings_data.sort(key=lambda x: x["store_price"])
    elif sort == "market":
        listings_data.sort(key=lambda x: (x["market_price"] is None, -(x["market_price"] or 0)))
    elif sort == "name":
        listings_data.sort(key=lambda x: x["card_name"].lower())
    
    # Calculate stats
    with_benchmark = [l for l in listings_data if l["market_price"] is not None]
    without_benchmark = [l for l in listings_data if l["market_price"] is None]
    underpriced = [l for l in with_benchmark if l["discount_percentage"] and l["discount_percentage"] > 0]
    overpriced = [l for l in with_benchmark if l["discount_percentage"] and l["discount_percentage"] < 0]
    
    stats = {
        "total": len(listings_data),
        "with_benchmark": len(with_benchmark),
        "without_benchmark": len(without_benchmark),
        "underpriced": len(underpriced),
        "overpriced": len(overpriced),
        "best_discount": max((l["discount_percentage"] for l in underpriced), default=0),
        "best_profit": max((l["potential_profit"] for l in underpriced), default=0),
    }
    
    return templates.TemplateResponse(
        "listings.html",
        {
            "request": request,
            "listings": listings_data,
            "stats": stats,
            "sort": sort,
            "store": store,
            "in_stock_only": in_stock_only,
            "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        },
    )


@router.get("/api/listings")
async def get_all_listings_json(
    db: Session = Depends(get_db),
    store: str = "all",
    in_stock_only: bool = True,
    limit: int = 100,
):
    """Get all listings with market comparisons as JSON."""
    # Reuse the logic from view_all_listings but return JSON
    cutoff = datetime.utcnow() - timedelta(hours=48)
    listings_data = []
    
    if store in ("all", "cherry"):
        cherry_query = (
            db.query(CherryListing)
            .filter(CherryListing.is_active == True)
            .filter(CherryListing.last_seen_at >= cutoff)
        )
        if in_stock_only:
            cherry_query = cherry_query.filter(CherryListing.in_stock == True)
        
        for listing in cherry_query.limit(limit).all():
            query = db.query(SearchQuery).filter(SearchQuery.id == listing.search_query_id).first()
            benchmark = _get_latest_benchmark(db, listing.search_query_id, listing.grader, listing.grade)
            
            store_price = Decimal(listing.price_aud)
            market_price = Decimal(benchmark.market_price) if benchmark else None
            
            if market_price and market_price > 0:
                discount_pct = float(((market_price - store_price) / market_price) * Decimal("100"))
                potential_profit = float(market_price - store_price)
            else:
                discount_pct = None
                potential_profit = None
            
            listings_data.append({
                "id": listing.id,
                "store": "cherry",
                "card_name": query.card_name if query else "Unknown",
                "product_title": listing.title,
                "grader": listing.grader,
                "grade": listing.grade,
                "store_price": float(store_price),
                "market_price": float(market_price) if market_price else None,
                "discount_percentage": discount_pct,
                "potential_profit": potential_profit,
                "product_url": listing.product_url,
                "image_url": listing.image_url,
                "in_stock": listing.in_stock,
            })
    
    if store in ("all", "leo"):
        leo_query = (
            db.query(LeoListing)
            .filter(LeoListing.is_active == True)
            .filter(LeoListing.last_seen_at >= cutoff)
        )
        if in_stock_only:
            leo_query = leo_query.filter(LeoListing.in_stock == True)
        
        for listing in leo_query.limit(limit).all():
            query = db.query(SearchQuery).filter(SearchQuery.id == listing.search_query_id).first()
            benchmark = _get_latest_benchmark(db, listing.search_query_id, listing.grader, listing.grade)
            
            store_price = Decimal(listing.price_aud)
            market_price = Decimal(benchmark.market_price) if benchmark else None
            
            if market_price and market_price > 0:
                discount_pct = float(((market_price - store_price) / market_price) * Decimal("100"))
                potential_profit = float(market_price - store_price)
            else:
                discount_pct = None
                potential_profit = None
            
            listings_data.append({
                "id": listing.id,
                "store": "leo",
                "card_name": query.card_name if query else "Unknown",
                "product_title": listing.title,
                "grader": listing.grader,
                "grade": listing.grade,
                "store_price": float(store_price),
                "market_price": float(market_price) if market_price else None,
                "discount_percentage": discount_pct,
                "potential_profit": potential_profit,
                "product_url": listing.product_url,
                "image_url": listing.image_url,
                "in_stock": listing.in_stock,
            })
    
    return {
        "count": len(listings_data),
        "listings": listings_data,
    }


class RunFullScanRequest(BaseModel):
    """Request to run a full scan of both stores."""
    in_stock_only: bool | None = Field(default=None)


@router.post("/api/run-full-scan")
async def run_full_scan_now(payload: RunFullScanRequest | None = None):
    """Trigger a full scan of both Cherry and Leo stores."""
    # Run all tasks with appropriate countdowns
    # Use force_all=True to process all queries without rate limits
    cherry_scrape = fetch_cherry_listings.apply_async()
    leo_scrape = fetch_leo_listings.apply_async(countdown=15)
    benchmarks = fetch_sold_benchmarks.apply_async(kwargs={"force_all": True}, countdown=120)
    cherry_score = identify_cherry_opportunities.apply_async(countdown=210)
    leo_score = identify_leo_opportunities.apply_async(countdown=240)

    return {
        "status": "queued",
        "queued_at": datetime.utcnow().isoformat(),
        "tasks": {
            "fetch_cherry_listings": cherry_scrape.id,
            "fetch_leo_listings": leo_scrape.id,
            "fetch_sold_benchmarks": benchmarks.id,
            "identify_cherry_opportunities": cherry_score.id,
            "identify_leo_opportunities": leo_score.id,
        },
    }
