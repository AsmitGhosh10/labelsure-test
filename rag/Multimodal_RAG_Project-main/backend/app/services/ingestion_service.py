from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.repositories.base_repository import BaseRepository
from ..db.repositories.document_repository import DocumentRepository
from ..db.models.document import Document
from ..db.models.chunk import Chunk
from ..ml.pipelines.ingestion_pipeline import IngestionPipeline

class IngestionService:
      """Business logic for document ingestion"""

      def __init__(self):
            self.document_repo = DocumentRepository()
            self.chunk_repo = BaseRepository(Chunk)
            self.pipeline = IngestionPipeline()

      async def ingest(
            self, 
            db:AsyncSession,
            title:str,
            file_name:str,
            file_type:str,
            content:str | None = None,
            images: List[str] | None = None,
            user_id: int | None = None
      ) -> Dict[str, Any]:
            """Correct flow: Save Document → Save Chunks → Embed → Index."""

            safe_content = content if content else (file_name or "image_upload")

            # 1. Save document metadata
            document, already_exists = await self.document_repo.get_or_create_by_content(
                  session=db,
                  title=title,
                  content=safe_content,
                  file_name=file_name,
                  file_type=file_type,
                  source_url=None,
                  user_id=user_id
            )
            await db.flush()  # Get document.id

            #------If document already exist then no chunking--------------------
            if already_exists:
                  return {
                        "document_id": document.id,
                        "title": title,
                        "status": "skipped",
                        "chunks_created": 0,
                        "message": "Document already exists.Skipping re-ingestion"
                  }

            # 2. Create and save Chunks (DB first)
            all_chunks = []
            if content:
                  chunk_dicts = self.pipeline.chunker.chunk_text(content, {"title": title})
                  for cd in chunk_dicts:
                        chunk = Chunk(
                              document_id=document.id,
                              chunk_index=cd["chunk_index"],
                              content=cd["content"],
                              chunk_type=cd["chunk_type"],
                              metadata_json=cd.get("metadata")   # Pass dict directly – JSON column handles it
                        )
                        db.add(chunk)
                        all_chunks.append(chunk)

            
            #===============
            #IMAGE CHUNKING
            #===============
            if images:
                  for idx, image_path in enumerate(images):
                        chunk = Chunk(
                              document_id = document.id,
                              chunk_index = len(all_chunks) + idx,
                              content = image_path,
                              chunk_type = "image",
                              metadata_json = {"source": "image", "path":image_path}     
                        )
                        db.add(chunk)
                        all_chunks.append(chunk)
            
            await db.commit()
            await db.refresh(document)
            # Convert to dict with real IDs for pipeline
            chunk_list_for_pipeline = [
                  {
                        "id": c.id,
                        "content": c.content,
                        "chunk_type": c.chunk_type,
                        "metadata": c.metadata_json or {}   # Now safely a dict
                  }
                  for c in all_chunks
            ]  
            # 3. Index in vector stores
            pipeline_result = await self.pipeline.ingest_chunks(document.id, chunk_list_for_pipeline)

            return {
                  "document_id": document.id,
                  "title": title,
                  "status": "success",
                  "chunks_created": len(all_chunks),
                  "faiss_vectors_total": pipeline_result["faiss_vectors"],
                  "vectors_added": pipeline_result["vectors_added"],
                  "message": "Document ingested and indexed successfully."
            }
      #=======================
      #INGESTION OF FILE ONLY
      #=======================
      async def ingest_file(
            self,
            db: AsyncSession,
            title: str,
            file_name: str ,
            file_type: str,
            content : str,
            user_id : int  | None
      ) -> Dict[str, any]:
            """
                  Clean text-only ingestion flow(v2).
                  No image handling.
            """
            safe_content = content if content else (file_name or "empty_file")
            #==============
            #Save document
            #==============
            document, already_exists = await self.document_repo.get_or_create_by_content(
                  session=db,
                  title=title,
                  content=safe_content,
                  file_name=file_name,
                  file_type=file_type,
                  source_url=None,
                  user_id=user_id
            )
            await db.flush()

            if already_exists:
                  return{
                        "document_id": document.id,
                        "title": title,
                        "status": "skipped",
                        "chunks_created": 0,
                        "message": "Document already exists.Skipping re-ingestion"
                  }
            #==============
            #Chunk text
            #==============
            chunk_dicts = self.pipeline.chunker.chunk_text(
                  content, {"title": title}
            )
            # print("=" * 50)
            # print(f"The chunks returned from the chunk_text function \n{chunk_dicts}")
            # print("=" * 50)
            chunks = []
            for cd in chunk_dicts:
                  chunk = Chunk(
                        document_id=document.id,
                        chunk_index=cd["chunk_index"],
                        content=cd["content"],
                        chunk_type="text",
                        metadata_json=cd.get("metadata")   # Pass dict directly – JSON column handles it
                  )
                  db.add(chunk)
                  chunks.append(chunk)
            
            await db.commit()
            await db.refresh(document)
            
            chunk_list_for_pipeline = [
                  {
                        "id": c.id,
                        "content": c.content,
                        "chunk_type": c.chunk_type,
                        "metadata": c.metadata_json or {}   # Now safely a dict
                  }
                  for c in chunks
            ]  
            # 3. Index in vector stores
            pipeline_result = await self.pipeline.ingest_text_chunks(document.id, chunk_list_for_pipeline)


            return {
                  "document_id": document.id,
                  "title": title,
                  "status": "success",
                  "chunks_created": len(chunks),
                  "faiss_vectors_total": pipeline_result["faiss_vectors"],
                  "vectors_added": pipeline_result["vectors_added"],
                  "message": "Document ingested and indexed successfully."
            }
      #========================
      #INGESTION OF IMAGE ONLY
      #========================
      async def ingest_image(
            self,
            db: AsyncSession,
            title: str,
            file_name : str, 
            file_type : str,
            image_path: str,
            user_id:int | None = None,
      ) -> Dict[str, Any]:
            """
                  Image only ingestion for v2
            """

            safe_content = file_name or "image_upload"

            document, already_exists = await self.document_repo.get_or_create_by_content(
                  session=db,
                  title=title,
                  content=safe_content,
                  file_name=file_name,
                  file_type=file_type,
                  source_url=None,
                  user_id=user_id
            ) 

            await db.flush()

            if already_exists:
                  return{
                        "document_id": document.id,
                        "title": title,
                        "status": "skipped",
                        "chunks_created": 0,
                        "message": "Image already exists.Skipping re-ingestion"
                  }
            #=====================
            #IMAGE CHUNK CREATION
            #=====================
            chunk = Chunk(
                  document_id=document.id,
                  chunk_index=0,
                  content=image_path,
                  chunk_type="image",
                  metadata_json={
                        "source": "image",
                        "path": image_path,
                  },
            )

            db.add(chunk)

            
            await db.commit()
            await db.refresh(document)

            #Prepare for pipeline
            chunk_list_for_pipeline = [
                  {
                        "id": chunk.id,
                        "content": chunk.content,
                        "chunk_type": chunk.chunk_type,
                        "metadata": chunk.metadata_json or {},
                  }
            ]
            #============================
            #PIPELINE CALL (IMAGE ONLY)
            #============================
            pipeline_result   = await self.pipeline.ingest_image_chunks(
                  document.id,chunk_list_for_pipeline
            )

            
            return {
                  "document_id": document.id,
                  "title": title,
                  "status": "success",
                  "chunks_created": 1,
                  "faiss_vectors_total": self.pipeline.faiss_manager.get_total_vectors("image"),
                  "vectors_added": pipeline_result["vectors_added"],
                  "message": "Image ingested and indexed successfully."
            }
