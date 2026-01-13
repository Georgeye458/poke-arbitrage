"""Celery tasks."""

from app.tasks.celery_app import celery_app
from app.tasks.scrape_listings import scrape_all_listings
from app.tasks.fetch_benchmarks import fetch_all_benchmarks
from app.tasks.identify_opportunities import identify_all_opportunities

__all__ = [
    "celery_app",
    "scrape_all_listings",
    "fetch_all_benchmarks",
    "identify_all_opportunities",
]
