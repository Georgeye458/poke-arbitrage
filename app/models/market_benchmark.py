"""Market benchmark model for tracking market prices."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MarketBenchmark(Base):
    """Represents the market benchmark price for a PSA 10 card (always < $3,000 AUD)."""
    
    __tablename__ = "market_benchmarks"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    search_query_id: Mapped[int] = mapped_column(ForeignKey("search_queries.id"), nullable=False)
    
    # Market price data (filtered to be < $3,000 AUD)
    market_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    data_source: Mapped[str] = mapped_column(String(100), default="ebay_merchandising_api")
    
    # Additional context
    sample_size: Mapped[int] = mapped_column(default=5)  # Number of items used to calculate average
    min_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    max_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    
    # Timestamp
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationship
    search_query: Mapped["SearchQuery"] = relationship("SearchQuery", back_populates="benchmarks")
    
    def __repr__(self) -> str:
        return f"<MarketBenchmark(id={self.id}, price={self.market_price})>"
