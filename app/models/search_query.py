"""Search query model for tracking Pokemon card searches."""

from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SearchQuery(Base):
    """Represents a PSA 10 Pokemon card search query."""
    
    __tablename__ = "search_queries"
    __table_args__ = (
        UniqueConstraint("query_text", "language", name="uq_search_queries_query_text_language"),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    query_text: Mapped[str] = mapped_column(String(255), nullable=False)
    card_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "EN" or "JP"
    language: Mapped[str] = mapped_column(String(5), default="EN", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    listings: Mapped[list["PSA10Listing"]] = relationship(
        "PSA10Listing", back_populates="search_query", cascade="all, delete-orphan"
    )
    benchmarks: Mapped[list["MarketBenchmark"]] = relationship(
        "MarketBenchmark", back_populates="search_query", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<SearchQuery(id={self.id}, card='{self.card_name}', lang='{self.language}')>"
