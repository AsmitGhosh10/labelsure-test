import asyncio
from typing import List, Tuple
import math

class CrossEncoderReranker:
      """Cross-Encoder reranker for final relevance scoring."""

      def __init__(self):
            self.model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            self._model = None
            self._lock = asyncio.Lock()
      
      async def _load_model(self):
            async with self._lock:
                  if self._model is None:
                        from sentence_transformers import CrossEncoder
                        self._model = CrossEncoder(self.model_name, max_length=512)
      
      async def rerank(self, query: str, candidates: List[Tuple[int, float, str]]) -> List[Tuple[int, float,str]]:
            """Rerank candidates using cross-encoder. candidates = [(chunk_id, score, content)]"""
            if not candidates:
                  return []

            await self._load_model()

            # Prepare pairs
            pairs = [(query, content) for _, _, content in candidates]

            loop = asyncio.get_running_loop()
            rerank_scores = await loop.run_in_executor(
                  None, self._model.predict, pairs
            )

            # Combine original score + reranker score
            reranked = []

            for (chunk_id, orig_score, content), rerank_score in zip(candidates, rerank_scores):
                  rerank_score = float(rerank_score)

                  # Sigmoid normalizaiton
                  norm_rerank = 1 / ( 1 + math.exp(-rerank_score))

                  # Original Score
                  norm_orig = max(0.0, min(1.0, float(orig_score)))

                  # Web boost
                  web_bonus = 0.10 if chunk_id < 0 else 0.0

                  # Final weighted score
                  final_score = (
                        0.80 * norm_rerank + 
                        0.20 * norm_orig + 
                        web_bonus
                  )

                  reranked.append(
                        (chunk_id, final_score, content)
                  )

            # Sort by final score
            return sorted(reranked, key=lambda x: x[1], reverse=True)    
      
      
            # min_score = min(rerank_scores)
            # max_score = max(rerank_scores)


            # for (chunk_id, orig_score, content), rerank_score in zip(candidates, rerank_scores):
            #       #---Normalize Reranker score---
            #       if max_score == min_score:
            #             norm_rerank = 0.5
            #       else:
            #             norm_rerank = (rerank_score - min_score) / (max_score - min_score)
                  
            #       # Normalize original score and avoid negative impact
            #       norm_orig = max(0.0, min(1.0, float(orig_score)))
            #       final_score = 0.7 * norm_rerank + 0.3 * norm_orig

            #       reranked.append((chunk_id, final_score, content))

            # # Sort by final score
            # return sorted(reranked, key=lambda x: x[1], reverse=True)