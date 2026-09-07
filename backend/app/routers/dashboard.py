"""Supervisor dashboard statistics (PRD §27)."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from backend.app import auth, database
from backend.app.services import legal

router = APIRouter()


@router.get("/stats")
def stats(
    principal: Dict[str, Any] = Depends(auth.require_role(auth.SUPERVISOR)),
):
    """Repository-wide statistics: totals, decision mix, average confidence,
    common violations, manufacturer trends, daily trend, inspector activity."""
    payload = database.inspection_stats()
    payload["disclaimer"] = legal.SHORT_DISCLAIMER
    return payload


@router.get("/stats/violations")
def violation_breakdown(
    limit: int = 20,
    principal: Dict[str, Any] = Depends(auth.require_role(auth.SUPERVISOR)),
):
    """Most frequent violated rules, with the regulation each one cites."""
    from backend.app.services.regulation_retrieval import get_retriever

    retriever = get_retriever()
    payload = database.inspection_stats(limit_common=limit)
    rows = []
    for entry in payload.get("common_violations", []):
        citation = retriever.citation_for_rule(entry["rule_id"])
        rows.append(
            {
                **entry,
                "rule": (citation or {}).get("rule"),
                "title": (citation or {}).get("title"),
                "page": (citation or {}).get("page"),
                "document": (citation or {}).get("document"),
            }
        )
    return {"violations": rows, "total_inspections": payload["total_inspections"]}
