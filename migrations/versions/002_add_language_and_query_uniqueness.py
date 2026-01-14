"""Add language to search queries and make (query_text, language) unique.

Revision ID: 002_add_language
Revises: 001_initial
Create Date: 2026-01-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_add_language"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add language column (default EN)
    op.add_column(
        "search_queries",
        sa.Column("language", sa.String(length=5), nullable=False, server_default="EN"),
    )

    # Drop old uniqueness on query_text (created by SQLAlchemy as search_queries_query_text_key)
    op.drop_constraint("search_queries_query_text_key", "search_queries", type_="unique")

    # Create new composite unique constraint
    op.create_unique_constraint(
        "uq_search_queries_query_text_language",
        "search_queries",
        ["query_text", "language"],
    )

    # Remove server default (keep app-level default)
    op.alter_column("search_queries", "language", server_default=None)


def downgrade() -> None:
    op.drop_constraint("uq_search_queries_query_text_language", "search_queries", type_="unique")
    op.create_unique_constraint("search_queries_query_text_key", "search_queries", ["query_text"])
    op.drop_column("search_queries", "language")

