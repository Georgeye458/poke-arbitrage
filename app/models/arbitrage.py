"""Arbitrage opportunity model."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArbitrageOpportunity(Base):
    """Represents an identified arbitrage opportunity."""
    
    __tablename__ = "arbitrage_opportunities"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # References
    listing_id: Mapped[int] = mapped_column(ForeignKey("psa10_listings.id"), nullable=False)
    search_query_id: Mapped[int] = mapped_column(ForeignKey("search_queries.id"), nullable=False)
    
    # Card details (denormalized for quick display)
    card_name: Mapped[str] = mapped_column(String(255), nullable=False)
    listing_title: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Price comparison
    listing_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    market_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    potential_profit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    
    # Listing info
    ebay_item_id: Mapped[str] = mapped_column(String(50), nullable=False)
    item_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=True)
    seller_username: Mapped[str] = mapped_column(String(100), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamps
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<ArbitrageOpportunity(id={self.id}, card='{self.card_name}', discount={self.discount_percentage}%)>"
