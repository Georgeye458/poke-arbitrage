"""Seed the database with initial search queries.

DEPRECATED: Static seeding is no longer needed. Search queries are now
dynamically created from Cherry Collectables PSA 10 listings.

To populate the database, run the fetch_cherry_listings task instead:
    celery -A app.tasks.celery_app call app.tasks.fetch_cherry_listings.fetch_cherry_listings
"""

if __name__ == "__main__":
    print("Static seeding is deprecated.")
    print("Search queries are now created dynamically from Cherry listings.")
    print("")
    print("To populate the database, run:")
    print("  celery -A app.tasks.celery_app call app.tasks.fetch_cherry_listings.fetch_cherry_listings")
