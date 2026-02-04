"""Celery application configuration."""

import ssl

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# Handle Heroku Redis SSL connection (rediss://)
redis_url = settings.redis_url
broker_use_ssl = None
backend_use_ssl = None

if redis_url.startswith("rediss://"):
    # Heroku Redis uses SSL - configure for self-signed certs
    broker_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_NONE,
    }
    backend_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_NONE,
    }

# Create Celery app
celery_app = Celery(
    "pokearbitrage",
    broker=redis_url,
    backend=redis_url,
    include=[
        # Legacy pipeline (kept for reference)
        "app.tasks.scrape_listings",
        "app.tasks.fetch_benchmarks",
        "app.tasks.identify_opportunities",
        # Cherry Collectables pipeline
        "app.tasks.fetch_cherry_listings",
        "app.tasks.fetch_sold_benchmarks",
        "app.tasks.identify_cherry_opportunities",
        # Leo Games pipeline
        "app.tasks.fetch_leo_listings",
        "app.tasks.identify_leo_opportunities",
    ],
)

# Celery configuration
celery_config = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "task_time_limit": 300,  # 5 minute timeout
    "worker_prefetch_multiplier": 1,
    "worker_concurrency": 2,
}

# Add SSL config if using rediss://
if broker_use_ssl:
    celery_config["broker_use_ssl"] = broker_use_ssl
    celery_config["redis_backend_use_ssl"] = backend_use_ssl

celery_app.conf.update(**celery_config)

# Beat schedule - runs every 30 minutes
celery_app.conf.beat_schedule = {}
if settings.scheduler_enabled:
    celery_app.conf.beat_schedule = {
        # Cherry Collectables tasks
        "fetch-cherry-listings-every-30-min": {
            "task": "app.tasks.fetch_cherry_listings.fetch_cherry_listings",
            "schedule": settings.task_interval_seconds,
        },
        # Leo Games tasks
        "fetch-leo-listings-every-30-min": {
            "task": "app.tasks.fetch_leo_listings.fetch_leo_listings",
            "schedule": settings.task_interval_seconds,
            "options": {"countdown": 30},
        },
        # Benchmarks (after store listings are fetched)
        "fetch-sold-benchmarks-every-30-min": {
            "task": "app.tasks.fetch_sold_benchmarks.fetch_sold_benchmarks",
            "schedule": settings.task_interval_seconds,
            "options": {"countdown": 120},
        },
        # Opportunity identification (after benchmarks are fetched)
        "identify-cherry-opportunities-every-30-min": {
            "task": "app.tasks.identify_cherry_opportunities.identify_cherry_opportunities",
            "schedule": settings.task_interval_seconds,
            "options": {"countdown": 210},
        },
        "identify-leo-opportunities-every-30-min": {
            "task": "app.tasks.identify_leo_opportunities.identify_leo_opportunities",
            "schedule": settings.task_interval_seconds,
            "options": {"countdown": 240},
        },
    }
