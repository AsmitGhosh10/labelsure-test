
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
      chunk_id: int
      content:str
      score:float
      chunk_type:str
      metadata: Dict[str, Any] = Field(default_factory=dict)

class SearchResponse(BaseModel):
      query: str
      results: List[RetrievedChunk]
      total_retrieved: int
      ranking_method: str = "hybrid_rrf_reranker"

class RAGResponse(BaseModel):
      query: str
      answer: str
      sources: List[RetrievedChunk]
      confidence: float = Field(..., ge=0.0, le=1.0)
      used_web_search:bool
