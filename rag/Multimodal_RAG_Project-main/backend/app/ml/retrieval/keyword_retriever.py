from typing import Tuple, List
from .bm25_manager import BM25Manager

class KeywordRetriever:
      def __init__(self):
            self.bm25_manager = BM25Manager()

      async def retrieve(self, query:str, k : int = 10) -> List[Tuple[int, float]]:
            """Reutrn (chunk_id, bm25_score)"""
            return await self.bm25_manager.search(query, k)