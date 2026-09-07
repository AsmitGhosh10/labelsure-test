from typing import List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.repositories.document_repository import DocumentRepository
from ..retrieval.hybrid_retriever import HybridRetriever
from .rrf_ranker import RRF_Ranker
from .reranker import CrossEncoderReranker


class ExplainabilityModule:
      """Provides explainable ranking with detailed factors."""

      def __init__(self):
            self.hybrid_retriever = HybridRetriever()
            self.rrf_ranker = RRF_Ranker()
            self.reranker = CrossEncoderReranker()
            self.document_repo = DocumentRepository()

      async def explain_ranking(
            self, 
            query:str,
            db:AsyncSession,
            k: int = 5,
      ) -> Dict[str, Any]:
            """Return retrieved chunks with detailed explanation of why they were ranked."""

            # Step 1: Hybrid retrieval
            hybrid_results = await self.hybrid_retriever.retrieve(query, k * 3)

            # Step 2: RRF ranking
            rrf_results = await self.rrf_ranker.rank([hybrid_results], query)
            #==========================
            #Step 3: EXtract chunk ids
            #==========================
            top_chunk_ids = [chunk_id for chunk_id, _ in rrf_results[:k * 2]]
            if not top_chunk_ids:
                  return {
                        "qeury": query,
                        "top_candidates": 0,
                        "final_results": [],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                  }
            #=======
            #Step 4
            #=======
            sources = await self.document_repo.get_chunks_with_documents(
                  session=db,
                  chunk_ids=top_chunk_ids,
            )
            #===Build chunk map===
            source_map = {s["chunk_id"]: s for s in sources}
            #===========================
            #Step 5: Prepare reanker candidates
            #===========================
            candidates = []
            for chunk_id, score in rrf_results[:k * 2]:
                  src = source_map.get(chunk_id)
                  if not src:
                        continue
                  candidates.append((chunk_id, score, src["content"]))
            #===============
            #Step 6: Rerank
            #===============
            reranked = await self.reranker.rerank(query, candidates)
            #===========================
            #Step 7 : Build Explanation
            #===========================
            explanations = []
            for rank, (chunk_id, final_score, content) in enumerate(reranked[:k], 1):
                  src = source_map.get(chunk_id)
                  if not src:
                        continue

                  explanations.append({
                  "rank": rank,
                  "chunk_id": chunk_id,
                  "content": content,
                 "documet":{
                        "id": src["document_id"],
                        "title": src["title"],
                        "file_name": src["file_name"],
                  },
                  "metadata": src["metadata"],
                  "final_score": round(float(final_score), 4),
                  "factors": {
                        "rrf_score": round(float(dict(rrf_results).get(chunk_id, 0)),4),
                        "reranker_score":round(float(final_score), 4),
                  },
                  "explanation": f"Ranked #{rank} after hybrid retrieval + cross-encoder reranking.",
                  "retrieval_method": "hybrid_faiss_bm25"
                  })
            
            return {
                  "query": query,
                  "total_candidates": len(hybrid_results),
                  "final_results": explanations,
                  "timestamp": datetime.now(timezone.utc).isoformat()
            }