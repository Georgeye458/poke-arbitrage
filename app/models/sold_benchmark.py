"""Sold-price benchmark model (eBay completed/sold comps)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SoldBenchmark(Base):
    """Represents a sold/completed market benchmark (AUD) for a query."""

    __tablename__ = "sold_benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_query_id: Mapped[int] = mapped_column(ForeignKey("search_queries.id"), nullable=False)

    market_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    data_source: Mapped[str] = mapped_column(String(100), default="ebay_finding_completed", nullable=False)

    sample_size: Mapped[int] = mapped_column(nullable=False, default=0)
    min_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    max_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)

    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    search_query: Mapped["SearchQuery"] = relationship("SearchQuery")

    def __repr__(self) -> str:
        return f"<SoldBenchmark(id={self.id}, price={self.market_price})>"

