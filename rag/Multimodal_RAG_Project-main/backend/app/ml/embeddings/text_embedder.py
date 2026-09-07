from functools import partial
from typing import List
import numpy as np
import torch
import asyncio
from ...core.config import settings

from .base_embedder import BaseEmbedder


class TextEmbedder(BaseEmbedder):
      """Lazy-loaded text embedder."""

      def __init__(self):
            self.model_name = settings.EMBEDDING_MODEL
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = None
            self._dimension = None
            self._lock = asyncio.Lock()

      async def _load_model(self):
            async with self._lock:
                  if self._model is None:
                        from sentence_transformers import SentenceTransformer
                        self._model = SentenceTransformer(self.model_name, device=self.device)
                        self._dimension = self._model.get_embedding_dimension()

      async def embed_text(self, texts: List[str]) -> np.ndarray:
            if not texts:
                  return np.array([], dtype=np.float32).reshape(0, self.dimension)

            await self._load_model()

            loop = asyncio.get_running_loop()
            embeddings = await loop.run_in_executor(
                  None, partial(self._model.encode, texts, convert_to_numpy=True, normalize_embeddings=True)
            )
            return embeddings

      async def embed_image(self, images):
            raise NotImplementedError("Use ImageEmbedder for images.")

      @property
      def dimension(self) -> int:
            if self._dimension is None:
                  # Force load to get dimension
                  import asyncio
                  asyncio.run(self._load_model())  # safe in this context
            return self._dimension