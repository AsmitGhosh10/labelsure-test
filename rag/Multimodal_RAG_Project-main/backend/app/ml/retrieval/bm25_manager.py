from typing import List, Optional, Tuple
import pickle
from pathlib import Path
import asyncio
import re 

from rank_bm25 import BM25Okapi
from ...core.config import settings

class BM25Manager:
      """
            Thread-safe BM25 manage with consistent corpus + chunk mapping.
      """

      _instance = None
      _lock = asyncio.Lock()

      def __new__(cls):
            if cls._instance is None:
                  cls._instance = super().__new__(cls)
                  cls._instance.__initialized = False
            return cls._instance
      

      def __init__(self):
            if self.__initialized:
                  return 
            
            self.index_path = Path(settings.BM25_INDEX_PATH)
            self.index_path.parent.mkdir(parents=True, exist_ok=True)

            self.bm25: Optional[BM25Okapi] = None
            self.chunk_ids: List[int] = []  
            self.corpus: List[str] = []

            self._write_lock = asyncio.Lock()

            self.__initialized = True
            self.load_index()
      
      # ========================
      # TOKENIZATION (IMPROVED)
      # ========================
      def _tokenize(self, text: str) -> List[str]:
            """
                  Better tokenizer than split().
            """
            text = text.lower()
            tokens = re.findall(r"\b\w+\b", text)
            return tokens
      
      # ==============
      # ➕ ADD DOCUMENTS
      # ==============
      async def add_documents(self, documents: List[str], chunk_ids: List[int]):
            """Add documents to BM25 corpus using real DB chunk IDs."""

            if not documents or len(documents) != len(chunk_ids):
                  return

            async with self._write_lock:
                  # ===== Filter invalid entries =====
                  valid_pairs = [
                        (doc, cid)
                        for doc, cid in zip(documents, chunk_ids)
                        if doc and cid is not None
                  ]

                  if not valid_pairs:
                        return
                  
                  docs, ids = zip(*valid_pairs)

                  self.corpus.extend(docs)
                  self.chunk_ids.extend(ids)

                  # 🔴 CRITICAL CHECK
                  assert len(self.corpus) == len(self.chunk_ids), "Corpus mismatch!"

                  # Rebuild BM25 
                  tokenized = [self._tokenize(doc) for doc in self.corpus]
                  self.bm25 = BM25Okapi(tokenized)

                  self._save_index()

                  print(f"[ BM25 ] Indexed docs: {len(self.corpus)}")
      # ==============
      # 🔍 SEARCH
      # ==============
      async def search(self, query: str, k: int = 10) -> List[Tuple[int, float]]:
            """Return (chunk_id, bm25_score)."""

            if self.bm25 is None or not self.chunk_ids:
                  return []

            tokenized_query = self._tokenize(query)
            scores = self.bm25.get_scores(tokenized_query)

            # Get top-k
            top_k = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:k]

            results = []
            for idx, score in top_k:
                  if idx < len(self.chunk_ids):
                        chunk_id = self.chunk_ids[idx]

                        # Extra safety
                        if chunk_id is not None:
                              results.append((chunk_id, float(score)))

            return results

      # ==========
      # ✅ SAVE 
      # ==========
      def _save_index(self):
            """Save current state"""

            with open(self.index_path, "wb") as f:
                  pickle.dump(
                        {
                              "bm25": self.bm25, 
                              "chunk_ids": self.chunk_ids, 
                              "corpus" : self.corpus,
                        }, 
                        f,
                  )
      
      # ===========
      # 🔃 LOAD
      # ===========
      def load_index(self):
            if not self.index_path.exists():
                  return

            try:
                  with open(self.index_path, "rb") as f:
                        data = pickle.load(f)

                        self.bm25 = data.get("bm25")
                        self.chunk_ids = data.get("chunk_ids", [])
                        self.corpus = data.get("corpus", [])
                  
                  print(f"[ BM25 ] Loaded docs: {len(self.corpus)}")
            
            except Exception as e:
                  print(f"[ BM25 ] Failed to load index: {e}")
                  self.bm25 = None
                  self.chunk_ids = []
                  self.corpus = []