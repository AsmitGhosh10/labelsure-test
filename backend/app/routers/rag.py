"""Regulation question-answering endpoints (RAG).

Retrieval-augmented answering over the same regulation corpus the rule engine
cites. Every answer carries its sources, and an ungrounded question gets an
explicit refusal rather than generated statutory prose.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.app.models import RAGAskRequest
from backend.app.services.rag_service import get_rag_service

router = APIRouter()


@router.get("/rag")
def rag_status() -> Dict[str, Any]:
    """Which retrieval, reranking and generation backends are live."""
    return get_rag_service().describe()


@router.post("/rag/ask")
def rag_ask(payload: RAGAskRequest) -> Dict[str, Any]:
    """Answer a question about the packaging rules, with citations."""
    try:
        return get_rag_service().ask(
            query=payload.query,
            k=payload.k,
            use_reranker=payload.use_reranker,
            category=payload.category,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
