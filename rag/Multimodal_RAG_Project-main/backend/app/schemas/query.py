
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
      query: str = Field(..., min_length = 1, max_length = 500, description="User query")
      k: int = Field(default=5,ge=1, le=20, description="No. of solutions to return")
      use_reranker: bool = Field(default=True, description="Whether to apply cross-encoder reranking")

class SearchRequest(QueryRequest):
      pass

class RAGRequest(QueryRequest):
      temperature: float = Field(default=0.7, ge=0.0, le=1.0)
      max_tokens: int = Field(default=512, ge=50, le=2048)
      use_web_search: bool = Field(default=False, description="Force web search even if internal confidence is high")


