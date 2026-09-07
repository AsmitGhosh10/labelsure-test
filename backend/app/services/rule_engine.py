import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

PASS = "PASS"
FAIL = "FAIL"
MANUAL_REVIEW = "MANUAL_REVIEW"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNVERIFIED = "UNVERIFIED"

VALID_SEVERITIES = ("HIGH", "MEDIUM", "LOW")

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "legal_metrology_rules.json"

PRICE_RANGE = (1.0, 50000.0)
QUANTITY_UNIT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|g|gm|gram|grams|l|ml|litre|liter|litres|liters|pcs|pieces|nos|units?)\b",
    re.IGNORECASE,
)
PRICE_NUMBER_PATTERN = re.compile(r"(\d{1,5}(?:\.\d{1,2})?)")
DATE_DIGIT_PATTERN = re.compile(r"\d")


@dataclass
class RuleResult:
    rule_id: str
    fields: List[str]
    status: str
    severity: str
    requirement: str
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    source: Dict[str, Any] = field(default_factory=dict)
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "fields": self.fields,
            "status": self.status,
            "severity": self.severity,
            "requirement": self.requirement,
            "reason": self.reason,
            "evidence": self.evidence,
            "source": self.source,
            "verified": self.verified,
        }


@dataclass
class ComplianceDecision:
    decision: str  # COMPLIANT / NON_COMPLIANT / MANUAL_REVIEW
    reasons: List[str] = field(default_factory=list)
    failed_rules: List[str] = field(default_factory=list)
    review_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": self.reasons,
            "failed_rules": self.failed_rules,
            "review_rules": self.review_rules,
        }


class RuleEngine:
    """Deterministic compliance rule engine.

    Evaluates JSON-defined rules against extracted fields. The engine makes
    no legal judgements of its own: it only checks field presence, extraction
    confidence and mechanical value validity. Absence-based FAIL decisions are
    suppressed when image quality is too poor to trust absence as evidence.
    """

    def __init__(
        self,
        rules_path: Optional[str] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
        enforce_verification: Optional[bool] = None,
    ):
        if rules is not None:
            self.rules = rules
            self.ruleset_verified = False
            self.enforce_verification = enforce_verification if enforce_verification is not None else False
            self.ruleset_meta = {}
        else:
            path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
            with open(path, "r") as f:
                data = json.load(f)
            self.rules = data.get("rules", [])
            self.ruleset_verified = bool(data.get("ruleset_verified", False))
            default_enforce = bool(data.get("enforce_verification", False))
            self.enforce_verification = (
                enforce_verification if enforce_verification is not None else default_enforce
            )
            meta = {k: v for k, v in data.items() if k != "rules"}
            self.ruleset_meta = meta

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        extracted_fields: Dict[str, Any],
        image_quality: Optional[Dict[str, Any]] = None,
        pointers: Optional[List[Dict[str, Any]]] = None,
    ) -> List[RuleResult]:
        results = []
        for rule in self.rules:
            results.append(
                self._evaluate_rule(rule, extracted_fields, image_quality, pointers)
            )
        return results

    def fuse(self, rule_results: List[RuleResult]) -> ComplianceDecision:
        failed = [r for r in rule_results if r.status == FAIL]
        review = [r for r in rule_results if r.status in (MANUAL_REVIEW, UNVERIFIED)]
        definitive = [r for r in rule_results if r.status in (PASS, FAIL)]

        if failed:
            reasons = []
            for r in failed:
                reasons.append(f"{r.rule_id} ({r.severity}): {r.reason}")
            return ComplianceDecision(
                decision="NON_COMPLIANT",
                reasons=reasons,
                failed_rules=[r.rule_id for r in failed],
                review_rules=[r.rule_id for r in review],
            )
        if review:
            reasons = [f"{r.rule_id}: {r.reason}" for r in review]
            return ComplianceDecision(
                decision="MANUAL_REVIEW",
                reasons=reasons,
                review_rules=[r.rule_id for r in review],
            )
        if definitive:
            return ComplianceDecision(decision="COMPLIANT", reasons=["All applicable rules passed"])
        return ComplianceDecision(
            decision="MANUAL_REVIEW",
            reasons=["No rules were evaluated for this inspection"],
        )

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def _evaluate_rule(
        self,
        rule: Dict[str, Any],
        fields: Dict[str, Any],
        image_quality: Optional[Dict[str, Any]],
        pointers: Optional[List[Dict[str, Any]]] = None,
    ) -> RuleResult:
        rule_id = rule.get("rule_id", "UNKNOWN")
        rule_fields = rule.get("fields", [])
        severity = rule.get("severity", "MEDIUM")
        requirement = rule.get("requirement", "")

        base = RuleResult(
            rule_id=rule_id,
            fields=rule_fields,
            status=MANUAL_REVIEW,
            severity=severity,
            requirement=requirement,
            reason="",
            source=rule.get("source", {}),
            verified=bool(rule.get("verified", False)),
        )

        # Guardrail: unverified rules never produce PASS/FAIL in verified mode
        if self.enforce_verification and not rule.get("verified", False):
            base.status = UNVERIFIED
            base.reason = "Rule pending verification against official document"
            return base

        # Applicability
        applicable, reason = self._check_applicability(rule, fields)
        if applicable is False:
            base.status = NOT_APPLICABLE
            base.reason = reason
            return base
        if applicable is None:
            base.status = MANUAL_REVIEW
            base.reason = reason
            return base

        # Evaluate by rule type
        rule_type = rule.get("rule_type", "MANDATORY")
        if rule_type in ("MANDATORY", "CONDITIONAL"):
            # CONDITIONAL rules reach here only when the applicability gate passed
            return self._evaluate_mandatory(
                base, rule, rule_fields[0] if rule_fields else None, fields, image_quality, pointers
            )
        if rule_type == "MANDATORY_ANY":
            return self._evaluate_mandatory_any(
                base, rule, rule_fields, fields, image_quality, pointers
            )
        # Unknown type -> safe default
        base.reason = f"Unknown rule_type '{rule_type}'"
        return base

    def _check_applicability(
        self, rule: Dict[str, Any], fields: Dict[str, Any]
    ) -> Tuple[Optional[bool], str]:
        applicability = rule.get("applicability", {"condition": "ALWAYS"})
        condition = applicability.get("condition", "ALWAYS")

        if condition == "ALWAYS":
            return True, ""

        if condition == "ORIGIN_NOT_INDIA":
            origin = self._field(fields, applicability.get("depends_on", "country_of_origin"))
            if origin is None or origin.get("value") is None:
                return None, "Country of origin not detected - cannot determine applicability"
            value = str(origin.get("value", ""))
            if re.search(r"india", value, re.IGNORECASE):
                return False, "Country of origin is India - importer declaration not required"
            return True, f"Country of origin detected as '{value}' - importer declaration required"

        if condition == "FIELD_PRESENT":
            dep_field = self._field(fields, applicability.get("depends_on", rule["fields"][0]))
            if dep_field is None or dep_field.get("value") is None:
                return False, "Field not detected - applicability depends on product type (needs RAG/manual context)"
            return True, ""

        return None, f"Unknown applicability condition '{condition}'"

    def _evaluate_mandatory(
        self,
        base: RuleResult,
        rule: Dict[str, Any],
        field_name: Optional[str],
        fields: Dict[str, Any],
        image_quality: Optional[Dict[str, Any]],
        pointers: Optional[List[Dict[str, Any]]] = None,
    ) -> RuleResult:
        if field_name is None:
            base.reason = "Rule defines no field"
            return base

        f = self._field(fields, field_name)
        value = f.get("value") if f else None
        level = (f.get("confidence_level") if f else None) or "MISSING"

        base.evidence = self._evidence(f)

        if value is None:
            pointer = self._matching_pointer(field_name, pointers)
            if self._quality_blocks_absence_fail(image_quality):
                base.status = MANUAL_REVIEW
                base.reason = (
                    f"'{field_name}' not detected and image quality is insufficient to trust "
                    "absence as evidence"
                )
            elif pointer is not None:
                base.status = MANUAL_REVIEW
                base.reason = (
                    f"'{field_name}' not detected on captured surfaces, but the label "
                    f"states this information is located elsewhere on the package "
                    f"(\"{pointer['text'][:80]}\" on '{pointer.get('image', '?')}') - "
                    "verify that surface"
                )
                base.evidence = {"detected": False, "reference_pointer": pointer}
            else:
                base.status = FAIL
                base.reason = f"'{field_name}' declaration not found on the captured package surface"
            return base

        if level == "LOW":
            base.status = MANUAL_REVIEW
            base.reason = f"'{field_name}' detected but extraction confidence is LOW"
            return base

        validation = rule.get("validation", "PRESENT")
        valid, reason = self._validate_value(validation, value)
        if valid:
            base.status = PASS
            base.reason = f"'{field_name}' declared"
            if reason:
                base.reason += f" ({reason})"
        else:
            base.status = MANUAL_REVIEW
            base.reason = f"'{field_name}' declared but value could not be validated: {reason}"
        return base

    def _evaluate_mandatory_any(
        self,
        base: RuleResult,
        rule: Dict[str, Any],
        rule_fields: List[str],
        fields: Dict[str, Any],
        image_quality: Optional[Dict[str, Any]],
        pointers: Optional[List[Dict[str, Any]]] = None,
    ) -> RuleResult:
        present, low, evidence = [], [], {}
        for name in rule_fields:
            f = self._field(fields, name)
            if f is None or f.get("value") is None:
                continue
            level = f.get("confidence_level") or "MISSING"
            evidence[name] = self._evidence(f)
            if level == "LOW":
                low.append(name)
            else:
                present.append(name)

        base.evidence = evidence

        if present:
            base.status = PASS
            base.reason = f"Declared via: {', '.join(present)}"
            return base

        if low:
            base.status = MANUAL_REVIEW
            base.reason = f"Only weak (LOW confidence) candidates found for: {', '.join(low)}"
            return base

        if self._quality_blocks_absence_fail(image_quality):
            base.status = MANUAL_REVIEW
            base.reason = (
                f"None of {', '.join(rule_fields)} detected and image quality is insufficient "
                "to trust absence as evidence"
            )
        else:
            pointer = None
            for name in rule_fields:
                pointer = self._matching_pointer(name, pointers)
                if pointer is not None:
                    break
            if pointer is not None:
                base.status = MANUAL_REVIEW
                base.reason = (
                    f"None of {', '.join(rule_fields)} detected on captured surfaces, but the "
                    f"label states this information is located elsewhere on the package "
                    f"(\"{pointer['text'][:80]}\" on '{pointer.get('image', '?')}') - "
                    "verify that surface"
                )
                base.evidence = {"detected": False, "reference_pointer": pointer}
            else:
                base.status = FAIL
                base.reason = f"None of {', '.join(rule_fields)} found on the captured package surface"
        return base

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_value(self, validation: str, value: str) -> Tuple[bool, str]:
        if validation == "PRESENT":
            return True, ""
        if validation == "PRESENT_AND_VALID_PRICE":
            m = PRICE_NUMBER_PATTERN.search(str(value))
            if not m:
                return False, "no parseable price in declared value"
            try:
                price = float(m.group(1))
            except ValueError:
                return False, "price value not numeric"
            lo, hi = PRICE_RANGE
            if not (lo <= price <= hi):
                return False, f"price {price} outside plausible range {lo}-{hi}"
            return True, f"price {price}"
        if validation == "PRESENT_AND_VALID_UNIT":
            if QUANTITY_UNIT_PATTERN.search(str(value)):
                return True, ""
            return False, "no valid quantity unit (g/kg/ml/l/pcs) in declared value"
        if validation == "VALID_DATE":
            if DATE_DIGIT_PATTERN.search(str(value)):
                return True, ""
            return False, "no determinate date in declared value"
        return False, f"unknown validation '{validation}'"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # Fields typically printed on the base/lid of cylindrical packages -
    # a generic 'see base of can' pointer softens absence for these
    BASE_LOCATION_FIELDS = {
        "mrp",
        "batch_number",
        "manufacturing_date",
        "packing_date",
        "best_before",
    }
    BASE_LOCATIONS = {"base", "bottom", "lid", "cap", "neck"}

    @staticmethod
    def _matching_pointer(
        field_name: str, pointers: Optional[List[Dict[str, Any]]]
    ) -> Optional[Dict[str, Any]]:
        """Find a package reference pointer that says this field's information
        lives on another (possibly uncaptured) part of the package."""
        if not pointers:
            return None
        for p in pointers:
            fields_hinted = p.get("fields") or []
            if field_name in fields_hinted:
                return p
            if (
                p.get("location") in RuleEngine.BASE_LOCATIONS
                and field_name in RuleEngine.BASE_LOCATION_FIELDS
            ):
                return p
        return None

    @staticmethod
    def _field(fields: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
        f = fields.get(name)
        if f is None:
            return None
        if isinstance(f, dict):
            return f
        # ExtractedField dataclass support
        try:
            return {
                "value": getattr(f, "value", None),
                "ocr_text": getattr(f, "ocr_text", ""),
                "ocr_confidence": getattr(f, "ocr_confidence", 0.0),
                "extraction_confidence": getattr(f, "extraction_confidence", 0.0),
                "confidence_level": getattr(f, "confidence_level", "MISSING"),
                "bbox": getattr(f, "bbox", []),
                "reason": getattr(f, "reason", ""),
            }
        except Exception:
            return None

    @staticmethod
    def _evidence(f: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not f:
            return {"detected": False}
        return {
            "detected": True,
            "value": f.get("value"),
            "ocr_text": f.get("ocr_text", ""),
            "ocr_confidence": f.get("ocr_confidence", 0.0),
            "extraction_confidence": f.get("extraction_confidence", 0.0),
            "confidence_level": f.get("confidence_level", "MISSING"),
            "bbox": f.get("bbox", []),
        }

    @staticmethod
    def _quality_blocks_absence_fail(image_quality: Optional[Dict[str, Any]]) -> bool:
        if not image_quality:
            return False
        if not image_quality.get("usable", True):
            return True
        score = image_quality.get("score", 100.0)
        return isinstance(score, (int, float)) and score < 60.0
