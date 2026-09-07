from fastapi import HTTPException
from pydantic import ValidationError

def validate_query_length(query: str, max_length:int = 500)-> str:
      """Validate query length and content."""
      if not query or not query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

      if len(query) > max_length:
            raise HTTPException(status_code=400, detail=f"Query too long. Max length = {max_length} characters")
      
      return query.strip()