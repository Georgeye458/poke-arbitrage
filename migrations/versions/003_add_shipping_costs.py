"""Add shipping cost fields to listings and opportunities.

Revision ID: 003_add_shipping_costs
Revises: 002_add_language
Create Date: 2026-01-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_add_shipping_costs"
down_revision: Union[str, None] = "002_add_language"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("psa10_listings", sa.Column("shipping_cost_aud", sa.Numeric(10, 2), nullable=True))
    op.add_column("arbitrage_opportunities", sa.Column("shipping_cost", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("arbitrage_opportunities", "shipping_cost")
    op.drop_column("psa10_listings", "shipping_cost_aud")

