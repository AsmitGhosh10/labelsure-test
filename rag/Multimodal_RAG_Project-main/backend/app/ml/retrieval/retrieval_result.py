from dataclasses import dataclass, field
from typing import Dict

@dataclass
class HybridResult:
      chunk_id : int 

      # 📋 Raw Scores
      faiss_score : float | None = None
      bm25_score : float | None = None
      clip_score : float | None = None

      # 📊 Rank position per retriever
      ranks : Dict[str, int] = field(default_factory = dict)

      # Fusion score
      rrf_score : float = 0.0

      # Final scores
      fusion_score : float | None = None
      final_score : float | None = None
