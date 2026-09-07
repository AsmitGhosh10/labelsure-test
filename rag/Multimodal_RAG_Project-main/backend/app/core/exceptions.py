from fastapi import HTTPException, status
from typing import Any



class RAGException(HTTPException):
      """Base exception for RAG system"""
      def __init__(self, detail:str , status_code:int  = status.HTTP_500_INTERNAL_SERVER_ERROR):
            super().__init__(status_code=status_code, detail = detail)

class NotFoundException(RAGException):
      def __init__(self, detail: str = "Resource not found"):
            super().__init__(detail, status.HTTP_404_NOT_FOUND)

class ValidationException(RAGException):
      def __init__(self, detail: str = "Validation error"):
            super().__init__(detail, status.HTTP_422_UNPROCESSABLE_CONTENT)

class LLMException(RAGException):
      def __init__(self, detail: str = "LLM service error"):
            super().__init__(detail, status.HTTP_503_SERVICE_UNAVAILABLE)
