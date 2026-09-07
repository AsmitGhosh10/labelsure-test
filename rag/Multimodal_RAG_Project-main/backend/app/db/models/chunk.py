from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Any

from sqlalchemy import Integer, Text, DateTime, ForeignKey,String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..base import Base

if TYPE_CHECKING:
      from backend.app.db.models.document import Document



class Chunk(Base):
      """Text/Image chunk for retrieval"""
      __tablename__ = "chunks"

      #-----------PRIMARY KEY------------------------------------------------------------
      id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

      #----------CHUNK DATA-------------------------------------------------------------
      document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
      chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
      content: Mapped[str] = mapped_column(Text, nullable=False)
      chunk_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text or image
      metadata_json: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # JSON string for extra info

      #-------DATETIME OF CREATION--------------------------------------------------------------
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

      document: Mapped["Document"] = relationship("Document", back_populates="chunks")