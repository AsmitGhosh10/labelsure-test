"""LabelGuard deterministic rule checker.

Evaluates the machine-readable Legal Metrology (Packaged Commodities)
Rules, 2011 ruleset (`labelguard_rules_draft.json`) against merged field
evidence. Interface-compatible with RuleEngine (evaluate/fuse produce the
same RuleResult / ComplianceDecision shapes), so the pipeline, confidence
engine and report generator work unchanged.

Honesty model (per the ruleset's engine_policy):
- Rules that cannot be evaluated from package images (physical measurement,
  schedule lookup, commodity-type conditionals, dealer/export/ad rules)
  return NOT_APPLICABLE with an explicit scope reason - never a fake verdict.
- The Rule 26 exemption gate is applied BEFORE declaration rules.
- Rule 12(6) is a content check: misleading quantity wording FAILs.
- Absence-based FAILs respect the quality guard and package reference
  pointers (same semantics as the previous engine).
"""

import json
import re
from pathlib import Path
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

DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parent.parent / "rules" / "labelguard_rules_draft.json"
)

PRICE_NUMBER_PATTERN = re.compile(r"(\d{1,5}(?:\.\d{1,2})?)")
PRICE_RANGE = (1.0, 50000.0)
QTY_VALUE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|g|gm|ml|l|cm|m|pcs?)\b", re.IGNORECASE
)
MONTH_YEAR_RES = [
    re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"),
    re.compile(r"\d{1,2}[/\-.]\d{4}"),  # month/year - Rule 6(1)(d)'s own form
    re.compile(r"\d{1,2}[A-Za-z]{3}\d{2,4}"),
    re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}"),
    re.compile(r"[A-Za-z]{3,9}\s*[\-]?\s*\d{2,4}"),
]
MONTHS_RE = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|month)", re.IGNORECASE
)
# Rule 12(6) bans the listed phrases "or equivalent" - common abbreviations
MISLEADING_ABBREVIATIONS = {
    "minimum": [r"\bmin\b", r"\bmin\."],
    "not less than": [r"\bn\.?l\.?t\b", r"\bnot\s*<\s*\d"],
    "average": [r"\bavg\b", r"\bavg\."],
    "approximately": [r"\bapprox\b", r"\bapprox\."],
    "about": [r"\babt\b"],
}
BASE_LOCATIONS = {"base", "bottom", "lid", "cap", "neck"}
BASE_LOCATION_FIELDS = {
    "mrp",
    "batch_number",
    "manufacturing_date",
    "packing_date",
    "best_before",
    "net_quantity",
}

# Rule categories exempted by the Rule 26 gate
DECLARATION_CATEGORIES = {
    "manufacturer_details",
    "commodity_identity",
    "net_quantity",
    "date_declaration",
    "mrp",
    "consumer_contact",
}
# Categories still required under the Rule 26 proviso (10-20 g/ml)
PARTIAL_REQUIRED_CATEGORIES = {"mrp", "net_quantity"}

# Validation types that cannot be evaluated from package images
SCOPE_NA_VALIDATION_TYPES = {
    "SCHEDULE_LOOKUP": "requires the Second Schedule standard pack sizes and commodity identification",
    "VISUAL_RULE": "requires physical/visual inspection of the package",
    "CONDITIONAL_DECLARATION_CHECK": "depends on package component structure that is not visible in photos",
    "MEASUREMENT_TABLE_LOOKUP": "requires physical scale - numeral height in mm cannot be measured from images without a scale reference",
    "LOCATION_AND_SPACING": "principal display panel and spacing require physical package inspection",
    "CONDITIONAL_WRAPPER_CHECK": "outside wrapper presence cannot be determined from captured surfaces",
    "MEASUREMENT_RULE": "requires physical weighing (tare exclusion)",
    "CONDITIONAL_COMPLIANCE_GATE": "requires export/re-packing context not available from images",
    "ADVERTISEMENT_CHECK": "applies to advertisements, not package images",
    "PACKAGE_COMPLIANCE_GATE": "binds the dealer/importer, not the package label",
    "CONDITIONAL_CONTAINER_RULE": "depends on commodity type (container goods)",
    "CONDITIONAL_FIELD_PRESENCE": "depends on commodity type (dimensions/sheets) which cannot be determined from images alone",
    "EXEMPTION_LOOKUP": "evaluated as the Rule 26 exemption gate before declaration rules",
}

# Specific rules outside automated image-inspection scope regardless of type
SCOPE_NA_RULE_IDS = {
    "PC2011-R24-001": "wholesale vs retail package cannot be determined from captured surfaces",
    "PC2011-R25-001": "export-package status cannot be determined from captured surfaces",
    "PC2011-R18-001": "binds the wholesale/retail dealer, not the package label",
    "PC2011-R31-001": "applies to advertisements, not package images",
}


class LabelGuardEngine:
    """Deterministic checker for the LabelGuard LM(PC)R 2011 ruleset."""

    def __init__(
        self,
        rules_path: Optional[str] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
        enforce_verification: bool = False,
    ):
        if rules is not None:
            self.rules = rules
            self.meta = {}
            self.ruleset_verified = False
            self.enforce_verification = enforce_verification
        else:
            path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
            with open(path, "r") as f:
                data = json.load(f)
            self.rules = data.get("rules", [])
            self.meta = {k: v for k, v in data.items() if k != "rules"}
            # uniform attribute name with the legacy RuleEngine
            self.ruleset_meta = self.meta
            self.ruleset_verified = all(r.get("verified", False) for r in self.rules)
            self.enforce_verification = enforce_verification

    # ------------------------------------------------------------------
    # Public API (RuleEngine-compatible)
    # ------------------------------------------------------------------

    def evaluate(
        self,
        extracted_fields: Dict[str, Any],
        image_quality: Optional[Dict[str, Any]] = None,
        pointers: Optional[List[Dict[str, Any]]] = None,
    ) -> List[RuleResult]:
        exemption = self._exemption_mode(extracted_fields)

        results: List[RuleResult] = []
        aggregate_rule = None
        for rule in self.rules:
            if rule.get("validation", {}).get("type") == "REQUIRED_DECLARATIONS_PRESENT":
                aggregate_rule = rule
                continue
            results.append(
                self._evaluate_rule(rule, extracted_fields, image_quality, pointers, exemption)
            )

        if aggregate_rule is not None:
            results.append(
                self._evaluate_aggregate(aggregate_rule, results)
            )
        return results

    def fuse(self, rule_results: List[RuleResult]) -> ComplianceDecision:
        failed = [r for r in rule_results if r.status == FAIL]
        review = [r for r in rule_results if r.status in (MANUAL_REVIEW, UNVERIFIED)]
        definitive = [r for r in rule_results if r.status in (PASS, FAIL)]

        if failed:
            reasons = [f"{r.rule_id} ({r.severity}): {r.reason}" for r in failed]
            return ComplianceDecision(
                decision="NON_COMPLIANT",
                reasons=reasons,
                failed_rules=[r.rule_id for r in failed],
                review_rules=[r.rule_id for r in review],
            )
        if review:
            return ComplianceDecision(
                decision="MANUAL_REVIEW",
                reasons=[f"{r.rule_id}: {r.reason}" for r in review],
                review_rules=[r.rule_id for r in review],
            )
        if definitive:
            return ComplianceDecision(decision="COMPLIANT", reasons=["All applicable rules passed"])
        return ComplianceDecision(
            decision="MANUAL_REVIEW",
            reasons=["No rules were evaluated for this inspection"],
        )

    # ------------------------------------------------------------------
    # Rule 26 exemption gate
    # ------------------------------------------------------------------

    @staticmethod
    def _exemption_mode(fields: Dict[str, Any]) -> str:
        """EXEMPT (<=10 g/ml), PARTIAL (10-20 g/ml: MRP + net qty still
        required), FULL (rules apply), UNKNOWN (no parseable quantity).

        A LOW-confidence quantity is never trusted to exempt rules - the
        exemption would then rest on an uncertain extraction."""
        f = fields.get("net_quantity", {})
        value = f.get("value") if isinstance(f, dict) else None
        if not value:
            return "UNKNOWN"
        if str(f.get("confidence_level", "")).upper() == "LOW":
            return "UNKNOWN"
        m = QTY_VALUE_RE.search(str(value))
        if not m:
            return "UNKNOWN"
        try:
            v = float(m.group(1))
        except ValueError:
            return "UNKNOWN"
        unit = m.group(2).lower()
        if unit in ("g", "gm"):
            grams = v
        elif unit == "kg":
            grams = v * 1000.0
        elif unit == "ml":
            grams = v
        elif unit == "l":
            grams = v * 1000.0
        else:
            return "FULL"
        if grams <= 10.0:
            return "EXEMPT"
        if grams <= 20.0:
            return "PARTIAL"
        return "FULL"

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def _evaluate_rule(
        self,
        rule: Dict[str, Any],
        fields: Dict[str, Any],
        image_quality: Optional[Dict[str, Any]],
        pointers: Optional[List[Dict[str, Any]]],
        exemption: str,
    ) -> RuleResult:
        rule_id = rule.get("rule_id", "UNKNOWN")
        vtype = rule.get("validation", {}).get("type", "")
        category = rule.get("category", "")

        base = RuleResult(
            rule_id=rule_id,
            fields=list(rule.get("validation", {}).get("fields", []) or []),
            status=MANUAL_REVIEW,
            severity=rule.get("severity", "MEDIUM"),
            requirement=rule.get("title", rule.get("requirement", "")),
            reason="",
            source=self._source(rule),
            verified=bool(rule.get("verified", False)),
        )

        # Verification guard
        if self.enforce_verification and not rule.get("verified", False):
            base.status = UNVERIFIED
            base.reason = "Rule pending verification against the official document"
            return base

        # Rule 26 gate row: report the gate outcome itself
        if vtype == "EXEMPTION_LOOKUP":
            base.status = NOT_APPLICABLE
            base.reason = {
                "EXEMPT": "Exemption gate: package declares <= 10 g/ml - declaration rules exempted under Rule 26",
                "PARTIAL": "Exemption gate: package declares 10-20 g/ml - only MRP and net quantity declarations required (Rule 26 proviso)",
                "FULL": "Exemption gate: package quantity above exemption thresholds - full rules apply",
                "UNKNOWN": "Exemption gate: net quantity not determinable - full rules applied",
            }[exemption]
            return base

        # Scope: rule ids outside image-inspection scope
        if rule_id in SCOPE_NA_RULE_IDS:
            base.status = NOT_APPLICABLE
            base.reason = f"Outside automated image-inspection scope: {SCOPE_NA_RULE_IDS[rule_id]}"
            return base

        # Scope: validation types outside image-inspection scope
        if vtype in SCOPE_NA_VALIDATION_TYPES:
            base.status = NOT_APPLICABLE
            base.reason = (
                f"Outside automated image-inspection scope: "
                f"{SCOPE_NA_VALIDATION_TYPES[vtype]}"
            )
            return base

        # Rule 26 exemption applied to declaration rules
        if category in DECLARATION_CATEGORIES:
            if exemption == "EXEMPT":
                base.status = NOT_APPLICABLE
                base.reason = "Package exempt under Rule 26 (net quantity <= 10 g/ml)"
                return base
            if exemption == "PARTIAL" and category not in PARTIAL_REQUIRED_CATEGORIES:
                base.status = NOT_APPLICABLE
                base.reason = (
                    "Exempt under Rule 26 (net quantity 10-20 g/ml) - only MRP and "
                    "net quantity declarations required"
                )
                return base

        handler = {
            "manufacturer_details": self._check_entity,
            "commodity_identity": self._check_product_name,
            "net_quantity": self._check_net_quantity,
            "quantity_unit": self._check_net_quantity,
            "date_declaration": self._check_manufacture_date,
            "mrp": self._check_mrp,
            "consumer_contact": self._check_consumer_contact,
            "quantity_language": self._check_quantity_wording,
            "unit_format": self._check_threshold_unit,
            "language": self._check_language,
            "declaration_legibility": self._check_legibility,
        }.get(category)

        if handler is None:
            base.reason = f"No handler for category '{category}' / validation '{vtype}'"
            return base
        return handler(base, rule, fields, image_quality, pointers)

    # ------------------------------------------------------------------
    # Category checks
    # ------------------------------------------------------------------

    @staticmethod
    def _low_confidence(fields, name) -> bool:
        return str(
            LabelGuardEngine._fget(fields, name, "confidence_level") or ""
        ).upper() == "LOW"

    def _check_entity(self, base, rule, fields, quality, pointers):
        """Rule 6(1)(a) + Rule 10: name AND address of manufacturer/packer/
        importer."""
        name_fields = ("manufacturer", "packer", "importer")
        present = [n for n in name_fields if self._fget(fields, n, "value")]
        if present:
            with_address = [n for n in present if self._fget(fields, n, "address_detected")]
            evidence = {
                "detected": True,
                "value": self._fget(fields, present[0], "value"),
                "address_text": self._fget(fields, present[0], "address_text"),
            }
            base.evidence = evidence
            if self._low_confidence(fields, present[0]):
                base.status = MANUAL_REVIEW
                base.reason = (
                    f"Entity name '{evidence['value']}' detected via unlabelled "
                    "association (LOW confidence) - requires verification"
                )
            elif with_address:
                base.status = PASS
                base.reason = (
                    f"Name and address declared via '{with_address[0]}' "
                    f"(address: \"{str(evidence['address_text'])[:60]}\")"
                )
            else:
                base.status = MANUAL_REVIEW
                base.reason = (
                    f"Entity name detected ('{present[0]}') but no address located "
                    "next to it - address may be on another surface or behind a "
                    "QR/reference pointer"
                )
            return base
        return self._absence(base, list(name_fields), quality, pointers, "manufacturer/packer/importer")

    def _check_product_name(self, base, rule, fields, quality, pointers):
        if self._fget(fields, "product_name", "value"):
            base.evidence = self._field_evidence(fields, "product_name")
            if self._low_confidence(fields, "product_name"):
                base.status = MANUAL_REVIEW
                base.reason = "Commodity name candidate detected but prominence heuristic is uncertain"
            else:
                base.status = PASS
                base.reason = "Common/generic name of the commodity is declared"
            return base
        return self._absence(base, ["product_name"], quality, pointers, "commodity name")

    def _check_net_quantity(self, base, rule, fields, quality, pointers):
        value = self._fget(fields, "net_quantity", "value")
        if value:
            base.evidence = self._field_evidence(fields, "net_quantity")
            if self._low_confidence(fields, "net_quantity"):
                base.status = MANUAL_REVIEW
                base.reason = f"Net quantity '{value}' detected but extraction confidence is LOW"
            elif QTY_VALUE_RE.search(str(value)):
                base.status = PASS
                base.reason = f"Net quantity declared with a standard unit ('{value}')"
            else:
                base.status = MANUAL_REVIEW
                base.reason = f"Net quantity declared but no standard unit detected in '{value}'"
            return base
        return self._absence(base, ["net_quantity"], quality, pointers, "net quantity")

    def _check_manufacture_date(self, base, rule, fields, quality, pointers):
        for name in ("manufacturing_date", "packing_date"):
            value = self._fget(fields, name, "value")
            if value:
                base.evidence = self._field_evidence(fields, name)
                if self._low_confidence(fields, name):
                    base.status = MANUAL_REVIEW
                    base.reason = f"Date '{value}' detected but extraction confidence is LOW"
                    return base
                has_month_year = any(p.search(str(value)) for p in MONTH_YEAR_RES) and (
                    MONTHS_RE.search(str(value))
                    or re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", str(value))
                )
                if has_month_year:
                    base.status = PASS
                    base.reason = f"Month and year of manufacture/packing declared ('{value}')"
                else:
                    base.status = MANUAL_REVIEW
                    base.reason = f"Date declared ('{value}') but month-and-year representation not confirmed"
                return base
        return self._absence(
            base, ["manufacturing_date", "packing_date"], quality, pointers,
            "month and year of manufacture/packing",
        )

    def _check_mrp(self, base, rule, fields, quality, pointers):
        value = self._fget(fields, "mrp", "value")
        if value:
            base.evidence = self._field_evidence(fields, "mrp")
            if self._low_confidence(fields, "mrp"):
                base.status = MANUAL_REVIEW
                base.reason = f"Price '{value}' detected but extraction confidence is LOW"
                return base
            m = PRICE_NUMBER_PATTERN.search(str(value))
            if m:
                try:
                    price = float(m.group(1))
                except ValueError:
                    price = None
            else:
                price = None
            if price is not None and PRICE_RANGE[0] <= price <= PRICE_RANGE[1]:
                base.status = PASS
                base.reason = f"Retail sale price declared (₹{price:g})"
            else:
                base.status = MANUAL_REVIEW
                base.reason = f"Price declared ('{value}') but value not parseable/plausible"
            return base
        return self._absence(base, ["mrp"], quality, pointers, "retail sale price (MRP)")

    def _check_consumer_contact(self, base, rule, fields, quality, pointers):
        value = self._fget(fields, "consumer_care", "value")
        if value:
            base.evidence = self._field_evidence(fields, "consumer_care")
            text = str(value)
            if "phone" in text.lower():
                base.status = PASS
                base.reason = "Consumer complaint contact details declared (telephone detected)"
            elif "email" in text.lower():
                base.status = MANUAL_REVIEW
                base.reason = (
                    "Only an e-mail contact detected - Rule 6(2) requires the "
                    "telephone number (e-mail is optional); phone may be present "
                    "but unreadable"
                )
            else:
                base.status = MANUAL_REVIEW
                base.reason = f"Contact details detected but form unclear ('{text[:40]}')"
            return base
        return self._absence(base, ["consumer_care"], quality, pointers, "consumer complaint contact details")

    def _check_quantity_wording(self, base, rule, fields, quality, pointers):
        """Rule 12(6): the ONLY content-FAIL rule - misleading qualifiers in
        the quantity declaration."""
        f = fields.get("net_quantity", {})
        value = f.get("value") if isinstance(f, dict) else None
        if not value:
            base.status = NOT_APPLICABLE
            base.reason = "No quantity declaration to assess"
            return base
        text = f"{value} | {f.get('ocr_text', '')}"
        disallowed = rule.get("validation", {}).get("disallowed_phrases", [])
        for phrase in disallowed:
            patterns = [rf"\b{re.escape(phrase)}\b"]
            patterns.extend(MISLEADING_ABBREVIATIONS.get(phrase.lower(), []))
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    base.status = FAIL
                    base.reason = (
                        f"Misleading quantity qualifier '{phrase}' (matched "
                        f"\"{re.search(pat, text, re.IGNORECASE).group(0)}\") in the "
                        f"quantity declaration (\"{str(f.get('ocr_text', ''))[:60]}\") "
                        "- Rule 12(6)"
                    )
                    base.evidence = self._field_evidence(fields, "net_quantity")
                    return base
        base.status = PASS
        base.reason = "Quantity declaration contains no misleading qualifiers"
        base.evidence = self._field_evidence(fields, "net_quantity")
        return base

    def _check_threshold_unit(self, base, rule, fields, quality, pointers):
        """Rule 13: g below 1 kg / kg at or above; ml below 1 l / l at or
        above; cm below 1 m / m at or above."""
        value = self._fget(fields, "net_quantity", "value")
        if not value:
            base.status = NOT_APPLICABLE
            base.reason = "No quantity declaration to assess"
            return base
        m = QTY_VALUE_RE.search(str(value))
        if not m:
            base.status = NOT_APPLICABLE
            base.reason = "Quantity unit not parseable for threshold check"
            return base
        v, unit = float(m.group(1)), m.group(2).lower()
        base.evidence = self._field_evidence(fields, "net_quantity")
        problems = {
            ("g", lambda x: x >= 1000): "declared in grams at/above 1 kg - Rule 13 requires kilogram",
            ("gm", lambda x: x >= 1000): "declared in grams at/above 1 kg - Rule 13 requires kilogram",
            ("kg", lambda x: x < 1): "declared in kilograms below 1 kg - Rule 13 requires gram",
            ("ml", lambda x: x >= 1000): "declared in millilitres at/above 1 litre - Rule 13 requires litre",
            ("l", lambda x: x < 1): "declared in litres below 1 litre - Rule 13 requires millilitre",
            ("cm", lambda x: x >= 100): "declared in centimetres at/above 1 metre - Rule 13 requires metre",
            ("m", lambda x: x < 1): "declared in metres below 1 metre - Rule 13 requires centimetre",
        }
        for (u, cond), message in problems.items():
            if unit == u and cond(v):
                base.status = MANUAL_REVIEW
                base.reason = f"Quantity '{value}': {message}"
                return base
        base.status = PASS
        base.reason = f"Unit appropriate for the declared quantity ('{value}')"
        return base

    def _check_language(self, base, rule, fields, quality, pointers):
        declared = [
            n
            for n in ("mrp", "net_quantity", "product_name", "manufacturer",
                      "manufacturing_date", "consumer_care", "country_of_origin")
            if self._fget(fields, n, "value")
        ]
        if len(declared) >= 2:
            base.status = PASS
            base.reason = (
                f"Declarations detected in English (Latin script) on the captured "
                f"surfaces ({len(declared)} declarations)"
            )
        else:
            base.status = MANUAL_REVIEW
            base.reason = "Too little declaration text detected to confirm Hindi/English language requirement"
        return base

    def _check_legibility(self, base, rule, fields, quality, pointers):
        """Rule 9(1) proxy: OCR readability of the MRP and net quantity lines."""
        confs = []
        for name in ("mrp", "net_quantity"):
            f = fields.get(name, {})
            if isinstance(f, dict) and f.get("value") is not None:
                confs.append(float(f.get("ocr_confidence", 0.0)))
        if len(confs) == 2:
            lowest = min(confs)
            if lowest >= 0.85:
                base.status = PASS
                base.reason = (
                    f"MRP and net quantity declarations legible to OCR "
                    f"(min line confidence {lowest:.2f}) - contrast appears conspicuous"
                )
            else:
                base.status = MANUAL_REVIEW
                base.reason = (
                    f"Declaration line confidence {lowest:.2f} below legibility "
                    "threshold - contrast/legibility needs manual verification"
                )
        elif len(confs) == 1:
            base.status = MANUAL_REVIEW
            base.reason = "Only one of MRP/net quantity detected - legibility of the other cannot be assessed"
        else:
            base.status = MANUAL_REVIEW
            base.reason = "MRP and net quantity not detected - legibility cannot be assessed"
        return base

    def _evaluate_aggregate(self, rule, results: List[RuleResult]) -> RuleResult:
        """Rule 4: package bears the required declarations (aggregate)."""
        base = RuleResult(
            rule_id=rule.get("rule_id", "R04"),
            fields=[],
            status=MANUAL_REVIEW,
            severity=rule.get("severity", "HIGH"),
            requirement=rule.get("title", ""),
            reason="",
            source=self._source(rule),
            verified=bool(rule.get("verified", False)),
        )
        if self.enforce_verification and not rule.get("verified", False):
            base.status = UNVERIFIED
            base.reason = "Rule pending verification against the official document"
            return base
        declaration_results = [
            r for r in results if r.status in (PASS, FAIL, MANUAL_REVIEW, UNVERIFIED)
        ]
        failed = [r for r in declaration_results if r.status == FAIL]
        review = [r for r in declaration_results if r.status in (MANUAL_REVIEW, UNVERIFIED)]
        if failed:
            base.status = FAIL
            base.reason = (
                f"Required declaration(s) missing or invalid: "
                f"{', '.join(r.rule_id for r in failed)}"
            )
        elif review:
            base.status = MANUAL_REVIEW
            base.reason = (
                f"Declaration completeness uncertain for: "
                f"{', '.join(r.rule_id for r in review[:4])}"
                + (" and others" if len(review) > 4 else "")
            )
        elif declaration_results:
            base.status = PASS
            base.reason = "All required declarations detectable under Chapter II are present"
        else:
            base.status = NOT_APPLICABLE
            base.reason = "Declaration rules exempted (Rule 26)"
        return base

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _absence(self, base, field_names, quality, pointers, label):
        if self._quality_blocks_absence_fail(quality):
            base.status = MANUAL_REVIEW
            base.reason = (
                f"The {label} is not detected and image quality is insufficient "
                "to trust absence as evidence"
            )
            return base
        pointer = None
        for name in field_names:
            pointer = self._matching_pointer(name, pointers)
            if pointer is not None:
                break
        if pointer is not None:
            base.status = MANUAL_REVIEW
            base.reason = (
                f"The {label} is not detected on captured surfaces, but the label "
                f"states this information is located elsewhere on the package "
                f"(\"{str(pointer.get('text', ''))[:80]}\") - verify that surface"
            )
            base.evidence = {"detected": False, "reference_pointer": pointer}
            return base
        base.status = FAIL
        base.reason = f"The {label} is not declared on any captured package surface"
        return base

    @staticmethod
    def _matching_pointer(field_name, pointers):
        if not pointers:
            return None
        for p in pointers:
            if field_name in (p.get("fields") or []):
                return p
            if p.get("location") in BASE_LOCATIONS and field_name in BASE_LOCATION_FIELDS:
                return p
        return None

    @staticmethod
    def _quality_blocks_absence_fail(image_quality):
        if not image_quality:
            return False
        if not image_quality.get("usable", True):
            return True
        score = image_quality.get("score", 100.0)
        return isinstance(score, (int, float)) and score < 60.0

    @staticmethod
    def _fget(fields, name, key):
        f = fields.get(name)
        if isinstance(f, dict):
            return f.get(key)
        return getattr(f, key, None)

    @staticmethod
    def _field_evidence(fields, name):
        f = fields.get(name)
        if not isinstance(f, dict):
            f = {
                "value": getattr(f, "value", None),
                "ocr_text": getattr(f, "ocr_text", ""),
                "ocr_confidence": getattr(f, "ocr_confidence", 0.0),
                "extraction_confidence": getattr(f, "extraction_confidence", 0.0),
                "bbox": getattr(f, "bbox", []),
            }
        return {
            "detected": True,
            "value": f.get("value"),
            "ocr_text": f.get("ocr_text", ""),
            "ocr_confidence": f.get("ocr_confidence", 0.0),
            "extraction_confidence": f.get("extraction_confidence", 0.0),
            "bbox": f.get("bbox", []),
            "source_image": f.get("source_image"),
        }

    @staticmethod
    def _source(rule):
        s = rule.get("source", {}) or {}
        return {
            "document": s.get("document", ""),
            "rule": s.get("rule_reference", rule.get("rule_reference", "")),
            "page": s.get("source_pdf_page"),
            "evidence_text": s.get("evidence_text", ""),
            "status": rule.get("status", "DRAFT"),
            "category": rule.get("category", ""),
        }
