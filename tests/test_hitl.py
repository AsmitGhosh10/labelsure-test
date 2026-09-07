"""Human-in-the-loop review, audit trail and inspection repository search
(PRD §21, §27, §28, §30)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.app import database
from backend.app.services import hitl


def _other_verdict(ai_decision):
    """A compliance state that is genuinely different from the AI verdict."""
    for candidate in ("NON_COMPLIANT", "COMPLIANT", "MANUAL_REVIEW"):
        if candidate != ai_decision:
            return candidate
    raise AssertionError("no alternative verdict")


@pytest.fixture
def stored(sample_result):
    """A saved inspection, with any earlier decisions cleared."""
    database.init_db()
    inspection_id = database.save_inspection(sample_result)
    assert inspection_id, "the fixture inspection must persist"
    with database.SessionLocal() as session:
        session.query(database.InspectorDecisionRow).filter(
            database.InspectorDecisionRow.inspection_id == inspection_id
        ).delete()
        row = session.get(database.InspectionRow, inspection_id)
        row.inspector_status = "PENDING"
        row.final_decision = None
        session.commit()
    return sample_result


class TestRecordDecision:
    def test_accept_adopts_the_ai_verdict(self, stored):
        out = hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-42",
            action="ACCEPT",
            reason="Verified against the physical pack",
            inspector_name="A. Inspector",
        )
        assert out["agreement"] is True
        assert out["decision"]["final_decision"] == stored["decision"]
        assert out["decision"]["ai_decision"] == stored["decision"]
        assert out["decision"]["inspector_id"] == "insp-42"
        assert out["decision"]["timestamp"].endswith("Z")

    def test_override_records_a_different_verdict(self, stored):
        target = (
            "COMPLIANT" if stored["decision"] != "COMPLIANT" else "NON_COMPLIANT"
        )
        out = hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-42",
            action="OVERRIDE",
            final_decision=target,
            reason="MRP is printed on the base of the can, verified by hand",
        )
        assert out["agreement"] is False
        assert out["decision"]["action"] == "OVERRIDE"
        assert out["decision"]["final_decision"] == target

    def test_override_without_reason_is_rejected(self, stored):
        with pytest.raises(hitl.DecisionError, match="reason"):
            hitl.record_decision(
                inspection_id=stored["inspection_id"],
                inspector_id="insp-42",
                action="OVERRIDE",
                final_decision="COMPLIANT",
                reason="",
            )

    def test_override_reason_must_be_substantive(self, stored):
        with pytest.raises(hitl.DecisionError, match="explain"):
            hitl.record_decision(
                inspection_id=stored["inspection_id"],
                inspector_id="insp-42",
                action="OVERRIDE",
                final_decision="COMPLIANT",
                reason="ok",
            )

    def test_inspector_id_is_required(self, stored):
        with pytest.raises(hitl.DecisionError, match="Inspector ID"):
            hitl.record_decision(
                inspection_id=stored["inspection_id"],
                inspector_id="  ",
                action="ACCEPT",
                reason="fine",
            )

    def test_unknown_action_is_rejected(self, stored):
        with pytest.raises(hitl.DecisionError, match="ACCEPT"):
            hitl.record_decision(
                inspection_id=stored["inspection_id"],
                inspector_id="insp-1",
                action="MAYBE",
                reason="unsure about this one",
            )

    def test_unknown_inspection_is_rejected(self):
        with pytest.raises(hitl.DecisionError, match="not found"):
            hitl.record_decision(
                inspection_id="does-not-exist",
                inspector_id="insp-1",
                action="ACCEPT",
                reason="fine",
            )

    def test_override_to_the_same_verdict_is_recorded_as_agreement(self, stored):
        """The record must describe what actually happened, not what was typed."""
        out = hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-7",
            action="OVERRIDE",
            final_decision=stored["decision"],
            reason="Agreed after checking the base of the pack",
        )
        assert out["decision"]["action"] == "ACCEPT"
        assert out["agreement"] is True

    def test_accept_cannot_smuggle_in_a_different_verdict(self, stored):
        other = "COMPLIANT" if stored["decision"] != "COMPLIANT" else "NON_COMPLIANT"
        with pytest.raises(hitl.DecisionError, match="OVERRIDE"):
            hitl.record_decision(
                inspection_id=stored["inspection_id"],
                inspector_id="insp-1",
                action="ACCEPT",
                final_decision=other,
                reason="trying to sneak a verdict past ACCEPT",
            )

    def test_invalid_final_decision_is_rejected(self, stored):
        with pytest.raises(hitl.DecisionError, match="final_decision"):
            hitl.record_decision(
                inspection_id=stored["inspection_id"],
                inspector_id="insp-1",
                action="OVERRIDE",
                final_decision="PROBABLY_FINE",
                reason="this verdict is not a real compliance state",
            )


class TestDecisionHistory:
    def test_a_second_decision_supersedes_the_first(self, stored):
        first = hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-1",
            action="ACCEPT",
            reason="Looks right",
        )
        second = hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-2",
            action="OVERRIDE",
            final_decision=_other_verdict(stored["decision"]),
            reason="Net quantity font is below the required height",
        )
        assert second["supersedes"] == first["decision"]["decision_id"]

        current = hitl.get_decision(stored["inspection_id"])
        assert current["decision_id"] == second["decision"]["decision_id"]

        history = database.get_decision_history(stored["inspection_id"])
        assert len(history) == 2
        superseded = [h for h in history if h["superseded"]]
        assert len(superseded) == 1
        assert superseded[0]["reason"] == "Looks right"

    def test_history_is_append_only(self, stored):
        """Superseding must never delete the earlier record."""
        hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-1",
            action="ACCEPT",
            reason="First pass",
        )
        hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-1",
            action="ACCEPT",
            reason="Second pass",
        )
        reasons = [h["reason"] for h in database.get_decision_history(stored["inspection_id"])]
        assert "First pass" in reasons and "Second pass" in reasons

    def test_recording_a_decision_does_not_mutate_the_ai_result(self, stored):
        before = database.get_inspection(stored["inspection_id"])
        hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-1",
            action="OVERRIDE",
            final_decision=_other_verdict(stored["decision"]),
            reason="Physical check found the declaration missing entirely",
        )
        after = database.get_inspection(stored["inspection_id"])
        assert after["decision"] == before["decision"]
        assert after["rule_results"] == before["rule_results"]


class TestAuditTrail:
    def test_trail_pairs_the_ai_and_human_decisions(self, stored):
        hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-9",
            action="OVERRIDE",
            final_decision=_other_verdict(stored["decision"]),
            reason="Manufacturer address is incomplete on the physical pack",
        )
        trail = hitl.audit_trail(stored["inspection_id"])
        assert trail["ai_decision"] == stored["decision"]
        assert trail["current_decision"]["inspector_id"] == "insp-9"
        assert trail["ai_confidence"] is not None
        actions = {e["action"] for e in trail["audit_log"]}
        assert "INSPECTION_OVERRIDE" in actions

    def test_audit_entry_records_who_what_and_why(self, stored):
        hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-3",
            action="ACCEPT",
            reason="Confirmed on the shelf",
            actor_role="supervisor",
        )
        entries = database.read_audit(entity_id=stored["inspection_id"])
        entry = next(e for e in entries if e["action"] == "INSPECTION_ACCEPT")
        assert entry["actor"] == "insp-3"
        assert entry["actor_role"] == "supervisor"
        assert entry["details"]["reason"] == "Confirmed on the shelf"
        assert entry["timestamp"]


class TestQueueAndSearch:
    def test_pending_queue_excludes_reviewed_inspections(self, stored):
        inspection_id = stored["inspection_id"]
        assert any(i["inspection_id"] == inspection_id for i in hitl.pending_queue())
        hitl.record_decision(
            inspection_id=inspection_id,
            inspector_id="insp-1",
            action="ACCEPT",
            reason="Done",
        )
        assert not any(i["inspection_id"] == inspection_id for i in hitl.pending_queue())

    def test_queue_buckets_follow_the_prd_thresholds(self):
        assert hitl.queue_bucket(0.95).startswith("🟢")
        assert hitl.queue_bucket(0.80).startswith("🟡")
        assert hitl.queue_bucket(0.50).startswith("🔴")
        assert hitl.queue_bucket(None).startswith("🔴")

    def test_search_by_product_and_status(self, stored):
        hits = database.search_inspections(product="Crispy")
        assert any(h["inspection_id"] == stored["inspection_id"] for h in hits)
        by_status = database.search_inspections(status=stored["decision"])
        assert any(h["inspection_id"] == stored["inspection_id"] for h in by_status)

    def test_search_by_manufacturer(self, stored):
        hits = database.search_inspections(manufacturer="ABC")
        assert any(h["inspection_id"] == stored["inspection_id"] for h in hits)

    def test_search_by_date_range(self, stored):
        day = stored["timestamp"][:10]
        assert database.search_inspections(date_from=day, date_to=day)
        assert not database.search_inspections(date_from="2099-01-01")

    def test_search_by_nonexistent_product_is_empty(self):
        assert database.search_inspections(product="zzz-no-such-product") == []

    def test_search_sorting_by_confidence(self, stored):
        ascending = database.search_inspections(sort_by="confidence", descending=False)
        confidences = [h["confidence"] for h in ascending]
        assert confidences == sorted(confidences)

    def test_summary_exposes_the_search_columns(self, stored):
        hit = database.search_inspections(inspection_id=stored["inspection_id"])[0]
        for key in (
            "manufacturer", "brand", "product_category", "compliance_score",
            "violation_rule_ids", "inspector_status", "final_decision",
        ):
            assert key in hit

    def test_resaving_never_clobbers_a_recorded_decision(self, stored):
        hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-1",
            action="ACCEPT",
            reason="Signed off",
        )
        database.save_inspection(stored)  # e.g. a re-run of the same payload
        hit = database.search_inspections(inspection_id=stored["inspection_id"])[0]
        assert hit["inspector_status"] == "ACCEPT"


class TestStats:
    def test_stats_count_the_repository(self, stored):
        stats = database.inspection_stats()
        assert stats["total_inspections"] >= 1
        assert 0.0 <= stats["compliance_rate"] <= 100.0
        assert isinstance(stats["common_violations"], list)
        assert isinstance(stats["daily_trend"], list)

    def test_override_rate_tracks_human_disagreement(self, stored):
        hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="insp-1",
            action="OVERRIDE",
            final_decision=_other_verdict(stored["decision"]),
            reason="Physical inspection contradicted the automated reading",
        )
        stats = database.inspection_stats()
        assert stats["human_reviewed"] >= 1
        assert stats["overrides"] >= 1
        assert stats["override_rate"] > 0
        assert any(a["inspector_id"] == "insp-1" for a in stats["inspector_activity"])
