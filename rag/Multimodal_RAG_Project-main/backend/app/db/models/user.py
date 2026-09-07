from sqlalchemy import Column, String, Integer, DateTime, func
from sqlalchemy.orm import mapped_column, Mapped
from ..base import Base

class User(Base):
      """User Model (placeholder for auth in future)"""
      __tablename__ = "users"

      id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
      email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
      full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
      created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
      updated_at: Mapped[DateTime] = mapped_column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
      )
