"""Database seed data for initial search queries.

DEPRECATED: This module is no longer used. Search queries are now dynamically
created from Cherry Collectables PSA 10 listings via fetch_cherry_listings task.
The static seed list below is kept for reference only.
"""

import logging
from app.database import SessionLocal
from app.models import SearchQuery

logger = logging.getLogger(__name__)

# Base PSA 10 Pokemon card search queries (22 cards)
BASE_QUERIES = [
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

# Extra targets from user list (seeded into both EN + JP streams; Browse language aspect_filter keeps them separated).
EXTRA_QUERIES = [
    # Base / Jungle / Fossil / Rocket / Neo
    ("chansey base set", "Chansey Base Set"),
    ("snorlax jungle", "Snorlax Jungle"),
    ("wigglytuff jungle", "Wigglytuff Jungle"),
    ("articuno fossil", "Articuno Fossil"),
    ("zapdos fossil", "Zapdos Fossil"),
    ("moltres fossil", "Moltres Fossil"),
    ("dark blastoise team rocket", "Dark Blastoise (Team Rocket)"),
    ("dark charizard team rocket", "Dark Charizard (Team Rocket)"),
    ("typhlosion neo genesis", "Typhlosion Neo Genesis"),
    ("feraligatr neo genesis", "Feraligatr Neo Genesis"),
    ("meganium neo genesis", "Meganium Neo Genesis"),

    # e-Card / Aquapolis-ish
    ("tyranitar aquapolis", "Tyranitar Aquapolis"),
    ("lugia aquapolis", "Lugia Aquapolis"),

    # EX era
    ("rayquaza ex ex dragon", "Rayquaza ex (EX Dragon)"),
    ("latios ex", "Latios ex"),
    ("latias ex", "Latias ex"),
    ("rocket's mewtwo ex", "Rocket's Mewtwo ex"),
    ("espeon ex unseen forces", "Espeon ex (Unseen Forces)"),
    ("umbreon ex unseen forces", "Umbreon ex (Unseen Forces)"),

    # DP / BW / XY / misc
    ("charizard stormfront secret rare", "Charizard (Stormfront Secret Rare)"),
    ("garchomp c lv.x supreme victors", "Garchomp C LV.X (Supreme Victors)"),
    ("n full art trainer", "N (Full Art)"),
    ("skyla full art trainer", "Skyla (Full Art)"),
    ("bianca full art trainer", "Bianca (Full Art)"),
    ("charizard plasma storm secret rare", "Charizard (Plasma Storm Secret Rare)"),
    ("white kyurem ex boundaries crossed", "White Kyurem EX (Boundaries Crossed)"),
    ("black kyurem ex boundaries crossed", "Black Kyurem EX (Boundaries Crossed)"),
    ("pikachu full art promo", "Pikachu Full Art Promo"),
    ("shining mew", "Shining Mew"),
    ("shining jirachi", "Shining Jirachi"),
]

BASE_QUERIES.extend(EXTRA_QUERIES)

# We track English and Japanese separately.
LANGUAGES = ["EN", "JP"]


def seed_search_queries():
    """Seed the database with initial search queries."""
    db = SessionLocal()
    try:
        created = 0

        for query_text, card_name in BASE_QUERIES:
            for language in LANGUAGES:
                exists = (
                    db.query(SearchQuery)
                    .filter(SearchQuery.query_text == query_text)
                    .filter(SearchQuery.language == language)
                    .first()
                )
                if exists:
                    continue

                query = SearchQuery(
                    query_text=query_text,
                    card_name=card_name,
                    language=language,
                    is_active=True,
                )
                db.add(query)
                created += 1

        db.commit()
        logger.info(f"Seeded/ensured {created} search queries (EN+JP)")
        
    except Exception as e:
        logger.error(f"Failed to seed search queries: {e}")
        db.rollback()
    finally:
        db.close()
