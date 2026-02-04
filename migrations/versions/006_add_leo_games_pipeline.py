"""Add Leo Games listings and opportunities.

Revision ID: 006_add_leo_games_pipeline
Revises: 005_add_cherry_sold_pipeline
Create Date: 2026-02-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_add_leo_games_pipeline"
down_revision: Union[str, None] = "005_add_cherry_sold_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Leo Games listings table
    op.create_table(
        "leo_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_query_id", sa.Integer(), sa.ForeignKey("search_queries.id"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("handle", sa.String(length=255), nullable=False),
        sa.Column("product_url", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("price_aud", sa.Numeric(10, 2), nullable=False),
        sa.Column("language", sa.String(length=5), nullable=False, server_default="EN"),
        sa.Column("grader", sa.String(length=20), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("scraped_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "variant_id", name="uq_leo_product_variant"),
    )
    op.create_index("ix_leo_listings_search_query_id", "leo_listings", ["search_query_id"])
    op.create_index("ix_leo_listings_is_active", "leo_listings", ["is_active"])
    op.create_index("ix_leo_listings_grader_grade", "leo_listings", ["grader", "grade"])
    op.alter_column("leo_listings", "language", server_default=None)
    op.alter_column("leo_listings", "in_stock", server_default=None)
    op.alter_column("leo_listings", "is_active", server_default=None)

    # Leo Games opportunities table
    op.create_table(
        "leo_opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("leo_listing_id", sa.Integer(), sa.ForeignKey("leo_listings.id"), nullable=False),
        sa.Column("search_query_id", sa.Integer(), sa.ForeignKey("search_queries.id"), nullable=False),
        sa.Column("card_name", sa.String(length=255), nullable=False),
        sa.Column("product_title", sa.String(length=500), nullable=False),
        sa.Column("grader", sa.String(length=20), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("store_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("market_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("potential_profit", sa.Numeric(10, 2), nullable=False),
        sa.Column("product_url", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("discovered_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_verified_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("leo_listing_id", name="uq_leo_opportunity_listing"),
    )
    op.create_index("ix_leo_opportunities_search_query_id", "leo_opportunities", ["search_query_id"])
    op.create_index("ix_leo_opportunities_is_active", "leo_opportunities", ["is_active"])
    op.create_index("ix_leo_opportunities_grader_grade", "leo_opportunities", ["grader", "grade"])
    op.alter_column("leo_opportunities", "in_stock", server_default=None)
    op.alter_column("leo_opportunities", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_leo_opportunities_grader_grade", table_name="leo_opportunities")
    op.drop_index("ix_leo_opportunities_is_active", table_name="leo_opportunities")
    op.drop_index("ix_leo_opportunities_search_query_id", table_name="leo_opportunities")
    op.drop_table("leo_opportunities")

    op.drop_index("ix_leo_listings_grader_grade", table_name="leo_listings")
    op.drop_index("ix_leo_listings_is_active", table_name="leo_listings")
    op.drop_index("ix_leo_listings_search_query_id", table_name="leo_listings")
    op.drop_table("leo_listings")
