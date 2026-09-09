import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.app.services.rule_engine import (
    RuleEngine,
    RuleResult,
    PASS,
    FAIL,
    MANUAL_REVIEW,
    NOT_APPLICABLE,
    UNVERIFIED,
)
from backend.app.services.field_extraction import ExtractedField

GOOD_QUALITY = {"usable": True, "score": 90.0, "checks": {}}
BAD_QUALITY = {"usable": False, "score": 45.0, "checks": {}}

FIXTURE_RULES = [
    {
        "rule_id": "MRP_001",
        "requirement": "MRP must be declared",
        "rule_type": "MANDATORY",
        "fields": ["mrp"],
        "validation": "PRESENT_AND_VALID_PRICE",
        "severity": "HIGH",
        "applicability": {"condition": "ALWAYS"},
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
    {
        "rule_id": "NET_QTY_001",
        "requirement": "Net quantity must be declared",
        "rule_type": "MANDATORY",
        "fields": ["net_quantity"],
        "validation": "PRESENT_AND_VALID_UNIT",
        "severity": "HIGH",
        "applicability": {"condition": "ALWAYS"},
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
    {
        "rule_id": "ENTITY_001",
        "requirement": "Manufacturer, packer or importer must be declared",
        "rule_type": "MANDATORY_ANY",
        "fields": ["manufacturer", "packer", "importer"],
        "validation": "PRESENT",
        "severity": "HIGH",
        "applicability": {"condition": "ALWAYS"},
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
    {
        "rule_id": "DATE_001",
        "requirement": "Date of manufacture or packing must be declared",
        "rule_type": "MANDATORY_ANY",
        "fields": ["manufacturing_date", "packing_date"],
        "validation": "PRESENT",
        "severity": "HIGH",
        "applicability": {"condition": "ALWAYS"},
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
    {
        "rule_id": "CONSUMER_CARE_001",
        "requirement": "Consumer care details must be declared",
        "rule_type": "MANDATORY",
        "fields": ["consumer_care"],
        "validation": "PRESENT",
        "severity": "HIGH",
        "applicability": {"condition": "ALWAYS"},
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
    {
        "rule_id": "ORIGIN_001",
        "requirement": "Country of origin must be declared",
        "rule_type": "MANDATORY",
        "fields": ["country_of_origin"],
        "validation": "PRESENT",
        "severity": "HIGH",
        "applicability": {"condition": "ALWAYS"},
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
    {
        "rule_id": "BATCH_001",
        "requirement": "Batch number should be declared",
        "rule_type": "MANDATORY",
        "fields": ["batch_number"],
        "validation": "PRESENT",
        "severity": "MEDIUM",
        "applicability": {"condition": "ALWAYS"},
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
    {
        "rule_id": "IMPORTER_001",
        "requirement": "Importer must be declared for non-Indian origin",
        "rule_type": "CONDITIONAL",
        "fields": ["importer"],
        "validation": "PRESENT",
        "severity": "HIGH",
        "applicability": {
            "condition": "ORIGIN_NOT_INDIA",
            "depends_on": "country_of_origin",
        },
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
    {
        "rule_id": "BEST_BEFORE_001",
        "requirement": "Best before should contain a determinate date",
        "rule_type": "CONDITIONAL",
        "fields": ["best_before"],
        "validation": "VALID_DATE",
        "severity": "MEDIUM",
        "applicability": {"condition": "FIELD_PRESENT", "depends_on": "best_before"},
        "source": {"document": "TEST", "rule": "TBD"},
        "verified": False,
    },
]


def make_field(name, value=None, ocr_conf=0.95, ext_conf=0.90, level=None, ocr_text=""):
    return {
        "field_name": name,
        "value": value,
        "ocr_text": ocr_text,
        "ocr_confidence": ocr_conf,
        "extraction_confidence": ext_conf if value is not None else 0.0,
        "confidence_level": level or ("MISSING" if value is None else "HIGH"),
        "bbox": [[0, 0], [10, 0], [10, 10], [0, 10]],
        "reason": "",
        "line_index": 0,
    }


def full_fields():
    return {
        "mrp": make_field("mrp", "₹20.00"),
        "net_quantity": make_field("net_quantity", "500 g"),
        "manufacturer": make_field("manufacturer", "ABC Foods Pvt Ltd"),
        "packer": make_field("packer", None),
        "importer": make_field("importer", None),
        "manufacturing_date": make_field("manufacturing_date", "15/01/2026"),
        "packing_date": make_field("packing_date", None),
        "best_before": make_field("best_before", "15/07/2026"),
        "batch_number": make_field("batch_number", "B123"),
        "consumer_care": make_field("consumer_care", "care@abctest.com"),
        "country_of_origin": make_field("country_of_origin", "Product of India"),
    }


class TestRuleEngine:
    def setup_method(self):
        self.engine = RuleEngine(rules=FIXTURE_RULES)

    def _by_id(self, results):
        return {r.rule_id: r for r in results}

    def test_all_fields_present_compliant(self):
        results = self.engine.evaluate(full_fields(), GOOD_QUALITY)
        decision = self.engine.fuse(results)
        assert decision.decision == "COMPLIANT"
        by_id = self._by_id(results)
        assert by_id["MRP_001"].status == PASS
        assert by_id["NET_QTY_001"].status == PASS
        assert by_id["ENTITY_001"].status == PASS
        assert by_id["DATE_001"].status == PASS
        assert by_id["CONSUMER_CARE_001"].status == PASS
        assert by_id["ORIGIN_001"].status == PASS
        assert by_id["BATCH_001"].status == PASS

    def test_missing_mrp_good_image_fails(self):
        fields = full_fields()
        fields["mrp"] = make_field("mrp", None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        decision = self.engine.fuse(results)
        by_id = self._by_id(results)
        assert by_id["MRP_001"].status == FAIL
        assert decision.decision == "NON_COMPLIANT"
        assert "MRP_001" in decision.failed_rules

    def test_missing_mrp_bad_image_goes_to_review(self):
        """Absence cannot be trusted as evidence on a poor image."""
        fields = full_fields()
        fields["mrp"] = make_field("mrp", None)
        results = self.engine.evaluate(fields, BAD_QUALITY)
        decision = self.engine.fuse(results)
        by_id = self._by_id(results)
        assert by_id["MRP_001"].status == MANUAL_REVIEW
        assert decision.decision == "MANUAL_REVIEW"

    def test_low_confidence_field_goes_to_review_not_fail(self):
        fields = full_fields()
        fields["mrp"] = make_field("mrp", "₹20", ext_conf=0.6, level="LOW")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = self._by_id(results)
        assert by_id["MRP_001"].status == MANUAL_REVIEW

    def test_mrp_unparseable_value_goes_to_review(self):
        fields = full_fields()
        fields["mrp"] = make_field("mrp", "MRP Rs. ???")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = self._by_id(results)
        assert by_id["MRP_001"].status == MANUAL_REVIEW

    def test_mrp_out_of_range_goes_to_review(self):
        fields = full_fields()
        fields["mrp"] = make_field("mrp", "₹99999")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = self._by_id(results)
        assert by_id["MRP_001"].status == MANUAL_REVIEW

    def test_net_quantity_valid_unit_passes(self):
        fields = full_fields()
        fields["net_quantity"] = make_field("net_quantity", "100 ml")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        assert self._by_id(results)["NET_QTY_001"].status == PASS

    def test_net_quantity_without_unit_goes_to_review(self):
        fields = full_fields()
        fields["net_quantity"] = make_field("net_quantity", "49.7")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = self._by_id(results)
        assert by_id["NET_QTY_001"].status == MANUAL_REVIEW

    def test_mandatory_any_single_entity_passes(self):
        fields = full_fields()
        fields["manufacturer"] = make_field("manufacturer", None)
        fields["importer"] = make_field("importer", None)
        fields["packer"] = make_field("packer", "XYZ Packers Ltd")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        assert self._by_id(results)["ENTITY_001"].status == PASS

    def test_mandatory_any_all_missing_fails(self):
        fields = full_fields()
        fields["manufacturer"] = make_field("manufacturer", None)
        fields["packer"] = make_field("packer", None)
        fields["importer"] = make_field("importer", None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        assert self._by_id(results)["ENTITY_001"].status == FAIL

    def test_mandatory_any_low_confidence_goes_to_review(self):
        fields = full_fields()
        fields["manufacturer"] = make_field("manufacturer", None)
        fields["importer"] = make_field("importer", None)
        fields["packer"] = make_field("packer", "XYZ Ltd", ext_conf=0.6, level="LOW")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        assert self._by_id(results)["ENTITY_001"].status == MANUAL_REVIEW

    def test_importer_required_when_origin_foreign(self):
        fields = full_fields()
        fields["country_of_origin"] = make_field("country_of_origin", "Product of USA")
        fields["importer"] = make_field("importer", None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        decision = self.engine.fuse(results)
        by_id = self._by_id(results)
        assert by_id["IMPORTER_001"].status == FAIL
        assert decision.decision == "NON_COMPLIANT"
        assert "IMPORTER_001" in decision.failed_rules

    def test_importer_not_applicable_when_origin_india(self):
        results = self.engine.evaluate(full_fields(), GOOD_QUALITY)
        assert self._by_id(results)["IMPORTER_001"].status == NOT_APPLICABLE

    def test_importer_indeterminate_when_origin_missing(self):
        fields = full_fields()
        fields["country_of_origin"] = make_field("country_of_origin", None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        assert self._by_id(results)["IMPORTER_001"].status == MANUAL_REVIEW

    def test_best_before_absent_not_applicable(self):
        fields = full_fields()
        fields["best_before"] = make_field("best_before", None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        assert self._by_id(results)["BEST_BEFORE_001"].status == NOT_APPLICABLE

    def test_best_before_present_passes(self):
        results = self.engine.evaluate(full_fields(), GOOD_QUALITY)
        assert self._by_id(results)["BEST_BEFORE_001"].status == PASS

    def test_medium_severity_fail_still_non_compliant(self):
        fields = full_fields()
        fields["batch_number"] = make_field("batch_number", None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        decision = self.engine.fuse(results)
        assert self._by_id(results)["BATCH_001"].status == FAIL
        assert decision.decision == "NON_COMPLIANT"

    def test_unverified_rules_blocked_in_verified_mode(self):
        engine = RuleEngine(rules=FIXTURE_RULES, enforce_verification=True)
        results = engine.evaluate(full_fields(), GOOD_QUALITY)
        decision = engine.fuse(results)
        assert all(r.status == UNVERIFIED for r in results)
        assert decision.decision == "MANUAL_REVIEW"
        assert decision.review_rules

    def test_default_ruleset_loads_from_json(self):
        engine = RuleEngine()
        assert len(engine.rules) >= 9
        assert engine.ruleset_verified is True
        assert engine.enforce_verification is True
        results = engine.evaluate(full_fields(), GOOD_QUALITY)
        decision = engine.fuse(results)
        assert decision.decision == "COMPLIANT"

    def test_accepts_extractedfield_dataclasses(self):
        fields = full_fields()
        fields["mrp"] = ExtractedField(
            field_name="mrp",
            value="₹20.00",
            ocr_text="MRP ₹20.00",
            ocr_confidence=0.97,
            extraction_confidence=0.95,
            confidence_level="HIGH",
            bbox=[[0, 0], [10, 0], [10, 10], [0, 10]],
            reason="test",
            line_index=0,
        )
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        assert self._by_id(results)["MRP_001"].status == PASS

    def test_rule_result_carries_evidence(self):
        results = self.engine.evaluate(full_fields(), GOOD_QUALITY)
        mrp_result = self._by_id(results)["MRP_001"]
        assert mrp_result.evidence["detected"] is True
        assert mrp_result.evidence["value"] == "₹20.00"
        assert mrp_result.evidence["bbox"]
        assert mrp_result.source["document"] == "TEST"

    def test_no_quality_context_allows_fail(self):
        """No quality dict = assume evidence is trustworthy (API standalone mode)."""
        fields = full_fields()
        fields["mrp"] = make_field("mrp", None)
        results = self.engine.evaluate(fields, None)
        assert self._by_id(results)["MRP_001"].status == FAIL
