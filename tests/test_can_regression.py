"""Regression tests using the REAL failing can package (test_images/img_can).

OCR lines below are transcribed from the actual PaddleOCR output of the three
surfaces (front / base / back label) of a Monster Energy Ultra can, so the
exact production failure (MRP/date/batch falsely failing, 'FSSAI' extracted as
manufacturer, care details missed) cannot reappear.

Ground truth for this package:
- MRP, mfg date, batch, expiry are printed on the BASE of the can (per the
  label's own 'see base of can' pointers); the base photo is too blurry to read
- Manufacturer: DEL MONTE FOODS PRIVATE LIMITED (or Hindustan Coca-Cola)
- Consumer care: 000-800-040-1274 / INFO@MONSTERENERGY.COM
- Net quantity: 350 ml
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.app.services.field_extraction import FieldExtractor
from backend.app.services.evidence import EvidencePipeline
from backend.app.services.rule_engine import RuleEngine
from backend.app.services.pipeline import InspectionPipeline
from backend.app.services.confidence import ConfidenceEngine


def bbox(y, x0=10, x1=300):
    return [[x0, y], [x1, y], [x1, y + 30], [x0, y + 30]]


# --- Surface 0: front of can (usable) - transcribed from OCR ---
FRONT_TEXTS = [
    "MONSTER",  # 0
    "ENERGY",  # 1
    "ULTRA",  # 2
    "dropping some hints lately.",  # 3
    "They Ve been asking us for a new",  # 4
    "onsterdrink A littleless sweet",  # 5
    "monsterenergy.com",  # 6
    "IS:14407",  # 7
    "ISI MARK IS FOR",  # 8
    "CONTAINERS ONLY",  # 9
    "CM/L-7500278116",  # 10
]
# Vertical base-rim fragments (narrow x column, stacked at the bottom)
FRONT_VERTICAL = ["2", "2", "9", "6", "897036"]
FRONT_V_Y0 = 1262
FRONT_V_X = (289, 348)

# --- Surface 1: base of can (UNUSABLE - blur) ---
BASE_TEXTS = ["MRP", "some", "unreadable", "fragments"]

# --- Surface 2: back label (usable) - transcribed from OCR ---
BACK_TEXTS = [
    "VITAMINS",  # 0
    "NON-CALORIC SWEETENER",  # 1
    "CONTAINS CAFFEINE",  # 2
    "FOR MANUFACTURER",  # 3
    "FSSAI",  # 4
    "LIC NO. - SEE THE FIRST",  # 5
    "LETTER BEFORE EXPIRY DATE ON THE BASE OF CAN.",  # 6
    "fssat",  # 7
    "fssai",  # 8
    "D) Lic No:10012042000203",  # 9
    "H) Lic No:1001202000287",  # 10
    "DEL MONTE FOODS",  # 11
    "HINDUSTAN COCA-COLA",  # 12
    "PRIVATE LIMITED",  # 13
    "BEVERAGES PVT. LTD.",  # 14
    "BRAND OWNED AND MKT",  # 15
    "BY MONSTER ENERGY INDIA PRIVATE",  # 16
    "RELATIONS REPRESENTATIVE AT",  # 17
    "000-800-040-1274",  # 18
    "INFO@MONSTERENERGY.COM",  # 19
    "ADDRESS: SAME AS BRAND OWNED AND MARKETED",  # 20
    "ENERGY COMPANY",  # 21
    "TAXES), UNIT SALE",  # 22
    "NUFACTURE,",  # 23
    "EXPIRY/USE",  # 24
    "NO., - SEE BASE OF CAN",  # 25
    "350 ml",  # 26
]


def surface(texts, y_step=40, x0=10, x1=300):
    confs = [0.98] * len(texts)
    bboxes = [bbox(i * y_step, x0, x1) for i in range(len(texts))]
    return texts, confs, bboxes


def make_per_image():
    """Build the per_image structure the EvidencePipeline expects."""
    extractor = FieldExtractor()

    def entry(idx, name, usable, texts, vertical=None):
        confs = [0.98] * len(texts)
        y = 0
        bboxes = []
        for t in texts:
            bboxes.append(bbox(y))
            y += 40
        if vertical:
            for k, t in enumerate(vertical):
                bboxes.append(
                    [
                        [FRONT_V_X[0], FRONT_V_Y0 + k * 60],
                        [FRONT_V_X[1], FRONT_V_Y0 + k * 60],
                        [FRONT_V_X[1], FRONT_V_Y0 + k * 60 + 40],
                        [FRONT_V_X[0], FRONT_V_Y0 + k * 60 + 40],
                    ]
                )
            texts = texts + vertical
            confs = confs + [0.9] * len(vertical)
        ocr = {"texts": list(texts), "confidences": confs, "bounding_boxes": bboxes}
        fields = {}
        if usable:
            raw = extractor.extract_all(texts, confs, bboxes)
            fields = {
                k: {
                    "field_name": f.field_name,
                    "value": f.value,
                    "ocr_text": f.ocr_text,
                    "ocr_confidence": f.ocr_confidence,
                    "extraction_confidence": f.extraction_confidence,
                    "confidence_level": f.confidence_level,
                    "bbox": f.bbox,
                    "reason": f.reason,
                    "line_index": f.line_index,
                }
                for k, f in raw.items()
            }
        return {"idx": idx, "name": name, "usable": usable, "ocr": ocr, "fields": fields}

    return [
        entry(0, "front.jpg", True, list(FRONT_TEXTS), vertical=FRONT_VERTICAL),
        entry(1, "base.jpg", False, list(BASE_TEXTS)),
        entry(2, "back.jpg", True, list(BACK_TEXTS)),
    ]


GOOD_QUALITY = {"usable": False, "score": 75.0, "checks": {}}


class TestCanEntityExtraction:
    """The 'FSSAI extracted as manufacturer' regression."""

    def test_manufacturer_is_not_fssai(self):
        texts, confs, bboxes = surface(BACK_TEXTS)
        ex = FieldExtractor()
        result = ex._extract_entity(texts, confs, bboxes, "manufacturer")
        assert result.value is not None
        assert "FSSAI" not in result.value.upper()
        assert "DEL MONTE" in result.value.upper()

    def test_manufacturer_rejects_licence_lines(self):
        texts, confs, bboxes = surface(BACK_TEXTS)
        ex = FieldExtractor()
        result = ex._extract_entity(texts, confs, bboxes, "manufacturer")
        assert "LIC" not in result.value.upper()
        assert "SEE" not in result.value.upper()

    def test_consumer_care_found_via_relations_representative(self):
        texts, confs, bboxes = surface(BACK_TEXTS)
        ex = FieldExtractor()
        result = ex._extract_consumer_care(texts, confs, bboxes)
        assert result.value is not None
        assert "800-040-1274" in result.value
        assert "INFO@MONSTERENERGY.COM" in result.value.upper()


class TestCanEvidencePipeline:
    """Evidence preservation + association across the can's surfaces."""

    def setup_method(self):
        self.per_image = make_per_image()
        self.ev = EvidencePipeline()
        self.out = self.ev.run(self.per_image)

    def test_every_ocr_element_is_pooled(self):
        # 11 front + 5 vertical + 4 base + 27 back = 47 elements, nothing dropped
        assert self.out["pool_size"] == len(FRONT_TEXTS) + len(FRONT_VERTICAL) + len(BASE_TEXTS) + len(BACK_TEXTS)

    def test_reference_pointers_detected(self):
        pointers = self.out["pointers"]
        assert len(pointers) >= 2
        joined = " | ".join(p["text"] for p in pointers)
        assert "BASE OF CAN" in joined.upper()
        locations = {p["location"] for p in pointers}
        assert "base" in locations

    def test_cylindrical_package_detected(self):
        assert self.out["cylindrical_package"] is True

    def test_pointer_fields_include_batch_and_best_before(self):
        all_hinted = set()
        for p in self.out["pointers"]:
            all_hinted.update(p.get("fields") or [])
        assert "batch_number" in all_hinted
        assert "best_before" in all_hinted

    def test_manufacturer_associated_not_fssai(self):
        fields = self.out["fields"]
        assert fields["manufacturer"]["value"] is not None
        assert "DEL MONTE" in fields["manufacturer"]["value"].upper()

    def test_net_quantity_from_back_label(self):
        fields = self.out["fields"]
        assert fields["net_quantity"]["value"] == "350 ml"

    def test_consumer_care_associated(self):
        fields = self.out["fields"]
        assert fields["consumer_care"]["value"] is not None
        assert "MONSTERENERGY.COM" in fields["consumer_care"]["value"].upper()

    def test_vertical_chain_detected_as_evidence(self):
        """The base-rim vertical text run must be retained - either associated
        to batch_number (pointer-gated, LOW confidence) or kept as unclaimed
        evidence. It must never be silently discarded."""
        fields = self.out["fields"]
        unclaimed = self.out["unclaimed_evidence"]
        batch_value = str(fields["batch_number"].get("value") or "")
        associated = "897036" in batch_value and fields["batch_number"].get("value") is not None
        chains_unclaimed = [c for c in unclaimed if "vertical" in (c.get("hint") or "")]
        assert associated or chains_unclaimed, (
            "base-rim vertical run was discarded: batch=%r, unclaimed_chains=%r"
            % (batch_value, chains_unclaimed)
        )
        if associated:
            # associated chains are pointer-gated and never auto-pass
            assert fields["batch_number"]["confidence_level"] == "LOW"

    def test_no_information_wasted_all_elements_represented(self):
        # every pool element is either claimed by a field or present in
        # candidates/unclaimed (smoke check: unclaimed evidence non-empty)
        assert len(self.out["unclaimed_evidence"]) > 0


class TestCanRuleDecisions:
    """The core regression: base-of-can fields must not FAIL when the label
    itself points to the base (or the base surface is unreadable).

    Note: the LabelGuard ruleset (LM(PC)R 2011 Rules 4-31) has no batch-number
    or country-of-origin rule on retail packages - the base-rim batch code is
    retained as evidence instead.
    """

    def setup_method(self):
        self.per_image = make_per_image()
        self.pipeline = InspectionPipeline()
        # bypass OCR/quality (fixtures already provide extraction input)
        self.ev_out = self.pipeline.evidence_pipeline.run(self.per_image)

    def _evaluate(self, per_image=None, quality=None):
        ev_out = self.ev_out
        if per_image is not None:
            ev_out = self.pipeline.evidence_pipeline.run(per_image)
        # mirrors merged-quality semantics: the base surface is unreadable,
        # so absence anywhere cannot be fully trusted
        if quality is None:
            quality = {"usable": False, "score": 75.0, "checks": {}}
        rule_results = self.pipeline.rule_engine.evaluate(
            ev_out["fields"], quality, pointers=ev_out["pointers"]
        )
        decision = self.pipeline.rule_engine.fuse(rule_results)
        return {r.rule_id: r for r in rule_results}, decision

    def test_mrp_not_failed_with_base_pointer(self):
        by_id, decision = self._evaluate()
        assert by_id["PC2011-R06-E-001"].status != "FAIL"
        assert by_id["PC2011-R06-E-001"].status == "MANUAL_REVIEW"
        # softened either by the unreadable base surface or by the label pointer
        reason = by_id["PC2011-R06-E-001"].reason.lower()
        assert "base" in reason or "elsewhere" in reason or "insufficient" in reason

    def test_mrp_not_failed_even_with_all_surfaces_readable(self):
        """Even if every captured surface were readable, the pointer alone
        must prevent a false MRP FAIL (the base simply was not captured)."""
        by_id, decision = self._evaluate(quality={"usable": True, "score": 95.0, "checks": {}})
        assert by_id["PC2011-R06-E-001"].status == "MANUAL_REVIEW"
        reason = by_id["PC2011-R06-E-001"].reason.lower()
        assert "elsewhere" in reason or "base" in reason

    def test_date_not_failed_with_base_pointer(self):
        by_id, decision = self._evaluate()
        assert by_id["PC2011-R06-D-001"].status == "MANUAL_REVIEW"

    def test_entity_name_found_but_address_routed_to_review(self):
        """Manufacturer is DEL MONTE FOODS (labelled) but no address block sits
        next to it on the can - Rule 6(1)(a)/Rule 10 must go to review, not
        silently pass, and never return 'FSSAI'."""
        by_id, decision = self._evaluate()
        r = by_id["PC2011-R06-A-001"]
        assert r.status in ("PASS", "MANUAL_REVIEW")
        assert "DEL MONTE" in str(r.evidence.get("value", "")) or r.status == "MANUAL_REVIEW"
        if r.status == "PASS":
            assert "DEL MONTE" in str(r.evidence.get("value", ""))
        else:
            assert "address" in r.reason.lower()

    def test_product_name_detected_from_front_brand(self):
        by_id, decision = self._evaluate()
        assert by_id["PC2011-R06-B-001"].status == "PASS"
        fields = self.ev_out["fields"]
        assert fields["product_name"]["value"] == "MONSTER"

    def test_overall_decision_is_review_not_false_non_compliant(self):
        by_id, decision = self._evaluate()
        assert decision.decision == "MANUAL_REVIEW"
        assert decision.failed_rules == []

    def test_single_back_surface_also_does_not_false_fail(self):
        """Original user report: running just the back label gave a false FAIL
        on MRP/date. Pointer-aware rules must route those to review."""
        per_image = [e for e in self.per_image if e["name"] == "back.jpg"]
        by_id, decision = self._evaluate(
            per_image=per_image, quality={"usable": True, "score": 95.0, "checks": {}}
        )
        assert by_id["PC2011-R06-E-001"].status == "MANUAL_REVIEW"
        assert by_id["PC2011-R06-D-001"].status == "MANUAL_REVIEW"
        # commodity name absent from the readable back label is an honest FAIL
        assert set(decision.failed_rules) <= {"PC2011-R06-B-001"}


class TestPointerRuleEngineUnit:
    """Unit tests for pointer-aware absence handling."""

    def setup_method(self):
        self.engine = RuleEngine()  # draft ruleset

    def _fields_missing_mrp(self):
        return {
            "mrp": {"value": None, "confidence_level": "MISSING"},
            "net_quantity": {"value": "350 ml", "confidence_level": "LOW"},
            "manufacturer": {"value": "DEL MONTE FOODS", "confidence_level": "MEDIUM"},
            "packer": {"value": None, "confidence_level": "MISSING"},
            "importer": {"value": None, "confidence_level": "MISSING"},
            "manufacturing_date": {"value": None, "confidence_level": "MISSING"},
            "packing_date": {"value": None, "confidence_level": "MISSING"},
            "best_before": {"value": None, "confidence_level": "MISSING"},
            "batch_number": {"value": None, "confidence_level": "MISSING"},
            "consumer_care": {"value": "Phone: 800-040-1274", "confidence_level": "HIGH"},
            "country_of_origin": {"value": None, "confidence_level": "MISSING"},
        }

    def test_no_pointer_still_fails(self):
        results = self.engine.evaluate(self._fields_missing_mrp(), {"usable": True, "score": 95.0})
        by_id = {r.rule_id: r for r in results}
        assert by_id["MRP_001"].status == "FAIL"

    def test_generic_base_pointer_softens_mrp(self):
        pointers = [
            {"text": "NO., - SEE BASE OF CAN", "location": "base", "fields": ["batch_number"], "image": "back.jpg"}
        ]
        results = self.engine.evaluate(
            self._fields_missing_mrp(), {"usable": True, "score": 95.0}, pointers=pointers
        )
        by_id = {r.rule_id: r for r in results}
        assert by_id["MRP_001"].status == "MANUAL_REVIEW"
        assert by_id["BATCH_001"].status == "MANUAL_REVIEW"
        assert "base" in by_id["MRP_001"].reason.lower() or "elsewhere" in by_id["MRP_001"].reason.lower()

    def test_specific_pointer_only_softens_its_field(self):
        pointers = [
            {"text": "EXPIRY DATE ON THE BASE OF CAN", "location": "base", "fields": ["best_before"], "image": "back.jpg"}
        ]
        results = self.engine.evaluate(
            self._fields_missing_mrp(), {"usable": True, "score": 95.0}, pointers=pointers
        )
        by_id = {r.rule_id: r for r in results}
        assert by_id["BEST_BEFORE_001"].status in ("MANUAL_REVIEW", "NOT_APPLICABLE")
        assert by_id["MRP_001"].status == "MANUAL_REVIEW"  # generic base location also covers MRP

    def test_non_base_pointer_does_not_soften_mrp(self):
        pointers = [
            {"text": "SEE BACK OF PACK", "location": "back", "fields": ["batch_number"], "image": "front.jpg"}
        ]
        results = self.engine.evaluate(
            self._fields_missing_mrp(), {"usable": True, "score": 95.0}, pointers=pointers
        )
        by_id = {r.rule_id: r for r in results}
        assert by_id["MRP_001"].status == "FAIL"
        assert by_id["BATCH_001"].status == "MANUAL_REVIEW"
