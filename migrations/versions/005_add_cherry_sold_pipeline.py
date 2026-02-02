"""Add Cherry listings, sold benchmarks, and Cherry opportunities.

Revision ID: 005_add_cherry_sold_pipeline
Revises: 004_add_listing_is_active
Create Date: 2026-02-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_add_cherry_sold_pipeline"
down_revision: Union[str, None] = "004_add_listing_is_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cherry_listings",
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
        sa.Column("grader", sa.String(length=20), nullable=False, server_default="PSA"),
        sa.Column("grade", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("scraped_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "variant_id", name="uq_cherry_product_variant"),
    )
    op.create_index("ix_cherry_listings_search_query_id", "cherry_listings", ["search_query_id"])
    op.create_index("ix_cherry_listings_is_active", "cherry_listings", ["is_active"])
    op.alter_column("cherry_listings", "language", server_default=None)
    op.alter_column("cherry_listings", "grader", server_default=None)
    op.alter_column("cherry_listings", "grade", server_default=None)
    op.alter_column("cherry_listings", "in_stock", server_default=None)
    op.alter_column("cherry_listings", "is_active", server_default=None)

    op.create_table(
        "sold_benchmarks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_query_id", sa.Integer(), sa.ForeignKey("search_queries.id"), nullable=False),
        sa.Column("market_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("data_source", sa.String(length=100), nullable=False, server_default="ebay_finding_completed"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("min_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("calculated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sold_benchmarks_search_query_id", "sold_benchmarks", ["search_query_id"])
    op.alter_column("sold_benchmarks", "data_source", server_default=None)
    op.alter_column("sold_benchmarks", "sample_size", server_default=None)

    op.create_table(
        "cherry_opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cherry_listing_id", sa.Integer(), sa.ForeignKey("cherry_listings.id"), nullable=False),
        sa.Column("search_query_id", sa.Integer(), sa.ForeignKey("search_queries.id"), nullable=False),
        sa.Column("card_name", sa.String(length=255), nullable=False),
        sa.Column("product_title", sa.String(length=500), nullable=False),
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
        sa.UniqueConstraint("cherry_listing_id", name="uq_cherry_opportunity_listing"),
    )
    op.create_index("ix_cherry_opportunities_search_query_id", "cherry_opportunities", ["search_query_id"])
    op.create_index("ix_cherry_opportunities_is_active", "cherry_opportunities", ["is_active"])
    op.alter_column("cherry_opportunities", "in_stock", server_default=None)
    op.alter_column("cherry_opportunities", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_cherry_opportunities_is_active", table_name="cherry_opportunities")
    op.drop_index("ix_cherry_opportunities_search_query_id", table_name="cherry_opportunities")
    op.drop_table("cherry_opportunities")

    op.drop_index("ix_sold_benchmarks_search_query_id", table_name="sold_benchmarks")
    op.drop_table("sold_benchmarks")

    op.drop_index("ix_cherry_listings_is_active", table_name="cherry_listings")
    op.drop_index("ix_cherry_listings_search_query_id", table_name="cherry_listings")
    op.drop_table("cherry_listings")

