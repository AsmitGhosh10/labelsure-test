"""Regulatory retrieval endpoints (PRD §8).

Search returns *citations*, never generated legal prose. An empty result set
means "nothing retrieved - manual verification required", which is reported
explicitly rather than dressed up as "no rule applies".
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.app.models import RegulationSearchRequest
from backend.app.services.regulation_retrieval import get_retriever

router = APIRouter()


@router.get("/regulations")
def corpus_stats():
    """What the retrieval corpus contains (documents, chunks, page coverage)."""
    return get_retriever().stats()


@router.get("/regulations/search")
def search_regulations(
    q: str,
    top_k: int = 5,
    category: Optional[str] = None,
    rule_reference: Optional[str] = None,
):
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query 'q' must not be empty")
    hits = get_retriever().search(
        q, top_k=top_k, category=category, rule_reference=rule_reference
    )
    return {
        "query": q,
        "count": len(hits),
        "results": hits,
        "note": (
            None
            if hits
            else "No regulation text retrieved - manual verification required"
        ),
    }


@router.post("/regulations/search")
def search_regulations_post(payload: RegulationSearchRequest):
    return search_regulations(
        q=payload.query,
        top_k=payload.top_k,
        category=payload.category,
        rule_reference=payload.rule_reference,
    )


@router.get("/regulations/{rule_id}")
def citation_for_rule(rule_id: str):
    citation = get_retriever().citation_for_rule(rule_id)
    if citation is None:
        raise HTTPException(
            status_code=404, detail=f"No regulation chunk for rule id {rule_id}"
        )
    return citation
