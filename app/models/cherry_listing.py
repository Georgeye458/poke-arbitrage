"""Cherry Collectables (Shopify) listing model."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CherryListing(Base):
    """Represents a PSA 10 Pokemon product listed on Cherry Collectables."""

    __tablename__ = "cherry_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_query_id: Mapped[int] = mapped_column(ForeignKey("search_queries.id"), nullable=False)

    # Shopify identifiers
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    variant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Product details
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    handle: Mapped[str] = mapped_column(String(255), nullable=False)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=True)

    # Pricing (AUD)
    price_aud: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Classification
    language: Mapped[str] = mapped_column(String(5), default="EN", nullable=False)  # EN or JP
    grader: Mapped[str] = mapped_column(String(20), default="PSA", nullable=False)
    grade: Mapped[int] = mapped_column(nullable=False, default=10)

    # Stock / status
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    search_query: Mapped["SearchQuery"] = relationship("SearchQuery")

    def __repr__(self) -> str:
        return f"<CherryListing(id={self.id}, product_id={self.product_id}, price={self.price_aud})>"

