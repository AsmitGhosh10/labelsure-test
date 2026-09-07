"""Visual evidence overlays (PRD §20) and the PDF report (PRD §29)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.app.services import annotate, pdf_report
from backend.app.services.report_generator import FIELD_LABELS

PIL = pytest.importorskip("PIL", reason="Pillow is required for image overlays")
from PIL import Image  # noqa: E402


def _box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


FIELDS = {
    "mrp": {
        "value": "45.00",
        "bbox": _box(10, 10, 200, 50),
        "source_image": "front.jpg",
        "extraction_confidence": 0.95,
    },
    "net_quantity": {
        "value": "200 g",
        "bbox": _box(10, 70, 200, 110),
        "source_image": "front.jpg",
        "extraction_confidence": 0.9,
    },
    "manufacturer": {
        "value": "ABC Foods",
        "bbox": _box(10, 10, 300, 50),
        "source_image": "back.jpg",
        "extraction_confidence": 0.8,
    },
    "batch_number": {  # detected but with no bounding box - not drawable
        "value": "B123",
        "bbox": [],
        "source_image": "back.jpg",
        "extraction_confidence": 0.7,
    },
    "importer": {"value": None, "bbox": [], "source_image": None},
}

RULES = [
    {"rule_id": "R1", "status": "PASS", "fields": ["mrp"]},
    {"rule_id": "R2", "status": "FAIL", "fields": ["net_quantity"]},
    {"rule_id": "R3", "status": "PASS", "fields": ["net_quantity"]},
    {"rule_id": "R4", "status": "MANUAL_REVIEW", "fields": ["manufacturer"]},
    {"rule_id": "R5", "status": "NOT_APPLICABLE", "fields": ["mrp"]},
]


class TestAnnotationPlan:
    def test_boxes_are_grouped_by_source_surface(self):
        plan = annotate.plan_annotations(FIELDS, RULES, FIELD_LABELS)
        assert set(plan) == {"front.jpg", "back.jpg"}
        assert {b["field"] for b in plan["front.jpg"]} == {"mrp", "net_quantity"}
        assert {b["field"] for b in plan["back.jpg"]} == {"manufacturer"}

    def test_undetected_fields_are_never_drawn(self):
        plan = annotate.plan_annotations(FIELDS, RULES, FIELD_LABELS)
        drawn = {b["field"] for boxes in plan.values() for b in boxes}
        assert "importer" not in drawn

    def test_fields_without_a_bounding_box_are_skipped(self):
        plan = annotate.plan_annotations(FIELDS, RULES, FIELD_LABELS)
        drawn = {b["field"] for boxes in plan.values() for b in boxes}
        assert "batch_number" not in drawn

    def test_worst_rule_status_wins(self):
        """net_quantity has one PASS and one FAIL - the inspector sees FAIL."""
        statuses = annotate.field_statuses(RULES)
        assert statuses["net_quantity"] == "FAIL"
        assert statuses["mrp"] == "PASS"
        assert statuses["manufacturer"] == "MANUAL_REVIEW"

    def test_status_colours_are_distinct(self):
        plan = annotate.plan_annotations(FIELDS, RULES, FIELD_LABELS)
        colors = {b["field"]: b["color"] for b in plan["front.jpg"]}
        assert colors["mrp"] != colors["net_quantity"]

    def test_a_field_no_rule_consumes_is_grey_not_green(self):
        plan = annotate.plan_annotations(
            {"mrp": FIELDS["mrp"]}, [], FIELD_LABELS
        )
        assert plan["front.jpg"][0]["status"] == "UNKNOWN"

    def test_malformed_bbox_does_not_raise(self):
        plan = annotate.plan_annotations(
            {"mrp": {**FIELDS["mrp"], "bbox": [["a", "b"]]}}, RULES, FIELD_LABELS
        )
        assert plan == {}

    def test_empty_input(self):
        assert annotate.plan_annotations({}, []) == {}


class TestAnnotatedImages:
    @pytest.fixture
    def surfaces(self, tmp_path):
        paths = []
        for name in ("front.jpg", "back.jpg"):
            path = tmp_path / name
            Image.new("RGB", (400, 300), (240, 240, 240)).save(path)
            paths.append(str(path))
        return paths

    def test_annotated_copies_are_written(self, surfaces, tmp_path):
        out = annotate.annotate_images(
            surfaces,
            ["front.jpg", "back.jpg"],
            FIELDS,
            RULES,
            output_dir=str(tmp_path / "evidence"),
            field_labels=FIELD_LABELS,
            inspection_id="test-1",
        )
        assert len(out) == 2
        for entry in out:
            assert os.path.exists(entry["path"])
            assert entry["path"].endswith(".annotated.png")
            assert entry["boxes"]

    def test_the_overlay_actually_changes_the_pixels(self, surfaces, tmp_path):
        out = annotate.annotate_images(
            surfaces, ["front.jpg", "back.jpg"], FIELDS, RULES,
            output_dir=str(tmp_path / "evidence"), inspection_id="test-2",
        )
        original = Image.open(surfaces[0]).convert("RGB")
        annotated = Image.open(out[0]["path"]).convert("RGB")
        assert annotated.size == original.size
        assert list(annotated.tobytes()) != list(original.tobytes())

    def test_box_metadata_travels_with_the_image(self, surfaces, tmp_path):
        out = annotate.annotate_images(
            surfaces, ["front.jpg", "back.jpg"], FIELDS, RULES,
            output_dir=str(tmp_path / "evidence"), field_labels=FIELD_LABELS,
            inspection_id="test-3",
        )
        front = next(e for e in out if e["name"] == "front.jpg")
        by_field = {b["field"]: b for b in front["boxes"]}
        assert by_field["mrp"]["value"] == "45.00"
        assert by_field["mrp"]["bbox"] == [10, 10, 200, 50]
        assert by_field["net_quantity"]["status"] == "FAIL"

    def test_missing_source_file_is_skipped_not_fatal(self, tmp_path):
        out = annotate.annotate_images(
            ["/no/such/front.jpg"], ["front.jpg"], FIELDS, RULES,
            output_dir=str(tmp_path / "evidence"), inspection_id="test-4",
        )
        assert out == []

    def test_no_evidence_produces_no_files(self, surfaces, tmp_path):
        out = annotate.annotate_images(
            surfaces, ["front.jpg", "back.jpg"], {}, RULES,
            output_dir=str(tmp_path / "evidence"), inspection_id="test-5",
        )
        assert out == []
        assert not (tmp_path / "evidence").exists()

    def test_pipeline_writes_overlays_end_to_end(self, tmp_path):
        from backend.app.services.pipeline import InspectionPipeline

        front = tmp_path / "front.jpg"
        Image.new("RGB", (500, 400), (250, 250, 250)).save(front)

        pipeline = InspectionPipeline(
            evidence_dir=str(tmp_path / "evidence"), annotate=True
        )
        texts = ["CRISPY WAFERS", "MRP: Rs. 45.00", "Net Qty: 200 g"]
        pipeline.assess_quality = lambda path: {"usable": True, "score": 95.0, "checks": {}}
        pipeline.ocr = lambda path: {
            "texts": texts,
            "confidences": [0.97] * 3,
            "bounding_boxes": [
                [[20, 20 + i * 60], [300, 20 + i * 60], [300, 60 + i * 60], [20, 60 + i * 60]]
                for i in range(3)
            ],
            "avg_confidence": 0.97,
        }
        result = pipeline.run_multi([str(front)], image_names=["front.jpg"])
        assert result["annotated_images"]
        assert os.path.exists(result["annotated_images"][0]["path"])


class TestPDFReport:
    def test_pdf_is_written_and_is_a_pdf(self, sample_result, tmp_path):
        path = pdf_report.generate_pdf_report(
            sample_result, str(tmp_path / "report.pdf")
        )
        assert os.path.exists(path)
        with open(path, "rb") as fh:
            assert fh.read(5) == b"%PDF-"
        assert os.path.getsize(path) > 2000

    def test_pdf_includes_the_inspector_signoff_when_recorded(
        self, sample_result, tmp_path
    ):
        decision = {
            "inspector_id": "insp-77",
            "inspector_name": "R. Verifier",
            "action": "OVERRIDE",
            "ai_decision": sample_result["decision"],
            "final_decision": "NON_COMPLIANT",
            "reason": "Net quantity numerals are below the required height",
            "timestamp": "2026-09-06T10:00:00Z",
            "notes": "Re-checked with a scale rule",
        }
        signed = pdf_report.generate_pdf_report(
            sample_result, str(tmp_path / "signed.pdf"), inspector_decision=decision
        )
        unsigned = pdf_report.generate_pdf_report(
            sample_result, str(tmp_path / "unsigned.pdf")
        )
        assert os.path.getsize(signed) != os.path.getsize(unsigned)

    def test_pdf_embeds_the_annotated_evidence(self, tmp_path):
        from backend.app.services.pipeline import InspectionPipeline

        front = tmp_path / "front.jpg"
        Image.new("RGB", (500, 400), (250, 250, 250)).save(front)
        pipeline = InspectionPipeline(evidence_dir=str(tmp_path / "ev"), annotate=True)
        pipeline.assess_quality = lambda p: {"usable": True, "score": 95.0, "checks": {}}
        pipeline.ocr = lambda p: {
            "texts": ["WAFERS", "MRP: Rs. 45.00", "Net Qty: 200 g"],
            "confidences": [0.97] * 3,
            "bounding_boxes": [
                [[20, 20 + i * 60], [300, 20 + i * 60], [300, 60 + i * 60], [20, 60 + i * 60]]
                for i in range(3)
            ],
            "avg_confidence": 0.97,
        }
        result = pipeline.run_multi([str(front)], image_names=["front.jpg"])
        with_images = pdf_report.generate_pdf_report(
            result, str(tmp_path / "with_images.pdf")
        )
        result_without = dict(result, annotated_images=[])
        without = pdf_report.generate_pdf_report(
            result_without, str(tmp_path / "without.pdf")
        )
        assert os.path.getsize(with_images) > os.path.getsize(without)

    def test_pdf_survives_an_early_return_result(self, tmp_path):
        """A quality-gate rejection has no fields or rules - it must still
        produce a filable report."""
        from backend.app.services.pipeline import InspectionPipeline

        pipeline = InspectionPipeline(annotate=False)
        pipeline.assess_quality = lambda p: {"usable": False, "score": 20.0, "checks": {}}
        pipeline.ocr = lambda p: {
            "texts": [], "confidences": [], "bounding_boxes": [], "avg_confidence": 0.0
        }
        result = pipeline.run_multi(["x.jpg"], image_names=["front.jpg"])
        path = pdf_report.generate_pdf_report(result, str(tmp_path / "empty.pdf"))
        assert os.path.getsize(path) > 1000

    def test_markup_in_a_field_value_cannot_break_the_pdf(self, sample_result, tmp_path):
        """OCR text is untrusted input: angle brackets must be escaped, not
        interpreted as ReportLab markup."""
        hostile = dict(sample_result)
        hostile["product_name"] = "<b>Evil</b> & <unclosed"
        hostile["extracted_fields"] = dict(sample_result["extracted_fields"])
        hostile["extracted_fields"]["mrp"] = {
            **sample_result["extracted_fields"]["mrp"],
            "value": "<font size=99>45</font>",
        }
        path = pdf_report.generate_pdf_report(hostile, str(tmp_path / "hostile.pdf"))
        assert os.path.getsize(path) > 1000


class TestRulesetVocabulary:
    """The overlay must colour fields using the *ruleset's* declaration names.

    `RuleResult.fields` carries statutory names ("retail_sale_price",
    "manufacturer_name"); `extracted_fields` is keyed by extractor names
    ("mrp", "manufacturer"). Matching them directly coloured only
    `net_quantity` — the one name both vocabularies share — so a real
    inspection drew every other declaration grey. The earlier tests missed it
    because their fixtures wrote both sides in the extractor vocabulary.
    """

    # Exactly the shape the LabelGuard engine emits.
    REAL_RULES = [
        {"rule_id": "PC2011-R06-E-001", "status": "PASS",
         "fields": ["retail_sale_price"], "source": {"category": "mrp"}},
        {"rule_id": "PC2011-R06-A-001", "status": "FAIL",
         "fields": ["manufacturer_name", "manufacturer_address"],
         "source": {"category": "manufacturer_details"}},
        {"rule_id": "PC2011-R06-B-001", "status": "PASS",
         "fields": ["common_or_generic_name"],
         "source": {"category": "commodity_identity"}},
        {"rule_id": "PC2011-R06-C-001", "status": "MANUAL_REVIEW",
         "fields": ["net_quantity", "net_quantity_unit"],
         "source": {"category": "net_quantity"}},
        {"rule_id": "PC2011-R06-D-001", "status": "PASS",
         "fields": ["manufacture_month_year"],
         "source": {"category": "date_declaration"}},
        {"rule_id": "PC2011-R06-2-001", "status": "PASS",
         "fields": ["consumer_contact_phone"],
         "source": {"category": "consumer_contact"}},
        # 22 of 31 real rules carry no field list at all
        {"rule_id": "PC2011-R12-001", "status": "MANUAL_REVIEW",
         "fields": [], "source": {"category": "quantity_language"}},
    ]

    def test_statutory_names_map_to_extractor_fields(self):
        statuses = annotate.field_statuses(self.REAL_RULES)
        assert statuses["mrp"] == "PASS"
        assert statuses["manufacturer"] == "FAIL"
        assert statuses["product_name"] == "PASS"
        assert statuses["net_quantity"] == "MANUAL_REVIEW"
        assert statuses["manufacturing_date"] == "PASS"
        assert statuses["consumer_care"] == "PASS"

    def test_a_rule_with_no_field_list_falls_back_to_its_category(self):
        statuses = annotate.field_statuses(
            [self.REAL_RULES[-1]]  # quantity_language, fields: []
        )
        assert statuses["net_quantity"] == "MANUAL_REVIEW"

    def test_real_rules_do_not_leave_declarations_uncoloured(self):
        """The regression itself: nearly everything used to come back UNKNOWN."""
        fields = {
            name: {
                "value": "x",
                "bbox": _box(10, i * 40, 200, i * 40 + 30),
                "source_image": "front.jpg",
                "extraction_confidence": 0.9,
            }
            for i, name in enumerate(
                ["mrp", "manufacturer", "product_name", "net_quantity",
                 "manufacturing_date", "consumer_care"]
            )
        }
        plan = annotate.plan_annotations(fields, self.REAL_RULES, FIELD_LABELS)
        drawn = plan["front.jpg"]
        unknown = [b["field"] for b in drawn if b["status"] == "UNKNOWN"]
        assert not unknown, f"declarations left uncoloured: {unknown}"

    def test_physical_measurement_declarations_stay_unmapped(self):
        """`dimensions` has no extracted counterpart - mapping it would invent
        a link that does not exist."""
        statuses = annotate.field_statuses(
            [{"rule_id": "R", "status": "FAIL", "fields": ["sheet_dimensions"],
              "source": {"category": "dimensions"}}]
        )
        assert statuses == {}

    def test_every_ruleset_declaration_name_is_considered(self):
        """A new declaration name in the ruleset must be mapped deliberately,
        not silently dropped."""
        import json
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent
            / "backend" / "app" / "rules" / "labelguard_rules_draft.json"
        )
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        declared = set()
        for rule in data["rules"]:
            validation = rule.get("validation", {}) or {}
            for key in ("fields", "required_fields"):
                value = validation.get(key)
                if isinstance(value, list):
                    declared.update(value)
        # physical measurements are intentionally absent from the map
        physical = {"dimensions", "sheet_dimensions", "usable_sheet_count"}
        unmapped = declared - set(annotate.DECLARATION_TO_FIELDS) - physical
        assert not unmapped, f"unmapped ruleset declarations: {sorted(unmapped)}"
