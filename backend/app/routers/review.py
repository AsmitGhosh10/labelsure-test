"""Human-in-the-loop review endpoints (PRD §21) and the audit trail (§30)."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app import auth, database
from backend.app.models import InspectorDecisionRequest, InspectorDecisionResponse
from backend.app.services import hitl

router = APIRouter()


@router.post(
    "/inspections/{inspection_id}/decision", response_model=InspectorDecisionResponse
)
def record_decision(
    inspection_id: str,
    payload: InspectorDecisionRequest,
    principal: Dict[str, Any] = Depends(auth.require_role(auth.INSPECTOR)),
):
    """Accept or override the automated finding.

    The inspector identity comes from the authenticated token when auth is
    enabled; only an unauthenticated (auth-disabled) caller may name itself.
    """
    if auth.auth_enabled():
        inspector_id = auth.principal_id(principal)
    else:
        inspector_id = (payload.inspector_id or "").strip()
        if not inspector_id:
            raise HTTPException(
                status_code=422,
                detail="inspector_id is required when authentication is disabled",
            )

    try:
        return hitl.record_decision(
            inspection_id=inspection_id,
            inspector_id=inspector_id,
            action=payload.action,
            reason=payload.reason,
            final_decision=payload.final_decision,
            inspector_name=payload.inspector_name,
            notes=payload.notes,
            actor_role=auth.principal_role(principal),
        )
    except hitl.DecisionError as e:
        message = str(e)
        raise HTTPException(
            status_code=404 if "not found" in message else 422, detail=message
        )
    except Exception as e:
        # A sign-off that did not persist must not report success.
        database.write_audit(
            action="INSPECTION_DECISION_FAILED",
            actor=inspector_id,
            entity_type="inspection",
            entity_id=inspection_id,
            outcome="ERROR",
            details={"error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"Could not record decision: {e}")


@router.get("/inspections/{inspection_id}/decision")
def get_decision(inspection_id: str):
    """The current inspector decision, or 404 if the inspection is unreviewed."""
    decision = hitl.get_decision(inspection_id)
    if decision is None:
        if not database.inspection_exists(inspection_id):
            raise HTTPException(status_code=404, detail="Inspection not found")
        raise HTTPException(
            status_code=404, detail="No inspector decision recorded for this inspection"
        )
    return decision


@router.get("/inspections/{inspection_id}/audit")
def inspection_audit(
    inspection_id: str,
    principal: Dict[str, Any] = Depends(auth.require_role(auth.INSPECTOR)),
):
    """AI decision + every inspector decision + every logged action."""
    if not database.inspection_exists(inspection_id):
        raise HTTPException(status_code=404, detail="Inspection not found")
    return hitl.audit_trail(inspection_id)


@router.get("/review-queue")
def review_queue(
    limit: int = 100,
    sort_by: str = "confidence",
    principal: Dict[str, Any] = Depends(auth.require_role(auth.INSPECTOR)),
):
    """Inspections awaiting a human decision, least-confident first (PRD §19)."""
    items = hitl.pending_queue(limit=limit, sort_by=sort_by)
    for item in items:
        item["priority"] = hitl.queue_bucket(item.get("confidence"))
    return {"count": len(items), "sort_by": sort_by, "queue": items}


@router.get("/audit-log")
def audit_log(
    entity_id: Optional[str] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 200,
    principal: Dict[str, Any] = Depends(auth.require_role(auth.SUPERVISOR)),
):
    """The append-only audit trail. Supervisor and above only."""
    return {
        "entries": database.read_audit(
            entity_id=entity_id, actor=actor, action=action, limit=limit
        )
    }
