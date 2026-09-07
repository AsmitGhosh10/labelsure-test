from typing import  Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import  select
from sqlalchemy.orm import selectinload
from ..models.document import Document
from ..models.chunk import Chunk
from ..repositories.base_repository import BaseRepository

class DocumentRepository(BaseRepository[Document]):
      """Creation of document and fetching them."""
      def __init__(self):
            super().__init__(Document)

      
      async def get_or_create_by_content(
            self, 
            session:AsyncSession,
            title:str,
            content:str,
            file_name: Optional[str] = None,
            file_type: Optional[str] = None,
            source_url:Optional[str] = None,
            user_id: Optional[int] = None,
            metadata_info: Optional[dict] = None
      ) -> Document:
            """Prevents duplicates using content_hash."""
            content_hash = Document.compute_content_hash(content)

            #-----------First check by content hash-----------------------------------
            result = await session.execute(select(Document).where(Document.content_hash == content_hash))
            existing_doc= result.scalar_one_or_none()

            if existing_doc:
                  #-------Update Metadata if source_url or title changed--------------------------
                  if source_url  and existing_doc.source_url != source_url:
                        existing_doc.source_url = source_url
                  if title and existing_doc.title != title:
                        existing_doc.title = title
                  await session.commit()
                  await session.refresh(existing_doc)
                  return existing_doc, True
            
            #---------Create new document if document hash not found------------------------------
            new_doc = Document.create_with_hash(
                  title = title,
                  content= content,
                  file_name=file_name,
                  file_type=file_type,
                  source_url=source_url,
                  user_id = user_id,
                  metadata_info=metadata_info
            )
            session.add(new_doc)
            await session.commit()
            await session.refresh(new_doc)
            return new_doc, False
      
      async def get_document_with_chunks(self, session: AsyncSession, doc_id: int) -> Optional[Document]:
            """Reliable fetch with chunks in one query."""
            result = await session.execute(select(Document).where(Document.id == doc_id).options(selectinload(Document.chunks)))

            return result.scalar_one_or_none()

                                           
      #---HELPER METHOD FOR BULK RETRIEVAL USED IN search/explain------------------------------
      async def get_documents_with_chunks_by_ids(self, session: AsyncSession, doc_ids: List[int]) -> List[Document]:

            """Fetch multiple documents with their chunk ids reliably"""
            if not doc_ids:
                  return []
            
            unique_doc_ids = list(dict.fromkeys(doc_ids))

            result = await session.execute(select(Document)
                                          .where(Document.id.in_(unique_doc_ids))
                                          .options(selectinload(Document.chunks))
                                    )
            return result.scalars().unique().all()
      

      async def get_chunks_with_documents(
            self, 
            session: AsyncSession,
            chunk_ids: List[int]
      ) -> List[Dict[str, Any]]:
            
            """Reliable way to fetch chunks + documents in a fresh session."""
            if not chunk_ids:
                  return []
            
            unique_chunk_ids = list(dict.fromkeys(chunk_ids))

            stmt = (
                  select(Chunk)
                  .where(Chunk.id.in_(unique_chunk_ids))
                  .options(selectinload(Chunk.document))
            )

            result = await session.execute(stmt)
            chunks = result.scalars().unique().all()

            sources  = []

            for chunk in chunks:
                  doc = getattr(chunk, "document", None)
                  if not doc :
                        continue

                  sources.append({
                        "document_id": doc.id,
                        "chunk_id": chunk.id,
                        "title": doc.title,
                        "file_name": doc.file_name,
                        "content":chunk.content[:800] + "..." if len(chunk.content) > 800 else chunk.content,
                        "chunk_type": getattr(chunk, "chunk_type", None),
                        "metadata": chunk.metadata_json or doc.metadata_info or {},
                        "score": 0.0,
                  })
            
            return sources
      
      async def get_chunks_with_documents_and_hashes(
            self,
            session: AsyncSession,
            chunk_ids: List[int]
            ) -> List[Dict[str, Any]]:
            """Fetch chunks + parent documents + documet content_hash for stronger deduplication."""
            if not chunk_ids:
                  return []
            
            unique_chunk_ids = list(dict.fromkeys(chunk_ids))

            stmt = (
                  select(Chunk)
                  .where(Chunk.id.in_(unique_chunk_ids))
                  .options(selectinload(Chunk.document))
            )

            result = await session.execute(stmt)
            chunks = result.scalars().unique().all()

            sources  = []

            for chunk in chunks:
                  doc = getattr(chunk, "document", None)
                  if not doc :
                        continue

                  sources.append({
                        "document_id": doc.id,
                        "document_content_hash": doc.content_hash,
                        "chunk_id": chunk.id,
                        "title": doc.title,
                        "file_name": doc.file_name,
                        "content":chunk.content[:800] + "..." if len(chunk.content) > 800 else chunk.content,
                        "chunk_type": getattr(chunk, "chunk_type", None),
                        "metadata": chunk.metadata_json or doc.metadata_info or {},
                        "score": 0.0,
                  })
            
            return sources
            

      

                                    
            
