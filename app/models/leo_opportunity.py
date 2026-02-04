"""Opportunity model: Leo Games price vs eBay sold market."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LeoOpportunity(Base):
    """Represents a detected discount of a Leo Games graded product vs eBay sold comps."""

    __tablename__ = "leo_opportunities"

    id: Mapped[int] = mapped_column(primary_key=True)

    leo_listing_id: Mapped[int] = mapped_column(ForeignKey("leo_listings.id"), nullable=False)
    search_query_id: Mapped[int] = mapped_column(ForeignKey("search_queries.id"), nullable=False)

    card_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Grading info
    grader: Mapped[str] = mapped_column(String(20), nullable=False)  # PSA or CGC
    grade: Mapped[int] = mapped_column(nullable=False)

    store_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    market_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    potential_profit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<LeoOpportunity(id={self.id}, card='{self.card_name}', grader={self.grader}, discount={self.discount_percentage}%)>"
