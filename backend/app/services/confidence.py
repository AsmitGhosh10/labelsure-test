from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from backend.app.services.rule_engine import (
    RuleResult,
    ComplianceDecision,
    PASS,
    FAIL,
    MANUAL_REVIEW,
    NOT_APPLICABLE,
    UNVERIFIED,
)

COMPLIANT = "COMPLIANT"
NON_COMPLIANT = "NON_COMPLIANT"
MANUAL_REVIEW_DECISION = "MANUAL_REVIEW"

DECISION_EMOJI = {
    COMPLIANT: "🟢",
    NON_COMPLIANT: "🔴",
    MANUAL_REVIEW_DECISION: "🟡",
}


@dataclass
class ConfidenceResult:
    overall: float
    components: Dict[str, float]
    per_field: Dict[str, float]
    decision: str
    decision_reasons: List[str] = field(default_factory=list)
    downgraded_from: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": round(self.overall, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "per_field": {k: round(v, 4) for k, v in self.per_field.items()},
            "decision": self.decision,
            "decision_reasons": self.decision_reasons,
            "downgraded_from": self.downgraded_from,
        }


class ConfidenceEngine:
    """Fuses OCR, extraction, image-quality and rule-applicability signals into
    a single confidence score, and guards the final decision.

    Guardrails:
    - A violation (NON_COMPLIANT) with weak overall confidence is downgraded to
      MANUAL_REVIEW - low confidence must never auto-FAIL.
    - A clean result (COMPLIANT) with weak overall confidence is downgraded to
      MANUAL_REVIEW - low confidence must never auto-PASS either.
    """

    WEIGHTS = {
        "ocr": 0.4,
        "extraction": 0.3,
        "image_quality": 0.2,
        "rule_applicability": 0.1,
    }

    def __init__(self, review_threshold: float = 0.70, high_threshold: float = 0.90):
        self.review_threshold = review_threshold
        self.high_threshold = high_threshold

    # ------------------------------------------------------------------
    # Confidence computation
    # ------------------------------------------------------------------

    def compute(
        self,
        ocr_result: Optional[Dict[str, Any]],
        extracted_fields: Dict[str, Any],
        image_quality: Optional[Dict[str, Any]],
        rule_results: Optional[List[RuleResult]] = None,
    ) -> ConfidenceResult:
        components = {
            "ocr": self._ocr_component(ocr_result),
            "extraction": self._extraction_component(extracted_fields),
            "image_quality": self._image_quality_component(image_quality),
            "rule_applicability": self._rule_applicability_component(rule_results),
        }

        overall = sum(self.WEIGHTS[k] * v for k, v in components.items())
        overall = max(0.0, min(1.0, overall))

        return ConfidenceResult(
            overall=overall,
            components=components,
            per_field=self._per_field_confidence(extracted_fields),
            decision=MANUAL_REVIEW_DECISION,
        )

    # ------------------------------------------------------------------
    # Decision fusion
    # ------------------------------------------------------------------

    def fuse_decision(
        self,
        confidence: ConfidenceResult,
        compliance: ComplianceDecision,
    ) -> ConfidenceResult:
        decision = compliance.decision
        reasons = list(compliance.reasons)
        downgraded_from = None

        if confidence.overall < self.review_threshold and decision in (COMPLIANT, NON_COMPLIANT):
            downgraded_from = decision
            decision = MANUAL_REVIEW_DECISION
            reasons.append(
                f"Evidence confidence {confidence.overall:.0%} is below the "
                f"{self.review_threshold:.0%} review threshold - routed to manual review"
            )

        confidence.decision = decision
        confidence.decision_reasons = reasons
        confidence.downgraded_from = downgraded_from
        return confidence

    # ------------------------------------------------------------------
    # Components
    # ------------------------------------------------------------------

    @staticmethod
    def _ocr_component(ocr_result: Optional[Dict[str, Any]]) -> float:
        if not ocr_result:
            return 0.0
        avg = ocr_result.get("avg_confidence", 0.0)
        n_lines = len(ocr_result.get("texts", []))
        if n_lines == 0:
            return 0.0
        return max(0.0, min(1.0, float(avg)))

    @staticmethod
    def _extraction_component(extracted_fields: Dict[str, Any]) -> float:
        confs = []
        for f in extracted_fields.values():
            value = f.get("value") if isinstance(f, dict) else getattr(f, "value", None)
            if value is None:
                continue
            ext = f.get("extraction_confidence") if isinstance(f, dict) else getattr(f, "extraction_confidence", 0.0)
            confs.append(max(0.0, min(1.0, float(ext))))
        if not confs:
            return 0.0
        return sum(confs) / len(confs)

    @staticmethod
    def _image_quality_component(image_quality: Optional[Dict[str, Any]]) -> float:
        if not image_quality:
            return 0.0
        score = image_quality.get("score", 0.0)
        return max(0.0, min(1.0, float(score) / 100.0))

    @staticmethod
    def _rule_applicability_component(rule_results: Optional[List[RuleResult]]) -> float:
        """Share of evaluated rules that reached a definitive (PASS/FAIL) status."""
        if not rule_results:
            return 0.5  # neutral: no rule information available
        evaluated = [
            r for r in rule_results if r.status in (PASS, FAIL, MANUAL_REVIEW, UNVERIFIED)
        ]
        if not evaluated:
            return 0.5  # all NOT_APPLICABLE - no signal either way
        definitive = [r for r in evaluated if r.status in (PASS, FAIL)]
        return len(definitive) / len(evaluated)

    @staticmethod
    def _per_field_confidence(extracted_fields: Dict[str, Any]) -> Dict[str, float]:
        per_field = {}
        for name, f in extracted_fields.items():
            if isinstance(f, dict):
                value = f.get("value")
                ocr_c = f.get("ocr_confidence", 0.0)
                ext_c = f.get("extraction_confidence", 0.0)
            else:
                value = getattr(f, "value", None)
                ocr_c = getattr(f, "ocr_confidence", 0.0)
                ext_c = getattr(f, "extraction_confidence", 0.0)
            if value is None:
                per_field[name] = 0.0
            else:
                per_field[name] = max(0.0, min(1.0, min(float(ocr_c), float(ext_c))))
        return per_field
