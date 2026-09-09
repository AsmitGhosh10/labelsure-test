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


@router.get("/regulations/documents")
def list_documents():
    """The indexed documents, with how much of the corpus each contributes."""
    return {"documents": get_retriever().documents()}


@router.get("/regulations/search")
def search_regulations(
    q: str = "",
    top_k: int = 5,
    category: Optional[str] = None,
    rule_reference: Optional[str] = None,
    document: Optional[str] = None,
):
    """Search the corpus, or browse one document when no query is given.

    An empty query with a `document` is a browse, not a failed search: it
    returns that document's clauses in source order, unranked.
    """
    retriever = get_retriever()

    if not q.strip():
        if not document:
            raise HTTPException(status_code=422, detail="Query 'q' must not be empty")
        results = retriever.list_by_document(document)
        return {
            "query": "",
            "document": document,
            "count": len(results),
            "results": results,
            "note": None if results else f"No clauses indexed for {document}",
        }

    hits = retriever.search(
        q,
        top_k=top_k,
        category=category,
        rule_reference=rule_reference,
        document=document,
    )
    return {
        "query": q,
        "document": document,
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
        document=payload.document,
    )


@router.get("/regulations/{rule_id}")
def citation_for_rule(rule_id: str):
    citation = get_retriever().citation_for_rule(rule_id)
    if citation is None:
        raise HTTPException(
            status_code=404, detail=f"No regulation chunk for rule id {rule_id}"
        )
    return citation
