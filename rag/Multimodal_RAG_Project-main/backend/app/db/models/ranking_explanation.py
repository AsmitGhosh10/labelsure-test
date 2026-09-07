from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, JSON,Float, func
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class RankingExplanation(Base):
    """Explainable ranking details."""
    __tablename__ = "ranking_explanations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    query_log_id: Mapped[int] = mapped_column(ForeignKey("query_logs.id"), nullable=False)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id"), nullable=False)
    rank_score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    factors_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # semantic_score, keyword_score, etc.
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())