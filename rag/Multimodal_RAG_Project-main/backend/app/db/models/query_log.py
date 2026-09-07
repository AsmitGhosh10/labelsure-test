from sqlalchemy import Column, Integer, String, JSON, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base

class QueryLog(Base):
      """Log of user for analytica/explainability"""
      __tablename__ = "query_logs"

      id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
      query_text: Mapped[str] = mapped_column(Text, nullable=False)
      user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
      retrieved_count: Mapped[int] = mapped_column(Integer, default=0)
      response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
      metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
      created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


