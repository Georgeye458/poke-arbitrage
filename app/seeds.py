"""Database seed data for initial search queries."""

import logging
from app.database import SessionLocal
from app.models import SearchQuery

logger = logging.getLogger(__name__)

# Initial PSA 10 Pokemon card search queries (22 cards)
INITIAL_QUERIES = [
    ("charizard base set", "Charizard Base Set"),
    ("charizard 1st edition base set", "Charizard 1st Edition Base Set"),
    ("blastoise base set", "Blastoise Base Set"),
    ("venusaur base set", "Venusaur Base Set"),
    ("pikachu illustrator", "Pikachu Illustrator"),
    ("pikachu red cheeks", "Pikachu Red Cheeks"),
    ("mewtwo base set", "Mewtwo Base Set"),
    ("mew ancient origins", "Mew Ancient Origins"),
    ("lugia neo genesis", "Lugia Neo Genesis"),
    ("ho-oh neo revelation", "Ho-Oh Neo Revelation"),
    ("umbreon neo discovery", "Umbreon Neo Discovery"),
    ("espeon neo discovery", "Espeon Neo Discovery"),
    ("rayquaza gold star", "Rayquaza Gold Star"),
    ("charizard gold star", "Charizard Gold Star"),
    ("shining gyarados", "Shining Gyarados"),
    ("shining mewtwo", "Shining Mewtwo"),
    ("crystal charizard", "Crystal Charizard"),
    ("shadowless charizard", "Shadowless Charizard"),
    ("alakazam base set", "Alakazam Base Set"),
    ("gengar fossil", "Gengar Fossil"),
    ("dragonite fossil", "Dragonite Fossil"),
    ("machamp 1st edition", "Machamp 1st Edition"),
]


def seed_search_queries():
    """Seed the database with initial search queries."""
    db = SessionLocal()
    try:
        # Check if already seeded
        existing_count = db.query(SearchQuery).count()
        if existing_count > 0:
            logger.info(f"Database already has {existing_count} search queries, skipping seed")
            return
        
        # Insert initial queries
        for query_text, card_name in INITIAL_QUERIES:
            query = SearchQuery(
                query_text=query_text,
                card_name=card_name,
                is_active=True,
            )
            db.add(query)
        
        db.commit()
        logger.info(f"Seeded {len(INITIAL_QUERIES)} search queries")
        
    except Exception as e:
        logger.error(f"Failed to seed search queries: {e}")
        db.rollback()
    finally:
        db.close()
