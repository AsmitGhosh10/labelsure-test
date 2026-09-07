import os
import faiss
import numpy as np
from typing import List, Tuple, Optional, Dict
import pickle
from pathlib import Path
import asyncio
import structlog

from ...core.config import settings

logger = structlog.get_logger()


class FAISSManager:
    """Singleton + thread-safe FAISS manager (shared across ingestion & search)."""

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
        self.index_path = Path(settings.FAISS_INDEX_PATH)
        self.image_path = Path(settings.FAISS_IMAGE_INDEX_PATH)
        self.image_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.dimension: Optional[int] = None
        self.index: Optional[faiss.IndexFlatIP] = None
        self.faiss_to_chunk: Dict[int, int] = {}  # faiss_id → real DB chunk_id
        self._write_lock = asyncio.Lock()
        self.__initialized = True
        self.indexes: Dict[str, faiss.IndexFlatIP] = {}
        self.dimensions: Dict[str, int] = {}
        self.mappings: Dict[str, Dict[int, int]] = {}

    async def _initialize_index(self, index_type: str, dimension: int):
        """Ensure index is initialized."""

        async with self._write_lock:
            # =======INDEX=========
            if index_type not in self.indexes:
                index_path = self._get_index_path(index_type)

                if index_path.exists():
                    index = faiss.read_index(str(index_path))
                    self.indexes[index_type] = index
                    self.dimensions[index_type] = index.d
                else:
                    self.indexes[index_type] = faiss.IndexFlatIP(dimension)
                    self.dimensions[index_type] = dimension
            # ====== MAPPING ============
            if index_type not in self.mappings:
                index_path = self._get_index_path(index_type)
                mapping_path = index_path.with_suffix(".mapping.pkl")
                if mapping_path.exists():
                    with open(mapping_path, "rb") as f:
                        self.mappings[index_type] = pickle.load(f)
                else:
                    self.mappings[index_type] = {}

    def _get_index_path(self, index_type: str) -> Path:
        base = Path(settings.FAISS_INDEX_PATH)
        return base.parent / f"{index_type}.faiss"

    async def add_embeddings(
        self,
        embeddings: np.ndarray,
        chunk_ids: List[int],
        index_type: str = "text",
        save: bool = True,
    ) -> List[int]:
        """Add embeddings using real DB chunk IDs."""

        if len(embeddings) == 0 or len(embeddings) != len(chunk_ids):
            return []

        if any(cid is None for cid in chunk_ids):  # Hard validation for None chunk_id
            raise ValueError(
                f"[FAISS:{index_type}] Found None chunk_id during ingestion"
            )

        await self._initialize_index(index_type, embeddings.shape[1])

        async with self._write_lock:
            index = self.indexes[index_type]
            mapping = self.mappings.setdefault(index_type, {})

            embeddings = embeddings.astype(np.float32)
            # faiss.normalize_L2(embeddings)

            start_id = index.ntotal
            index.add(embeddings)

            faiss_ids = list(range(start_id, start_id + len(chunk_ids)))

            for f_id, c_id in zip(faiss_ids, chunk_ids):
                mapping[f_id] = c_id

            # ==== Invariant Check ====
            if index.ntotal != len(mapping):
                raise RuntimeError(
                    f"[FAISS:{index_type}] Index Size ({index.ntotal}) != Mapping Size ({len(mapping)})"
                )

            if save:
                self._save_index(index_type)

            # logger.info(f"[FAISS:{index_type}] Added ({len(chunk_ids)}) |  Total : ({index.ntotal})")
            logger.info(
                "FAISS Index updated",
                index_type=index_type,
                added=len(chunk_ids),
                total=index.ntotal,
            )

            return faiss_ids

    async def search(
        self, query_embedding: np.ndarray, k: int = 10, index_type: str = "text"
    ) -> List[Tuple[int, float]]:
        """Search – thread-safe for reads."""

        dim = query_embedding.shape[-1]
        await self._initialize_index(index_type, dim)

        index = self.indexes.get(index_type)
        mapping = dict(self.mappings.get(index_type, {}))

        if index is None or index.ntotal == 0:
            return []

        if index.d != dim:
            raise ValueError(f"Dimension mismatch: index={index.d}, query={dim}")

        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)

        query_embedding = query_embedding.astype(np.float32)
        faiss.normalize_L2(query_embedding)

        # logger.info(f"[FAISS:{index_type}] Search k = {k} | Index Size = {index.ntotal}")
        logger.info(
            f"FAISS search : {index_type}",
            index_type=index_type,
            k=k,
            index_size=index.ntotal,
        )

        scores, indices = index.search(query_embedding, k)

        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx != -1:
                chunk_id = mapping.get(int(idx))
                if chunk_id is not None:
                    results.append((chunk_id, float(score)))

        return results

    def _save_index(self, index_type: str):
        """Persist index and mapping."""
        index = self.indexes.get(index_type)
        if index is None:
            return

        index_path = self._get_index_path(index_type)
        faiss.write_index(index, str(index_path))
        mapping_path = index_path.with_suffix(".mapping.pkl")
        with open(mapping_path, "wb") as f:
            pickle.dump(self.mappings[index_type], f)

    def get_chunk_id(self, faiss_id: int) -> Optional[int]:
        return self.faiss_to_chunk.get(faiss_id)

    async def ensure_loaded(self, dimension: int = 384):
        """Public method to ensure index is loaded."""
        await self._initialize_index(dimension)

    def get_total_vectors(self, index_type: str) -> int:
        index = self.indexes.get(index_type)
        if index is None:
            return 0
        return index.ntotal

    async def save_index(self, index_type: str):
        async with self._write_lock:
            self._save_index(index_type)

    @property
    def total_vectors(self) -> Dict[str, int]:
        """Safe access to ntotal."""
        return {k: v.ntotal for k, v in self.indexes.items()}
