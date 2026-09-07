"""Human-in-the-loop review (PRD §21).

The AI never has the last word. Every inspection can be closed by a named
inspector who either **accepts** the automated finding or **overrides** it,
always with a reason, and the pair (AI decision, inspector decision) is
stored together with an append-only audit entry.

Rules enforced here:

* An override must state a reason - "because I said so" is not an audit
  trail. Accepting also requires a reason, but a short one is fine.
* The inspector's final decision must be one of the three compliance states.
* Overriding to the same verdict the AI produced is an ACCEPT, not an
  OVERRIDE, and is corrected rather than rejected - the record must describe
  what actually happened.
* Recording a decision never mutates the stored inspection payload. The AI
  result stays exactly as produced; the human decision sits alongside it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app import database
from backend.app.database import ACCEPT, FINAL_DECISIONS, OVERRIDE

MIN_OVERRIDE_REASON_CHARS = 10


class DecisionError(ValueError):
    """Raised when a sign-off is not valid and must not be recorded."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_decision(
    inspection_id: str,
    inspector_id: str,
    action: str,
    reason: str,
    final_decision: Optional[str] = None,
    inspector_name: Optional[str] = None,
    notes: Optional[str] = None,
    actor_role: Optional[str] = None,
) -> Dict[str, Any]:
    """Record an inspector's accept/override on one inspection.

    Returns the stored decision plus the AI decision it responds to. Raises
    :class:`DecisionError` for anything that must not be persisted.
    """
    inspection = database.get_inspection(inspection_id)
    if inspection is None:
        raise DecisionError(f"Inspection {inspection_id} not found")

    inspector_id = (inspector_id or "").strip()
    if not inspector_id:
        raise DecisionError("Inspector ID is required - decisions are attributable")

    action = (action or "").strip().upper()
    if action not in (ACCEPT, OVERRIDE):
        raise DecisionError(f"action must be {ACCEPT} or {OVERRIDE}, got '{action}'")

    reason = (reason or "").strip()
    if not reason:
        raise DecisionError("A reason is required for every inspector decision")

    ai_decision = inspection.get("decision")

    if action == ACCEPT:
        # Accepting means adopting the AI verdict as-is.
        if final_decision and final_decision != ai_decision:
            raise DecisionError(
                f"ACCEPT adopts the AI decision ({ai_decision}); to record "
                f"{final_decision} use action={OVERRIDE}"
            )
        final = ai_decision
    else:
        final = (final_decision or "").strip().upper()
        if final not in FINAL_DECISIONS:
            raise DecisionError(
                f"final_decision must be one of {', '.join(FINAL_DECISIONS)}"
            )
        if final == ai_decision:
            # Same verdict, so this is agreement however it was submitted.
            action = ACCEPT
        elif len(reason) < MIN_OVERRIDE_REASON_CHARS:
            raise DecisionError(
                "An override reason must explain the disagreement "
                f"(at least {MIN_OVERRIDE_REASON_CHARS} characters)"
            )

    if final not in FINAL_DECISIONS:
        # AI decision itself was absent/unknown - the human must state one.
        raise DecisionError(
            "This inspection has no automated decision to accept; record an "
            f"{OVERRIDE} with an explicit final_decision"
        )

    decision_id = str(uuid.uuid4())
    timestamp = _now()
    previous = database.get_inspector_decision(inspection_id)

    stored = database.save_inspector_decision(
        decision_id=decision_id,
        inspection_id=inspection_id,
        inspector_id=inspector_id,
        action=action,
        final_decision=final,
        reason=reason,
        ai_decision=ai_decision,
        inspector_name=inspector_name,
        notes=notes,
        timestamp=timestamp,
    )

    database.write_audit(
        action=f"INSPECTION_{action}",
        actor=inspector_id,
        actor_role=actor_role or "inspector",
        entity_type="inspection",
        entity_id=inspection_id,
        outcome="SUCCESS",
        details={
            "ai_decision": ai_decision,
            "final_decision": final,
            "reason": reason,
            "decision_id": decision_id,
            "supersedes": previous.get("decision_id") if previous else None,
        },
    )

    return {
        "decision": stored,
        "ai_decision": ai_decision,
        "agreement": action == ACCEPT,
        "supersedes": previous.get("decision_id") if previous else None,
    }


def get_decision(inspection_id: str) -> Optional[Dict[str, Any]]:
    return database.get_inspector_decision(inspection_id)


def audit_trail(inspection_id: str) -> Dict[str, Any]:
    """The full trail for one inspection: what the AI decided, what every
    inspector decided, and every logged action."""
    inspection = database.get_inspection(inspection_id)
    return {
        "inspection_id": inspection_id,
        "ai_decision": (inspection or {}).get("decision"),
        "ai_confidence": ((inspection or {}).get("confidence") or {}).get("overall"),
        "ai_timestamp": (inspection or {}).get("timestamp"),
        "inspector_decisions": database.get_decision_history(inspection_id),
        "current_decision": database.get_inspector_decision(inspection_id),
        "audit_log": database.read_audit(entity_id=inspection_id),
    }


def pending_queue(
    limit: int = 100, sort_by: str = "confidence"
) -> List[Dict[str, Any]]:
    """Inspections awaiting a human decision, hardest-first by default.

    Sorting ascending by confidence puts the least trustworthy results at the
    top of the queue, which is what PRD §19 asks for.
    """
    descending = sort_by not in ("confidence", "compliance_score")
    return database.search_inspections(
        inspector_status="PENDING",
        sort_by=sort_by,
        descending=descending,
        limit=limit,
    )


def queue_bucket(confidence: Optional[float], high: float = 0.90, review: float = 0.70) -> str:
    """PRD §17 review tier for a confidence value."""
    if confidence is None:
        return "🔴 PRIORITY REVIEW"
    if confidence >= high:
        return "🟢 AUTO ACCEPT"
    if confidence >= review:
        return "🟡 REVIEW"
    return "🔴 PRIORITY REVIEW"
