import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.app.services.confidence import (
    ConfidenceEngine,
    ConfidenceResult,
    DECISION_EMOJI,
)
from backend.app.services.rule_engine import (
    RuleResult,
    ComplianceDecision,
    PASS,
    FAIL,
    MANUAL_REVIEW,
)


def rr(rule_id, status, severity="HIGH"):
    return RuleResult(
        rule_id=rule_id,
        fields=["mrp"],
        status=status,
        severity=severity,
        requirement="req",
        reason="test",
    )


def make_fields(conf=0.90, count=5):
    return {
        f"field_{i}": {
            "field_name": f"field_{i}",
            "value": f"val{i}",
            "ocr_text": f"val{i}",
            "ocr_confidence": conf,
            "extraction_confidence": conf,
            "confidence_level": "HIGH",
            "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]],
            "reason": "",
            "line_index": 0,
        }
        for i in range(count)
    }


class TestConfidenceComputation:
    def setup_method(self):
        self.engine = ConfidenceEngine()

    def test_weights_sum_to_one(self):
        assert abs(sum(ConfidenceEngine.WEIGHTS.values()) - 1.0) < 1e-9

    def test_perfect_inputs_high_confidence(self):
        ocr = {"avg_confidence": 0.97, "texts": ["x"] * 10}
        quality = {"usable": True, "score": 95.0}
        rules = [rr(f"R{i}", PASS) for i in range(5)]
        conf = self.engine.compute(ocr, make_fields(0.92), quality, rules)
        assert conf.overall > 0.80
        assert conf.components["ocr"] == pytest.approx(0.97)
        assert conf.components["image_quality"] == pytest.approx(0.95)
        assert conf.components["rule_applicability"] == pytest.approx(1.0)

    def test_no_ocr_zero_component(self):
        conf = self.engine.compute(None, make_fields(), {"score": 90.0}, [])
        assert conf.components["ocr"] == 0.0

    def test_empty_ocr_zero_component(self):
        conf = self.engine.compute({"avg_confidence": 0.0, "texts": []}, make_fields(), {"score": 90.0}, [])
        assert conf.components["ocr"] == 0.0

    def test_no_detected_fields_extraction_zero(self):
        fields = make_fields()
        for f in fields.values():
            f["value"] = None
            f["extraction_confidence"] = 0.0
        conf = self.engine.compute({"avg_confidence": 0.95, "texts": ["x"]}, fields, {"score": 90.0}, [])
        assert conf.components["extraction"] == 0.0

    def test_bad_image_lowers_confidence(self):
        conf = self.engine.compute({"avg_confidence": 0.95, "texts": ["x"]}, make_fields(), {"score": 40.0}, [])
        assert conf.components["image_quality"] == pytest.approx(0.40)
        assert conf.overall < 0.85

    def test_rule_applicability_definitive_share(self):
        rules = [rr("R1", PASS), rr("R2", PASS), rr("R3", MANUAL_REVIEW), rr("R4", FAIL)]
        conf = self.engine.compute({"avg_confidence": 0.9, "texts": ["x"]}, make_fields(), {"score": 90.0}, rules)
        assert conf.components["rule_applicability"] == pytest.approx(0.75)

    def test_rule_applicability_no_results_neutral(self):
        conf = self.engine.compute({"avg_confidence": 0.9, "texts": ["x"]}, make_fields(), {"score": 90.0}, None)
        assert conf.components["rule_applicability"] == pytest.approx(0.5)

    def test_overall_within_bounds(self):
        conf = self.engine.compute({"avg_confidence": 1.0, "texts": ["x"]}, make_fields(1.0), {"score": 100.0}, [rr("R", PASS)])
        assert conf.overall <= 1.0

    def test_per_field_confidence_weakest_link(self):
        fields = {
            "a": {"value": "x", "ocr_confidence": 0.98, "extraction_confidence": 0.80},
            "b": {"value": None, "ocr_confidence": 0.0, "extraction_confidence": 0.0},
        }
        conf = self.engine.compute(None, fields, None, None)
        assert conf.per_field["a"] == pytest.approx(0.80)
        assert conf.per_field["b"] == 0.0


class TestDecisionFusion:
    def setup_method(self):
        self.engine = ConfidenceEngine(review_threshold=0.70)

    def _conf(self, overall):
        return ConfidenceResult(
            overall=overall,
            components={},
            per_field={},
            decision="MANUAL_REVIEW",
        )

    def test_non_compliant_with_strong_confidence_stands(self):
        compliance = ComplianceDecision(
            decision="NON_COMPLIANT", reasons=["MRP_001: missing"], failed_rules=["MRP_001"]
        )
        result = self.engine.fuse_decision(self._conf(0.92), compliance)
        assert result.decision == "NON_COMPLIANT"
        assert result.downgraded_from is None

    def test_non_compliant_with_weak_confidence_downgraded(self):
        """Guardrail: low confidence must never auto-FAIL."""
        compliance = ComplianceDecision(
            decision="NON_COMPLIANT", reasons=["MRP_001: missing"], failed_rules=["MRP_001"]
        )
        result = self.engine.fuse_decision(self._conf(0.55), compliance)
        assert result.decision == "MANUAL_REVIEW"
        assert result.downgraded_from == "NON_COMPLIANT"
        assert any("below" in r for r in result.decision_reasons)

    def test_compliant_with_weak_confidence_downgraded(self):
        """Guardrail: low confidence must never auto-PASS either."""
        compliance = ComplianceDecision(decision="COMPLIANT", reasons=["all pass"])
        result = self.engine.fuse_decision(self._conf(0.60), compliance)
        assert result.decision == "MANUAL_REVIEW"
        assert result.downgraded_from == "COMPLIANT"

    def test_manual_review_stays(self):
        compliance = ComplianceDecision(decision="MANUAL_REVIEW", reasons=["review"], review_rules=["X"])
        result = self.engine.fuse_decision(self._conf(0.50), compliance)
        assert result.decision == "MANUAL_REVIEW"
        assert result.downgraded_from is None

    def test_threshold_boundary_not_downgraded(self):
        compliance = ComplianceDecision(decision="NON_COMPLIANT", reasons=["x"], failed_rules=["X"])
        result = self.engine.fuse_decision(self._conf(0.70), compliance)
        assert result.decision == "NON_COMPLIANT"

    def test_decision_emoji_mapping(self):
        assert DECISION_EMOJI["COMPLIANT"] == "🟢"
        assert DECISION_EMOJI["NON_COMPLIANT"] == "🔴"
        assert DECISION_EMOJI["MANUAL_REVIEW"] == "🟡"
