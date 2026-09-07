"""Unit tests for the LabelGuard (LM(PC)R 2011) rule checker."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.app.services.labelguard_engine import LabelGuardEngine

GOOD_QUALITY = {"usable": True, "score": 95.0, "checks": {}}
BAD_QUALITY = {"usable": False, "score": 40.0, "checks": {}}


def field(value, level="HIGH", ocr=0.97, ocr_text="", **extra):
    d = {
        "value": value,
        "confidence_level": level if value is not None else "MISSING",
        "ocr_confidence": ocr if value is not None else 0.0,
        "extraction_confidence": 0.9 if value is not None else 0.0,
        "ocr_text": ocr_text,
        "bbox": [[0, 0], [10, 0], [10, 10], [0, 10]],
        "source_image": "front.jpg",
    }
    d.update(extra)
    return d


def full_compliant_fields():
    return {
        "mrp": field("₹20.00", ocr_text="MRP Rs 20.00"),
        "product_name": field("DEMO SNACK", ocr_text="DEMO SNACK"),
        "net_quantity": field("100 g", ocr_text="Net Qty: 100 g"),
        "manufacturer": field(
            "ABC Foods Pvt Ltd",
            ocr_text="Manufactured By: ABC",
            address_detected=True,
            address_text="Plot 5, Industrial Estate, Mumbai",
        ),
        "packer": field(None),
        "importer": field(None),
        "manufacturing_date": field("15/01/2026", ocr_text="Mfg. Date: 15/01/2026"),
        "packing_date": field(None),
        "best_before": field(None),
        "batch_number": field("A25X77"),
        "consumer_care": field("Phone: 1800-123-4567", ocr_text="Customer Care"),
        "country_of_origin": field("India"),
    }


class TestLabelGuardBasics:
    def setup_method(self):
        self.engine = LabelGuardEngine()

    def test_ruleset_loads(self):
        assert len(self.engine.rules) == 31
        assert self.engine.ruleset_verified is False

    def test_fully_compliant_package(self):
        results = self.engine.evaluate(full_compliant_fields(), GOOD_QUALITY)
        decision = self.engine.fuse(results)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-A-001"].status == "PASS"
        assert by_id["PC2011-R06-B-001"].status == "PASS"
        assert by_id["PC2011-R06-C-001"].status == "PASS"
        assert by_id["PC2011-R06-D-001"].status == "PASS"
        assert by_id["PC2011-R06-E-001"].status == "PASS"
        assert by_id["PC2011-R06-2-001"].status == "PASS"
        assert by_id["PC2011-R10-001"].status == "PASS"
        assert by_id["PC2011-R04-001"].status == "PASS"
        assert decision.decision == "COMPLIANT"

    def test_scope_na_rules_reported_honestly(self):
        results = self.engine.evaluate(full_compliant_fields(), GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        for rule_id in (
            "PC2011-R05-001",   # standard pack sizes (schedule lookup)
            "PC2011-R06-3-001", # stickers (visual)
            "PC2011-R07-001",   # font heights (physical scale)
            "PC2011-R08-001",   # principal display panel
            "PC2011-R11-001",   # tare (physical weighing)
            "PC2011-R24-001",   # wholesale
            "PC2011-R31-001",   # advertisements
        ):
            assert by_id[rule_id].status == "NOT_APPLICABLE", rule_id
            assert "scope" in by_id[rule_id].reason.lower()

    def test_source_citations_carried(self):
        results = self.engine.evaluate(full_compliant_fields(), GOOD_QUALITY)
        mrp = {r.rule_id: r for r in results}["PC2011-R06-E-001"]
        assert mrp.source["rule"] == "Rule 6(1)(e)"
        assert mrp.source["page"] == 44
        assert "retail sale price" in mrp.source["evidence_text"].lower()
        assert mrp.severity == "CRITICAL"


class TestDeclarationChecks:
    def setup_method(self):
        self.engine = LabelGuardEngine()

    def test_missing_mrp_fails(self):
        fields = full_compliant_fields()
        fields["mrp"] = field(None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-E-001"].status == "FAIL"
        decision = self.engine.fuse(results)
        assert decision.decision == "NON_COMPLIANT"
        assert "PC2011-R06-E-001" in decision.failed_rules

    def test_missing_mrp_bad_image_review(self):
        fields = full_compliant_fields()
        fields["mrp"] = field(None)
        results = self.engine.evaluate(fields, BAD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-E-001"].status == "MANUAL_REVIEW"

    def test_pointer_softens_mrp_absence(self):
        fields = full_compliant_fields()
        fields["mrp"] = field(None)
        pointers = [
            {"text": "NO., - SEE BASE OF CAN", "location": "base",
             "fields": ["batch_number"], "image": "back.jpg"}
        ]
        results = self.engine.evaluate(fields, GOOD_QUALITY, pointers=pointers)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-E-001"].status == "MANUAL_REVIEW"
        assert "elsewhere" in by_id["PC2011-R06-E-001"].reason.lower()

    def test_entity_without_address_review(self):
        fields = full_compliant_fields()
        fields["manufacturer"]["address_detected"] = False
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-A-001"].status == "MANUAL_REVIEW"
        assert "address" in by_id["PC2011-R06-A-001"].reason.lower()

    def test_low_confidence_net_quantity_never_passes(self):
        fields = full_compliant_fields()
        fields["net_quantity"] = field("350 ml", level="LOW")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-C-001"].status == "MANUAL_REVIEW"

    def test_net_quantity_without_unit_review(self):
        fields = full_compliant_fields()
        fields["net_quantity"] = field("49.7")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-C-001"].status == "MANUAL_REVIEW"

    def test_email_only_consumer_contact_review(self):
        """Rule 6(2) requires the telephone number; e-mail is optional."""
        fields = full_compliant_fields()
        fields["consumer_care"] = field("Email: care@abc.com")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-2-001"].status == "MANUAL_REVIEW"
        assert "telephone" in by_id["PC2011-R06-2-001"].reason.lower()

    def test_month_year_format_checked(self):
        fields = full_compliant_fields()
        fields["manufacturing_date"] = field("2026")  # year only
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-D-001"].status == "MANUAL_REVIEW"


class TestContentRules:
    """Rule 12(6) - the first rule that FAILs on declaration CONTENT."""

    def setup_method(self):
        self.engine = LabelGuardEngine()

    def test_misleading_quantity_wording_fails(self):
        fields = full_compliant_fields()
        fields["net_quantity"] = field("Min 100 g", ocr_text="Net Wt: Min 100 g")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        r = by_id["PC2011-R12-6-001"]
        assert r.status == "FAIL"
        assert "minimum" in r.reason.lower() or "'min" in r.reason.lower() or "qualifier" in r.reason.lower()
        decision = self.engine.fuse(results)
        assert decision.decision == "NON_COMPLIANT"

    def test_clean_quantity_wording_passes(self):
        results = self.engine.evaluate(full_compliant_fields(), GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R12-6-001"].status == "PASS"

    def test_threshold_unit_grams_above_1kg_review(self):
        fields = full_compliant_fields()
        fields["net_quantity"] = field("1500 g", ocr_text="Net Wt: 1500 g")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R13-001"].status == "MANUAL_REVIEW"
        assert "kilogram" in by_id["PC2011-R13-001"].reason

    def test_threshold_unit_kg_below_1kg_review(self):
        fields = full_compliant_fields()
        fields["net_quantity"] = field("0.5 kg", ocr_text="Net Wt: 0.5 kg")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R13-001"].status == "MANUAL_REVIEW"
        assert "gram" in by_id["PC2011-R13-001"].reason

    def test_threshold_unit_ok_passes(self):
        results = self.engine.evaluate(full_compliant_fields(), GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R13-001"].status == "PASS"


class TestRule26ExemptionGate:
    def setup_method(self):
        self.engine = LabelGuardEngine()

    def _gate(self, qty):
        fields = full_compliant_fields()
        fields["net_quantity"] = field(qty, ocr_text=f"Net Qty: {qty}")
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        return {r.rule_id: r for r in results}

    def test_exempt_small_package(self):
        """<= 10 g: declaration rules exempted under Rule 26."""
        by_id = self._gate("8 g")
        assert by_id["PC2011-R26-001"].status == "NOT_APPLICABLE"
        assert "exempt" in by_id["PC2011-R26-001"].reason.lower()
        # declaration rules exempted even though MRP is missing
        fields = full_compliant_fields()
        fields["net_quantity"] = field("8 g")
        fields["mrp"] = field(None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-E-001"].status == "NOT_APPLICABLE"
        assert by_id["PC2011-R06-B-001"].status == "NOT_APPLICABLE"

    def test_partial_exemption_keeps_mrp_and_quantity(self):
        """10-20 g: only MRP and net quantity declarations remain required."""
        fields = full_compliant_fields()
        fields["net_quantity"] = field("15 g")
        fields["mrp"] = field(None)
        fields["product_name"] = field(None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-E-001"].status == "FAIL"          # MRP still required
        assert by_id["PC2011-R06-C-001"].status == "PASS"          # qty declared
        assert by_id["PC2011-R06-B-001"].status == "NOT_APPLICABLE"  # name exempted

    def test_above_threshold_full_rules(self):
        by_id = self._gate("500 g")
        assert "full rules apply" in by_id["PC2011-R26-001"].reason.lower()

    def test_unknown_quantity_full_rules(self):
        fields = full_compliant_fields()
        fields["net_quantity"] = field(None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        by_id = {r.rule_id: r for r in results}
        assert by_id["PC2011-R06-C-001"].status == "FAIL"  # absence still enforced


class TestAggregateAndVerification:
    def setup_method(self):
        self.engine = LabelGuardEngine()

    def test_aggregate_rule4_follows_declaration_rules(self):
        fields = full_compliant_fields()
        fields["mrp"] = field(None)
        results = self.engine.evaluate(fields, GOOD_QUALITY)
        decision = self.engine.fuse(results)
        assert "PC2011-R06-E-001" in decision.failed_rules
        assert "PC2011-R04-001" in decision.failed_rules

    def test_enforce_verification_blocks_unverified_rules(self):
        engine = LabelGuardEngine(enforce_verification=True)
        results = engine.evaluate(full_compliant_fields(), GOOD_QUALITY)
        assert all(r.status == "UNVERIFIED" for r in results)
        decision = engine.fuse(results)
        assert decision.decision == "MANUAL_REVIEW"
