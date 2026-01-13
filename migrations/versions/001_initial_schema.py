"""Initial schema with all tables.

Revision ID: 001_initial
Revises: 
Create Date: 2026-01-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create search_queries table
    op.create_table(
        'search_queries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('query_text', sa.String(255), nullable=False),
        sa.Column('card_name', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('query_text'),
    )
    
    # Create psa10_listings table
    op.create_table(
        'psa10_listings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('search_query_id', sa.Integer(), nullable=False),
        sa.Column('ebay_item_id', sa.String(50), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('price_aud', sa.Numeric(10, 2), nullable=False),
        sa.Column('original_currency', sa.String(10), nullable=True),
        sa.Column('original_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('seller_username', sa.String(100), nullable=True),
        sa.Column('seller_feedback_score', sa.Integer(), nullable=True),
        sa.Column('item_url', sa.Text(), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('listing_date', sa.DateTime(), nullable=True),
        sa.Column('scraped_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['search_query_id'], ['search_queries.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ebay_item_id'),
    )
    
    # Create market_benchmarks table
    op.create_table(
        'market_benchmarks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('search_query_id', sa.Integer(), nullable=False),
        sa.Column('market_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('data_source', sa.String(100), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False, default=5),
        sa.Column('min_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('max_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('calculated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['search_query_id'], ['search_queries.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    
    # Create arbitrage_opportunities table
    op.create_table(
        'arbitrage_opportunities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('listing_id', sa.Integer(), nullable=False),
        sa.Column('search_query_id', sa.Integer(), nullable=False),
        sa.Column('card_name', sa.String(255), nullable=False),
        sa.Column('listing_title', sa.String(500), nullable=False),
        sa.Column('listing_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('market_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('discount_percentage', sa.Numeric(5, 2), nullable=False),
        sa.Column('potential_profit', sa.Numeric(10, 2), nullable=False),
        sa.Column('ebay_item_id', sa.String(50), nullable=False),
        sa.Column('item_url', sa.Text(), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('seller_username', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('discovered_at', sa.DateTime(), nullable=False),
        sa.Column('last_verified_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['psa10_listings.id']),
        sa.ForeignKeyConstraint(['search_query_id'], ['search_queries.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    
    # Create indexes for performance
    op.create_index('ix_psa10_listings_search_query_id', 'psa10_listings', ['search_query_id'])
    op.create_index('ix_psa10_listings_last_seen_at', 'psa10_listings', ['last_seen_at'])
    op.create_index('ix_market_benchmarks_search_query_id', 'market_benchmarks', ['search_query_id'])
    op.create_index('ix_market_benchmarks_calculated_at', 'market_benchmarks', ['calculated_at'])
    op.create_index('ix_arbitrage_opportunities_is_active', 'arbitrage_opportunities', ['is_active'])
    op.create_index('ix_arbitrage_opportunities_discovered_at', 'arbitrage_opportunities', ['discovered_at'])


def downgrade() -> None:
    op.drop_table('arbitrage_opportunities')
    op.drop_table('market_benchmarks')
    op.drop_table('psa10_listings')
    op.drop_table('search_queries')
