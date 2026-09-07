"""Compliance score (PRD §26)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.services.compliance_score import (
    CATEGORY_BUCKETS,
    compute_compliance_score,
)


def rule(rule_id, status, severity="HIGH", category="mrp"):
    return {
        "rule_id": rule_id,
        "status": status,
        "severity": severity,
        "source": {"category": category},
    }


class TestComplianceScore:
    def test_all_pass_scores_100(self):
        result = compute_compliance_score(
            [rule("R1", "PASS"), rule("R2", "PASS", category="net_quantity")]
        )
        assert result["score"] == 100.0
        assert result["grade"] == "A"

    def test_all_fail_scores_zero(self):
        result = compute_compliance_score([rule("R1", "FAIL"), rule("R2", "FAIL")])
        assert result["score"] == 0.0
        assert result["grade"] == "E"

    def test_manual_review_scores_half(self):
        result = compute_compliance_score([rule("R1", "MANUAL_REVIEW")])
        assert result["score"] == 50.0

    def test_not_applicable_is_excluded_from_the_denominator(self):
        """A package must not look compliant because most rules were out of
        scope - NOT_APPLICABLE is reported, never scored."""
        scored = compute_compliance_score([rule("R1", "PASS")])
        with_na = compute_compliance_score(
            [rule("R1", "PASS")] + [rule(f"N{i}", "NOT_APPLICABLE") for i in range(10)]
        )
        assert scored["score"] == with_na["score"] == 100.0
        assert with_na["not_assessable"] == 10
        assert with_na["scored_rules"] == 1

    def test_severity_weighting_penalises_critical_failures_more(self):
        critical_fail = compute_compliance_score(
            [rule("R1", "FAIL", severity="CRITICAL"), rule("R2", "PASS", severity="LOW")]
        )
        low_fail = compute_compliance_score(
            [rule("R1", "PASS", severity="CRITICAL"), rule("R2", "FAIL", severity="LOW")]
        )
        assert critical_fail["score"] < low_fail["score"]

    def test_no_assessable_rules_gives_no_score_not_zero(self):
        result = compute_compliance_score([rule("R1", "NOT_APPLICABLE")])
        assert result["score"] is None
        assert result["grade"] == "—"

    def test_empty_input(self):
        result = compute_compliance_score([])
        assert result["score"] is None
        assert result["counts"]["pass"] == 0

    def test_category_breakdown_separates_buckets(self):
        result = compute_compliance_score(
            [
                rule("R1", "PASS", category="mrp"),
                rule("R2", "FAIL", category="quantity_unit"),
                rule("R3", "PASS", category="declaration_legibility"),
            ]
        )
        by_bucket = {c["bucket"]: c for c in result["categories"]}
        assert by_bucket["mandatory_declarations"]["score"] == 100.0
        assert by_bucket["formatting"]["score"] == 0.0
        assert by_bucket["readability"]["score"] == 100.0

    def test_unknown_category_falls_into_other(self):
        result = compute_compliance_score(
            [rule("R1", "PASS", category="a_category_that_does_not_exist")]
        )
        by_bucket = {c["bucket"]: c for c in result["categories"]}
        assert by_bucket["other"]["rules_scored"] == 1

    def test_disclaimer_always_present(self):
        """PRD §26/§35: the score never ships without its caveat."""
        result = compute_compliance_score([rule("R1", "PASS")])
        assert "statutory inspection" in result["disclaimer"]
        assert result["system_role"] == "AI-assisted compliance screening"

    def test_real_pipeline_result_is_scored(self, sample_result):
        score = sample_result["compliance_score"]
        assert score["score"] is not None
        assert 0.0 <= score["score"] <= 100.0
        assert score["scored_rules"] > 0
        # every scored rule lands in exactly one bucket
        assert sum(c["rules_scored"] for c in score["categories"]) == score["scored_rules"]

    def test_every_ruleset_category_is_mapped(self):
        """A new rule category must be mapped deliberately, not silently
        dumped into 'other'."""
        import json
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent
            / "backend" / "app" / "rules" / "labelguard_rules_draft.json"
        )
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        categories = {r.get("category") for r in data["rules"] if r.get("category")}
        unmapped = categories - set(CATEGORY_BUCKETS)
        assert not unmapped, f"unmapped rule categories: {sorted(unmapped)}"
