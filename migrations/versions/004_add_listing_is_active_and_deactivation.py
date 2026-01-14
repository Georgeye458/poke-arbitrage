"""Add is_active to listings for per-scan replacement semantics.

Revision ID: 004_add_listing_is_active
Revises: 003_add_shipping_costs
Create Date: 2026-01-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004_add_listing_is_active"
down_revision: Union[str, None] = "003_add_shipping_costs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "psa10_listings",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_psa10_listings_is_active", "psa10_listings", ["is_active"])
    op.alter_column("psa10_listings", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_psa10_listings_is_active", table_name="psa10_listings")
    op.drop_column("psa10_listings", "is_active")

