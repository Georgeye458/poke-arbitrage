"""PSA 10 listing model for active eBay listings."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PSA10Listing(Base):
    """Represents an active PSA 10 Pokemon card listing on eBay."""
    
    __tablename__ = "psa10_listings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    search_query_id: Mapped[int] = mapped_column(ForeignKey("search_queries.id"), nullable=False)
    
    # eBay listing details
    ebay_item_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    price_aud: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    shipping_cost_aud: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    original_currency: Mapped[str] = mapped_column(String(10), default="AUD")
    original_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    
    # Listing metadata
    seller_username: Mapped[str] = mapped_column(String(100), nullable=True)
    seller_feedback_score: Mapped[int] = mapped_column(nullable=True)
    item_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Timestamps
    listing_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Status (active = seen in most recent scan for this query)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationship
    search_query: Mapped["SearchQuery"] = relationship("SearchQuery", back_populates="listings")
    
    def __repr__(self) -> str:
        return f"<PSA10Listing(id={self.id}, item_id='{self.ebay_item_id}', price={self.price_aud})>"
