"""Inspection history, inspector decisions, audit trail and user storage.

Dev default: SQLite file (`inspections.db`). Production: set DATABASE_URL
to a PostgreSQL DSN (e.g. postgresql://user:pass@host/legal_metrology).

Storage is best-effort for the *inspection* path: an inspection never fails
because the DB is down. It is **not** best-effort for the inspector decision
and audit paths - a sign-off that was not durably recorded must surface as an
error, never be silently swallowed (PRD §21/§30).
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    Integer,
    Text,
    Boolean,
    desc,
    func,
    inspect as sa_inspect,
    text as sa_text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite:///inspections.db"
)

# Module-level engine (import-time); fallback to sqlite if the configured
# DSN is unreachable at first use is handled by callers being best-effort.
is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

Base = declarative_base()

# Inspector decision vocabulary (PRD §21)
ACCEPT = "ACCEPT"
OVERRIDE = "OVERRIDE"
DECISION_ACTIONS = (ACCEPT, OVERRIDE)
FINAL_DECISIONS = ("COMPLIANT", "NON_COMPLIANT", "MANUAL_REVIEW")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class InspectionRow(Base):
    __tablename__ = "inspections"

    inspection_id = Column(String, primary_key=True)
    response_schema = Column(String)
    timestamp = Column(String)
    product_name = Column(String)
    decision = Column(String, index=True)
    decision_emoji = Column(String)
    confidence = Column(Float)
    surfaces_total = Column(Integer)
    surfaces_usable = Column(Integer)
    cylindrical_package = Column(Boolean)
    ruleset_id = Column(String)
    ruleset_version = Column(String)
    ruleset_verified = Column(Boolean)
    num_rules_pass = Column(Integer)
    num_rules_fail = Column(Integer)
    num_rules_review = Column(Integer)
    num_review_actions = Column(Integer)
    result_json = Column(Text)  # full frozen response payload

    # --- schema 1.1 search/dashboard columns (nullable, back-filled on save)
    brand = Column(String, index=True)
    manufacturer = Column(String, index=True)
    product_category = Column(String, index=True)
    compliance_score = Column(Float)
    violation_rule_ids = Column(Text)  # comma-separated FAIL rule ids
    inspector_status = Column(String, index=True)  # PENDING / ACCEPT / OVERRIDE
    final_decision = Column(String, index=True)  # inspector-confirmed verdict


class InspectorDecisionRow(Base):
    """The human sign-off on one inspection (PRD §21).

    The AI decision is stored alongside the inspector decision so the pair is
    always readable together - an audit must be able to answer "what did the
    machine say, what did the person say, and why did they differ?".
    """

    __tablename__ = "inspector_decisions"

    decision_id = Column(String, primary_key=True)
    inspection_id = Column(String, index=True, nullable=False)
    inspector_id = Column(String, index=True, nullable=False)
    inspector_name = Column(String)
    action = Column(String, nullable=False)  # ACCEPT / OVERRIDE
    ai_decision = Column(String)
    final_decision = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    notes = Column(Text)
    timestamp = Column(String, nullable=False)
    superseded = Column(Boolean, default=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "inspection_id": self.inspection_id,
            "inspector_id": self.inspector_id,
            "inspector_name": self.inspector_name,
            "action": self.action,
            "ai_decision": self.ai_decision,
            "final_decision": self.final_decision,
            "reason": self.reason,
            "notes": self.notes,
            "timestamp": self.timestamp,
            "superseded": bool(self.superseded),
        }


class AuditLogRow(Base):
    """Append-only audit trail (PRD §30).

    Rows are never updated or deleted by application code. `details_json`
    carries structured context but must never contain credentials or raw
    personal data - callers pass identifiers, not secrets.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, index=True, nullable=False)
    actor = Column(String, index=True)
    actor_role = Column(String)
    action = Column(String, index=True, nullable=False)
    entity_type = Column(String, index=True)
    entity_id = Column(String, index=True)
    outcome = Column(String)
    details_json = Column(Text)

    def to_dict(self) -> Dict[str, Any]:
        try:
            details = json.loads(self.details_json) if self.details_json else {}
        except (TypeError, ValueError):
            details = {}
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "actor_role": self.actor_role,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "outcome": self.outcome,
            "details": details,
        }


class UserRow(Base):
    """Local user account (PRD §30). Password is stored as a PBKDF2 hash."""

    __tablename__ = "users"

    username = Column(String, primary_key=True)
    full_name = Column(String)
    role = Column(String, nullable=False)  # inspector / supervisor / admin
    password_hash = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    iterations = Column(Integer, nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(String)

    def to_dict(self) -> Dict[str, Any]:
        """Never exposes the hash or salt."""
        return {
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "active": bool(self.active),
            "created_at": self.created_at,
        }


_initialised = False


def init_db() -> None:
    """Create tables and add any columns missing from an older database file."""
    global _initialised
    Base.metadata.create_all(engine)
    if not _initialised:
        _migrate_added_columns()
        _initialised = True


# Columns added after the first release, with their DDL types. SQLite cannot
# ALTER an existing table via SQLAlchemy metadata, so they are added here.
_ADDED_COLUMNS = {
    "inspections": {
        "brand": "VARCHAR",
        "manufacturer": "VARCHAR",
        "product_category": "VARCHAR",
        "compliance_score": "FLOAT",
        "violation_rule_ids": "TEXT",
        "inspector_status": "VARCHAR",
        "final_decision": "VARCHAR",
    }
}


def _migrate_added_columns() -> None:
    try:
        inspector = sa_inspect(engine)
        for table, columns in _ADDED_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            with engine.begin() as conn:
                for name, ddl_type in columns.items():
                    if name not in existing:
                        conn.execute(
                            sa_text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}")
                        )
    except Exception:
        # A failed migration must not stop the service starting; the affected
        # columns simply stay unavailable for search until it is fixed.
        pass


# ---------------------------------------------------------------------------
# Inspections
# ---------------------------------------------------------------------------


def _field_value(result: Dict[str, Any], name: str) -> Optional[str]:
    f = (result.get("extracted_fields") or {}).get(name) or {}
    value = f.get("value")
    return str(value) if value is not None else None


def save_inspection(result: Dict[str, Any]) -> Optional[str]:
    """Persist an inspection result (best-effort). Returns the id or None."""
    try:
        init_db()
        counts = {"PASS": 0, "FAIL": 0, "MANUAL_REVIEW": 0}
        violations = []
        for r in result.get("rule_results", []):
            if r.get("status") in counts:
                counts[r["status"]] += 1
            if r.get("status") == "FAIL":
                violations.append(r.get("rule_id", ""))
        coverage = result.get("coverage", {}) or {}
        ruleset = result.get("ruleset", {}) or {}
        conf = result.get("confidence", {}) or {}
        score = (result.get("compliance_score") or {}).get("score")
        category = (result.get("product_category") or {}).get("category")
        row = InspectionRow(
            inspection_id=result.get("inspection_id"),
            response_schema=result.get("response_schema"),
            timestamp=result.get("timestamp"),
            product_name=result.get("product_name"),
            decision=result.get("decision"),
            decision_emoji=result.get("decision_emoji"),
            confidence=float(conf.get("overall", 0.0)),
            surfaces_total=int(coverage.get("surfaces_total", 0) or 0),
            surfaces_usable=int(coverage.get("surfaces_usable", 0) or 0),
            cylindrical_package=bool(result.get("cylindrical_package", False)),
            ruleset_id=str(ruleset.get("id", "")),
            ruleset_version=str(ruleset.get("version", "")),
            ruleset_verified=bool(ruleset.get("verified", False)),
            num_rules_pass=counts["PASS"],
            num_rules_fail=counts["FAIL"],
            num_rules_review=counts["MANUAL_REVIEW"],
            num_review_actions=len(result.get("review_actions", []) or []),
            result_json=json.dumps(result),
            brand=_field_value(result, "brand"),
            manufacturer=_field_value(result, "manufacturer"),
            product_category=category,
            compliance_score=float(score) if score is not None else None,
            violation_rule_ids=",".join(v for v in violations if v),
            inspector_status="PENDING",
            final_decision=None,
        )
        with SessionLocal() as session:
            existing = session.get(InspectionRow, row.inspection_id)
            if existing is not None:
                # never clobber a recorded human decision on re-save
                row.inspector_status = existing.inspector_status
                row.final_decision = existing.final_decision
            session.merge(row)
            session.commit()
        return row.inspection_id
    except Exception:
        return None


def _summary(r: InspectionRow) -> Dict[str, Any]:
    return {
        "inspection_id": r.inspection_id,
        "timestamp": r.timestamp,
        "product_name": r.product_name,
        "brand": r.brand,
        "manufacturer": r.manufacturer,
        "product_category": r.product_category,
        "decision": r.decision,
        "decision_emoji": r.decision_emoji,
        "confidence": r.confidence,
        "compliance_score": r.compliance_score,
        "surfaces_total": r.surfaces_total,
        "surfaces_usable": r.surfaces_usable,
        "ruleset_id": r.ruleset_id,
        "ruleset_verified": r.ruleset_verified,
        "num_rules_pass": r.num_rules_pass,
        "num_rules_fail": r.num_rules_fail,
        "num_rules_review": r.num_rules_review,
        "num_review_actions": r.num_review_actions,
        "violation_rule_ids": [
            v for v in (r.violation_rule_ids or "").split(",") if v
        ],
        "inspector_status": r.inspector_status or "PENDING",
        "final_decision": r.final_decision,
    }


def list_inspections(limit: int = 50) -> List[Dict[str, Any]]:
    """Recent inspection summaries (no full payload)."""
    try:
        init_db()
        with SessionLocal() as session:
            rows = (
                session.query(InspectionRow)
                .order_by(desc(InspectionRow.timestamp))
                .limit(limit)
                .all()
            )
            return [_summary(r) for r in rows]
    except Exception:
        return []


SORT_FIELDS = {
    "timestamp": InspectionRow.timestamp,
    "confidence": InspectionRow.confidence,
    "compliance_score": InspectionRow.compliance_score,
    "product_name": InspectionRow.product_name,
    "manufacturer": InspectionRow.manufacturer,
    "decision": InspectionRow.decision,
}


def search_inspections(
    product: Optional[str] = None,
    manufacturer: Optional[str] = None,
    brand: Optional[str] = None,
    inspection_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    violation_rule_id: Optional[str] = None,
    inspector_status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    sort_by: str = "timestamp",
    descending: bool = True,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Search the inspection repository (PRD §28).

    All filters are AND-combined; text filters are case-insensitive substring
    matches. Dates compare against the stored ISO timestamp prefix, so
    ``date_from="2026-09-01"`` works without parsing.
    """
    try:
        init_db()
        with SessionLocal() as session:
            q = session.query(InspectionRow)
            if product:
                q = q.filter(InspectionRow.product_name.ilike(f"%{product}%"))
            if manufacturer:
                q = q.filter(InspectionRow.manufacturer.ilike(f"%{manufacturer}%"))
            if brand:
                q = q.filter(InspectionRow.brand.ilike(f"%{brand}%"))
            if inspection_id:
                q = q.filter(InspectionRow.inspection_id.ilike(f"%{inspection_id}%"))
            if status:
                q = q.filter(InspectionRow.decision == status)
            if category:
                q = q.filter(InspectionRow.product_category == category)
            if violation_rule_id:
                q = q.filter(
                    InspectionRow.violation_rule_ids.ilike(f"%{violation_rule_id}%")
                )
            if inspector_status:
                if inspector_status == "PENDING":
                    # Rows stored before the review columns existed have NULL
                    # here; an unreviewed inspection is pending either way.
                    q = q.filter(
                        (InspectionRow.inspector_status == "PENDING")
                        | (InspectionRow.inspector_status.is_(None))
                    )
                else:
                    q = q.filter(InspectionRow.inspector_status == inspector_status)
            if date_from:
                q = q.filter(InspectionRow.timestamp >= date_from)
            if date_to:
                # inclusive end-of-day for a bare date
                q = q.filter(InspectionRow.timestamp <= f"{date_to}T23:59:59")
            if min_confidence is not None:
                q = q.filter(InspectionRow.confidence >= min_confidence)
            if max_confidence is not None:
                q = q.filter(InspectionRow.confidence <= max_confidence)

            column = SORT_FIELDS.get(sort_by, InspectionRow.timestamp)
            q = q.order_by(desc(column) if descending else column)
            return [_summary(r) for r in q.limit(limit).all()]
    except Exception:
        return []


def get_inspection(inspection_id: str) -> Optional[Dict[str, Any]]:
    """Full stored response payload for one inspection."""
    try:
        init_db()
        with SessionLocal() as session:
            row = session.get(InspectionRow, inspection_id)
            if row is None:
                return None
            return json.loads(row.result_json)
    except Exception:
        return None


def inspection_exists(inspection_id: str) -> bool:
    try:
        init_db()
        with SessionLocal() as session:
            return session.get(InspectionRow, inspection_id) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Statistics (PRD §27 supervisor dashboard)
# ---------------------------------------------------------------------------


def inspection_stats(limit_common: int = 8) -> Dict[str, Any]:
    """Aggregate statistics across the whole repository."""
    try:
        init_db()
        with SessionLocal() as session:
            total = session.query(func.count(InspectionRow.inspection_id)).scalar() or 0
            if total == 0:
                return _empty_stats()

            by_decision = dict(
                session.query(InspectionRow.decision, func.count())
                .group_by(InspectionRow.decision)
                .all()
            )
            avg_conf = session.query(func.avg(InspectionRow.confidence)).scalar() or 0.0
            avg_score = (
                session.query(func.avg(InspectionRow.compliance_score))
                .filter(InspectionRow.compliance_score.isnot(None))
                .scalar()
            )
            by_category = dict(
                session.query(InspectionRow.product_category, func.count())
                .group_by(InspectionRow.product_category)
                .all()
            )
            by_inspector_status = dict(
                session.query(InspectionRow.inspector_status, func.count())
                .group_by(InspectionRow.inspector_status)
                .all()
            )

            # Violation frequency and per-manufacturer / per-day trends
            rows = session.query(
                InspectionRow.violation_rule_ids,
                InspectionRow.manufacturer,
                InspectionRow.timestamp,
                InspectionRow.decision,
            ).all()

            violations: Dict[str, int] = {}
            manufacturers: Dict[str, Dict[str, int]] = {}
            per_day: Dict[str, Dict[str, int]] = {}
            for vids, manufacturer, timestamp, decision in rows:
                for rule_id in (vids or "").split(","):
                    if rule_id:
                        violations[rule_id] = violations.get(rule_id, 0) + 1
                key = (manufacturer or "Unknown").strip()
                bucket = manufacturers.setdefault(
                    key, {"total": 0, "non_compliant": 0}
                )
                bucket["total"] += 1
                if decision == "NON_COMPLIANT":
                    bucket["non_compliant"] += 1
                day = (timestamp or "")[:10] or "unknown"
                day_bucket = per_day.setdefault(
                    day,
                    {"total": 0, "COMPLIANT": 0, "NON_COMPLIANT": 0, "MANUAL_REVIEW": 0},
                )
                day_bucket["total"] += 1
                if decision in day_bucket:
                    day_bucket[decision] += 1

            # Inspector activity from recorded decisions
            activity = dict(
                session.query(
                    InspectorDecisionRow.inspector_id, func.count()
                )
                .filter(InspectorDecisionRow.superseded.is_(False))
                .group_by(InspectorDecisionRow.inspector_id)
                .all()
            )
            overrides = (
                session.query(func.count(InspectorDecisionRow.decision_id))
                .filter(
                    InspectorDecisionRow.superseded.is_(False),
                    InspectorDecisionRow.action == OVERRIDE,
                )
                .scalar()
                or 0
            )
            reviewed = (
                session.query(func.count(InspectorDecisionRow.decision_id))
                .filter(InspectorDecisionRow.superseded.is_(False))
                .scalar()
                or 0
            )

            compliant = by_decision.get("COMPLIANT", 0)
            return {
                "total_inspections": total,
                "compliant": compliant,
                "non_compliant": by_decision.get("NON_COMPLIANT", 0),
                "manual_review": by_decision.get("MANUAL_REVIEW", 0),
                "compliance_rate": round(100.0 * compliant / total, 1),
                "average_confidence": round(float(avg_conf), 4),
                "average_compliance_score": (
                    round(float(avg_score), 1) if avg_score is not None else None
                ),
                "by_decision": by_decision,
                "by_category": {(k or "unknown"): v for k, v in by_category.items()},
                "by_inspector_status": {
                    (k or "PENDING"): v for k, v in by_inspector_status.items()
                },
                "common_violations": [
                    {"rule_id": rule_id, "count": count}
                    for rule_id, count in sorted(
                        violations.items(), key=lambda kv: -kv[1]
                    )[:limit_common]
                ],
                "manufacturer_trends": [
                    {
                        "manufacturer": name,
                        "inspections": data["total"],
                        "non_compliant": data["non_compliant"],
                        "non_compliance_rate": round(
                            100.0 * data["non_compliant"] / data["total"], 1
                        ),
                    }
                    for name, data in sorted(
                        manufacturers.items(), key=lambda kv: -kv[1]["total"]
                    )[:limit_common]
                ],
                "daily_trend": [
                    {"date": day, **counts}
                    for day, counts in sorted(per_day.items())
                ],
                "inspector_activity": [
                    {"inspector_id": name, "decisions": count}
                    for name, count in sorted(activity.items(), key=lambda kv: -kv[1])
                ],
                "human_reviewed": reviewed,
                "overrides": overrides,
                "override_rate": (
                    round(100.0 * overrides / reviewed, 1) if reviewed else 0.0
                ),
            }
    except Exception:
        return _empty_stats()


def _empty_stats() -> Dict[str, Any]:
    return {
        "total_inspections": 0,
        "compliant": 0,
        "non_compliant": 0,
        "manual_review": 0,
        "compliance_rate": 0.0,
        "average_confidence": 0.0,
        "average_compliance_score": None,
        "by_decision": {},
        "by_category": {},
        "by_inspector_status": {},
        "common_violations": [],
        "manufacturer_trends": [],
        "daily_trend": [],
        "inspector_activity": [],
        "human_reviewed": 0,
        "overrides": 0,
        "override_rate": 0.0,
    }


# ---------------------------------------------------------------------------
# Inspector decisions (PRD §21) - NOT best-effort: failures propagate
# ---------------------------------------------------------------------------


def save_inspector_decision(
    decision_id: str,
    inspection_id: str,
    inspector_id: str,
    action: str,
    final_decision: str,
    reason: str,
    ai_decision: Optional[str] = None,
    inspector_name: Optional[str] = None,
    notes: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a sign-off. Any earlier decision on the same inspection is kept
    but marked superseded - the audit trail is append-only.

    Raises on failure: a sign-off that was not stored must not look stored.
    """
    init_db()
    row = InspectorDecisionRow(
        decision_id=decision_id,
        inspection_id=inspection_id,
        inspector_id=inspector_id,
        inspector_name=inspector_name,
        action=action,
        ai_decision=ai_decision,
        final_decision=final_decision,
        reason=reason,
        notes=notes,
        timestamp=timestamp or _utc_now(),
        superseded=False,
    )
    with SessionLocal() as session:
        session.query(InspectorDecisionRow).filter(
            InspectorDecisionRow.inspection_id == inspection_id,
            InspectorDecisionRow.superseded.is_(False),
        ).update({InspectorDecisionRow.superseded: True})
        session.add(row)
        inspection = session.get(InspectionRow, inspection_id)
        if inspection is not None:
            inspection.inspector_status = action
            inspection.final_decision = final_decision
        session.commit()
    return row.to_dict()


def get_inspector_decision(inspection_id: str) -> Optional[Dict[str, Any]]:
    """The current (non-superseded) decision for one inspection."""
    try:
        init_db()
        with SessionLocal() as session:
            row = (
                session.query(InspectorDecisionRow)
                .filter(
                    InspectorDecisionRow.inspection_id == inspection_id,
                    InspectorDecisionRow.superseded.is_(False),
                )
                .order_by(desc(InspectorDecisionRow.timestamp))
                .first()
            )
            return row.to_dict() if row else None
    except Exception:
        return None


def get_decision_history(inspection_id: str) -> List[Dict[str, Any]]:
    """Every decision ever recorded for an inspection, oldest first."""
    try:
        init_db()
        with SessionLocal() as session:
            rows = (
                session.query(InspectorDecisionRow)
                .filter(InspectorDecisionRow.inspection_id == inspection_id)
                .order_by(InspectorDecisionRow.timestamp)
                .all()
            )
            return [r.to_dict() for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Audit log (PRD §30)
# ---------------------------------------------------------------------------


def write_audit(
    action: str,
    actor: Optional[str] = None,
    actor_role: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    outcome: str = "SUCCESS",
    details: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Append one audit entry. Never raises - auditing must not break a request,
    but a failed write returns None so the caller can react if it matters."""
    try:
        init_db()
        row = AuditLogRow(
            timestamp=_utc_now(),
            actor=actor,
            actor_role=actor_role,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            details_json=json.dumps(details or {}),
        )
        with SessionLocal() as session:
            session.add(row)
            session.commit()
            return row.id
    except Exception:
        return None


def read_audit(
    entity_id: Optional[str] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    try:
        init_db()
        with SessionLocal() as session:
            q = session.query(AuditLogRow)
            if entity_id:
                q = q.filter(AuditLogRow.entity_id == entity_id)
            if actor:
                q = q.filter(AuditLogRow.actor == actor)
            if action:
                q = q.filter(AuditLogRow.action == action)
            rows = q.order_by(desc(AuditLogRow.id)).limit(limit).all()
            return [r.to_dict() for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Users (PRD §30)
# ---------------------------------------------------------------------------


def upsert_user(
    username: str,
    role: str,
    password_hash: str,
    salt: str,
    iterations: int,
    full_name: Optional[str] = None,
    active: bool = True,
) -> Dict[str, Any]:
    init_db()
    with SessionLocal() as session:
        row = session.get(UserRow, username)
        if row is None:
            row = UserRow(username=username, created_at=_utc_now())
            session.add(row)
        row.role = role
        row.password_hash = password_hash
        row.salt = salt
        row.iterations = iterations
        row.full_name = full_name
        row.active = active
        session.commit()
        return row.to_dict()


def get_user_record(username: str) -> Optional[UserRow]:
    """Internal: returns the row *including* the hash. API layers must call
    ``to_dict()`` before exposing anything."""
    try:
        init_db()
        with SessionLocal() as session:
            return session.get(UserRow, username)
    except Exception:
        return None


def list_users() -> List[Dict[str, Any]]:
    try:
        init_db()
        with SessionLocal() as session:
            return [r.to_dict() for r in session.query(UserRow).all()]
    except Exception:
        return []


def count_users() -> int:
    try:
        init_db()
        with SessionLocal() as session:
            return session.query(func.count(UserRow.username)).scalar() or 0
    except Exception:
        return 0
