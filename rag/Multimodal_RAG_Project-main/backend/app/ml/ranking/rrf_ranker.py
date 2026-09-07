from typing import List, Tuple, Dict
import asyncio

class RRF_Ranker:
      """Reciprocal Ranking Fusion (RRF) for hybrid ranking."""

      def __init__(self, k : int = 40):
            self.k = k #RRF constant
      
      async def rank(self, result_lists: List[List[Tuple[int, float]]], query: str) -> List[Tuple[int , float]]:
            """Apply RRF on list  of (chunk_id, score) from different retrievers."""
            
            # Group by chunk_id and compute RRF score
            score_map: Dict[int, float] = {}
            for results in result_lists:
                  for rank, (chunk_id, _) in enumerate(results, 1):
                        rrf_score = 1.0 / (self.k + rank)
                        score_map[chunk_id] = score_map.get(chunk_id, 0.0) + rrf_score

            #Sort by RRF score
            ranked = sorted(score_map.items(),key = lambda x : x[1], reverse=True )
            return ranked

      
      

            
