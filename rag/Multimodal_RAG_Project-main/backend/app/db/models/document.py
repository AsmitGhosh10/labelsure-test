from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict
import hashlib

from sqlalchemy import  String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from ..base import Base

if TYPE_CHECKING:
      from backend.app.db.models.chunk import Chunk



class Document(Base):
      """Document metadata"""
      __tablename__ = "documents"

      #---------------------PRIMARY KEY------------------------------
      id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)


      #-------------EXISTING FIELDS OF FILES----------------------------------------------
      title: Mapped[str] = mapped_column(String(500), nullable=False)
      file_name: Mapped[str] = mapped_column(String(255), nullable=False)
      file_type: Mapped[str] = mapped_column(String(50), nullable=False)  # pdf, jpg, etc.
      content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
      user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

      #---------NEW FIELDS ADDED  TO REMOVE DUPLICATES AND REDUCE STORAGE USAGE------------------
      content_hash:Mapped[str] = mapped_column(String(64), index=True, nullable=False, unique=True)
      source_url:Mapped[str | None] = mapped_column(String, nullable=True)
      metadata_info:Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)



      #---------DETAILS OF CREATION AND UPDATION--------------------------------------------
      created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
      updated_at:Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

      # -------------RELATIONSHIPS-------------------------------------------------------------
      chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

      #------UTILITY FUNCTION TO COMPUTE AND CREATE HASH------------------------------------------
      @staticmethod
      def compute_content_hash(content: str) -> str:
            return hashlib.sha256(content.encode('utf-8')).hexdigest()
      

      @classmethod
      def create_with_hash(cls,
                        title:str,
                        content:str,
                        file_name: str | None = None,
                        file_type:str | None = None,
                        source_url: str | None = None,
                        user_id: int  | None = None,
                        metadata_info : dict | None = None
      ):
            content_hash = cls.compute_content_hash(content)
            return cls(
                  title = title, 
                  content_hash = content_hash,
                  content_summary = content[:500],
                  file_name = file_name,
                  file_type = file_type,
                  source_url = source_url,
                  user_id = user_id,
                  metadata_info = metadata_info or {}
            )