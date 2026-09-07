from typing import List, Dict, Any
import traceback
import time 
import structlog

from ..chunking.document_chunker import DocumentChunker
from ..embeddings.text_embedder import TextEmbedder
from ..embeddings.image_embedder import ImageEmbedder
from ..retrieval.faiss_manager import FAISSManager
from ..retrieval.bm25_manager import BM25Manager

logger = structlog.get_logger()

class IngestionPipeline:
      """DB-first ingestion: chunks saved first → real IDs → embeddings → vector stores."""

      def __init__(self):
            self.chunker = DocumentChunker()
            self.text_embedder = TextEmbedder()
            self.image_embedder = ImageEmbedder()
            self.faiss_manager = FAISSManager()
            self.bm25_manager = BM25Manager()

      async def ingest_chunks(self, document_id: int, chunks: List[Dict[str, Any]]) -> None:
            """Take pre-saved chunks with real DB IDs and index them."""
            if not chunks:    
                  return

            text_contents = [c["content"] for c in chunks if c["chunk_type"] == "text"]
            text_chunk_ids = [c["id"] for c in chunks if c["chunk_type"] == "text"]

            vectors_added = 0

            if text_contents:
                  embeddings = await self.text_embedder.embed_text(text_contents)
                  await self.faiss_manager.add_embeddings(embeddings, text_chunk_ids)
                  await self.bm25_manager.add_documents(text_contents, text_chunk_ids)
                  vectors_added += len(text_contents)


            # Image handling (simplified)
            for chunk in [c for c in chunks if c["chunk_type"] == "image"]:
                  img_path = chunk.get("metadata", {}).get("path")
                  if img_path:
                        try:
                              emb = await self.image_embedder.embed_image([img_path])
                              if emb.shape[0] > 0:
                                    await self.faiss_manager.add_embeddings(emb, [chunk["id"]])
                                    vectors_added += 1
                        except Exception as e:
                              print(f"Warning: Failed to embed image {img_path}: {str(e)}")
                              traceback.print_exc()
                              continue
            

            return {
                  "total_chunks": len(chunks),
                  "faiss_vectors": self.faiss_manager.total_vectors,
                  "vectors_added": vectors_added
            }
      #=========================
      #TEXT ONLY INGESTION (v2)
      #=========================
      async def ingest_text_chunks(
            self, 
            document_id:int,
            chunks:List[Dict[str, Any]],
      ) -> Dict[str, Any]:
            """
                  Clean text only ingestion.
                  No image handling.
            """

            if not chunks:
                  return {
                        "total_chunks": 0,
                        "faiss_vectors": self.faiss_manager.total_vectors,
                        "vectors_added": 0,
                  }
            
            text_chunks = [c for c in chunks if c["chunk_type"] == "text"]
            if not text_chunks:
                  return {
                        "total_chunks": 0,
                        "faiss_vectors": self.faiss_manager.total_vectors,
                        "vectors_added": 0,
                  }
            
            start = time.time()
            text_content = [c["content"] for c in text_chunks]
            text_ids = [c["id"] for c  in text_chunks]

            BATCH_SIZE = 32

            vectors_added = 0

            try:
                  for i in range(0, len(text_content), BATCH_SIZE):
                        batch_texts = text_content[i: i + BATCH_SIZE]
                        batch_ids = text_ids[i : i + BATCH_SIZE]

                        # Generate embeddings
                        embeddings = await self.text_embedder.embed_text(batch_texts)

                        # Store in FAISS
                        await self.faiss_manager.add_embeddings(
                              embeddings=embeddings, 
                              chunk_ids=batch_ids, 
                              index_type="text",
                              save = False,
                        )

                        # Store in BM25
                        await self.bm25_manager.add_documents(batch_texts, batch_ids)

                        vectors_added += len(batch_texts)

                        logger.info(
                              f"Text Batch Processed",
                              size = len(batch_texts),
                              time = time.time() - start,
                        )
                  
                  await self.faiss_manager.save_index("text")

            except Exception as e :
                  print(f"Text embeddings failed: {str(e)}")
                  traceback.print_exc()
            
            
            return {
                  "total_chunks": len(text_chunks),
                  "faiss_vectors": self.faiss_manager.get_total_vectors("text"),
                  "vectors_added": vectors_added,
            }
      
      #==================================
      #PIPELINE FOR IMAGE INGESTION (v2)
      #==================================
      async def ingest_image_chunks(
            self, 
            document_id:int,
            chunks: List[Dict[str, Any]],
      ) -> Dict[str, Any]:
            """
                  Clean image-only ingestion for v2
            """
            if not chunks:
                  return {
                        "total_chunks": 0,
                        "faiss_vectors": self.faiss_manager.get_total_vectors("image"),
                        "vectors_added": 0,
                  }
            image_chunks = [c for c in chunks if c["chunk_type"] == "image"]            
            if not image_chunks:
                  return {
                        "total_chunks": 0,
                        "faiss_vectors": self.faiss_manager.get_total_vectors("image"),
                        "vectors_added": 0,
                  }
            
            valid_paths = []
            valid_ids = []
            

            for chunk in image_chunks:
                  img_path = chunk.get("metadata", {}).get("path")
                  if img_path:
                        valid_paths.append(img_path)
                        valid_ids.append(chunk["id"])
                  
            if not valid_paths:
                  return {
                        "total_chunks": len(image_chunks),
                        "faiss_vectors": self.faiss_manager.get_total_vectors("image"),
                        "vectors_added": 0,
                  }

            start = time.time()
            vectors_added = 0
            BATCH_SIZE = 8

            try:
                  for i in range(0, len(valid_paths), BATCH_SIZE):
                        batch_paths = valid_paths[i: i + BATCH_SIZE]
                        batch_ids = valid_ids[i : i + BATCH_SIZE]

                        # Generate embedding
                        embeddings, valid_indices = await self.image_embedder.embed_image(batch_paths)
                        if embeddings.shape[0] == 0:
                              continue
                        
                        filtered_indices = [batch_ids[i] for i in valid_indices]

                        # Store in FAISS (image index)
                        await self.faiss_manager.add_embeddings(
                              embeddings=embeddings,
                              chunk_ids=filtered_indices,
                              index_type="image",
                              save=False,
                        )
                        vectors_added += len(batch_ids)

                        logger.info(
                              f"Text Batch Processed",
                              size = len(batch_ids),
                              time = time.time() - start,
                        )
                  
                  await self.faiss_manager.save_index("image")

            except Exception as e:
                  print(f"Failed image embedding: {str(e)}")
                  traceback.print_exc()

            
            return {
                  "total_chunks": len(image_chunks),
                  "faiss_vectors": self.faiss_manager.get_total_vectors("image"),
                  "vectors_added": vectors_added,
            }
