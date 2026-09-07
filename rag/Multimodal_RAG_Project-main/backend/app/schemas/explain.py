from pydantic import BaseModel
from typing import List, Dict, Any


class ExplainResponse(BaseModel):
      query: str
      total_candidates: int
      final_results: List[Dict[str, Any]]
      timestamp: str