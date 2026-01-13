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
        "app.tasks.scrape_listings",
        "app.tasks.fetch_benchmarks",
        "app.tasks.identify_opportunities",
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
celery_app.conf.beat_schedule = {
    "scrape-listings-every-30-min": {
        "task": "app.tasks.scrape_listings.scrape_all_listings",
        "schedule": settings.task_interval_seconds,  # 1800 seconds = 30 min
    },
    "fetch-benchmarks-every-30-min": {
        "task": "app.tasks.fetch_benchmarks.fetch_all_benchmarks",
        "schedule": settings.task_interval_seconds,
    },
    "identify-opportunities-every-30-min": {
        "task": "app.tasks.identify_opportunities.identify_all_opportunities",
        # Run 2 minutes after benchmarks to ensure data is ready
        "schedule": settings.task_interval_seconds,
        "options": {"countdown": 120},
    },
}
