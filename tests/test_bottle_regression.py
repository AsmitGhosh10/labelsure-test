"""Regression tests using the REAL bottle package (test_images/image_bottle).

Transcribed from actual PaddleOCR output of a Varun Beverages / PepsiCo
bottle (3 surfaces: neck macro + two label sides). All three photos were
WRONGLY rejected by the blur gate (Laplacian 7.85-54.21) despite being
perfectly readable (OCR avg conf 0.96-0.97) - the OCR-evidence rescue and
neck-pointer handling below pin the correct behaviour.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.app.services.field_extraction import FieldExtractor
from backend.app.services.evidence import EvidencePipeline
from backend.app.services.pipeline import InspectionPipeline


def bbox(y, x0=10, x1=300):
    return [[x0, y], [x1, y], [x1, y + 30], [x0, y + 30]]


# --- Surface 0: bottle neck (gate-rejected for blur, OCR-readable) ---
NECK_TEXTS = ["CN5255D16G26", "USEBY12/04/27"]

# --- Surface 1: back label (gate-rejected for blur, OCR-readable) ---
LABEL_BACK_TEXTS = [
    "WATER TREATMENT THROUGH: SAND FILTRATION, ACTIVATED CARBON FILTRATION,U.V. TREATMENT",
    "INGREDIENTS: TREATED WATER, MINERALS (SALTS OF MAGNESIUM AND CALCIUM).",
    "MFD. BY: VARUN BEVERAGES LIMITED",
    "CONTACT CUSTOMER SERVICE",
    "CONSUMER.FEEDBAC",
    "SEE NECK FOR BATCH NO.,",
    "MFD., USE BY DATE,",
    "NET QUANTIT",
    "MRP. 7 (INCL. OF ALL",
    "L TAXES), USP.",
    "500ml",
    "NET QUANTITY:",
]

# --- Surface 2: other label side (gate-rejected for blur, OCR-readable) ---
LABEL_SIDE_TEXTS = [
    "MFD. BY: VARUN BEVERAGES LIMITED",
    "MKT. BY: PEPSICO INDIA HOLDINGS PVTT",
    "LIC. NO.10014064000435",
    "CONTACT CUSTOMER SERVICE MANAGER AT: P.O. BOX 27,",
    "DLF QUTAB ENCLAVE-I, GURUGRAM -122002, HARYANA",
    "CONSUMER.FEEDBACK@PEPSICO.COM",
    "1800 22 4020",
]


def make_per_image():
    extractor = FieldExtractor()

    def entry(idx, name, usable, texts):
        confs = [0.97] * len(texts)
        bboxes = [bbox(i * 40) for i in range(len(texts))]
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
        entry(0, "neck.jpg", True, NECK_TEXTS),
        entry(1, "label_back.jpg", True, LABEL_BACK_TEXTS),
        entry(2, "label_side.jpg", True, LABEL_SIDE_TEXTS),
    ]


class TestBottleLabelledExtraction:
    """Keyword and pattern gaps the bottle exposed."""

    def test_mfd_by_extracts_manufacturer(self):
        ex = FieldExtractor()
        result = ex._extract_entity(
            ["MFD. BY: VARUN BEVERAGES LIMITED"], [0.98], [bbox(0)]
            , "manufacturer",
        ) if False else ex._extract_entity(
            ["MFD. BY: VARUN BEVERAGES LIMITED"],
            [0.98],
            [bbox(0)],
            "manufacturer",
        )
        assert result.value == "VARUN BEVERAGES LIMITED"
        assert result.confidence_level == "HIGH"

    def test_mkt_by_extracts_manufacturer(self):
        ex = FieldExtractor()
        result = ex._extract_entity(
            ["MKT. BY: PEPSICO INDIA HOLDINGS PVTT"], [0.96], [bbox(0)], "manufacturer"
        )
        assert result.value is not None
        assert "PEPSICO" in result.value

    def test_useby_embedded_date_extracted(self):
        """'USEBY12/04/27' - date embedded in a token, no word boundaries."""
        ex = FieldExtractor()
        result = ex._extract_date(["USEBY12/04/27"], [0.99], [bbox(0)], "best_before")
        assert result.value == "12/04/27"

    def test_mrp_fragment_line(self):
        """'MRP. 7 (INCL. OF ALL' + 'L TAXES), USP.' - fragmented MRP line."""
        ex = FieldExtractor()
        texts = ["MRP. 7 (INCL. OF ALL", "L TAXES), USP."]
        result = ex._extract_mrp(texts, [0.95, 0.99], [bbox(0), bbox(40)])
        assert result.value is not None
        assert "7" in result.value

    def test_net_quantity_value_before_label(self):
        """'500ml' on the OCR line BEFORE its 'NET QUANTITY:' label."""
        ex = FieldExtractor()
        texts = ["NO.,", "500ml", "NET QUANTITY:"]
        result = ex._extract_net_quantity(texts, [0.99] * 3, [bbox(0), bbox(40), bbox(80)])
        assert result.value == "500ml"

    def test_consumer_care_via_customer_service_email(self):
        ex = FieldExtractor()
        texts = [
            "CONTACT CUSTOMER SERVICE MANAGER AT: P.O. BOX 27,",
            "DLF QUTAB ENCLAVE-I, GURUGRAM -122002, HARYANA",
            "CONSUMER.FEEDBACK@PEPSICO.COM",
            "1800 22 4020",
        ]
        result = ex._extract_consumer_care(texts, [0.99] * 4, [bbox(i * 40) for i in range(4)])
        assert result.value is not None
        assert "CONSUMER.FEEDBACK@PEPSICO.COM" in result.value.upper()


class TestBottleEvidencePipeline:
    """Cross-surface evidence: neck carries batch + use-by; label points there."""

    def setup_method(self):
        self.ev = EvidencePipeline()
        self.out = self.ev.run(make_per_image())

    def test_neck_pointer_detected_with_continuation(self):
        pointers = self.out["pointers"]
        assert pointers, "expected the SEE NECK pointer to be detected"
        neck = [p for p in pointers if p["location"] == "neck"]
        assert neck, f"no neck pointer: {pointers}"
        text = neck[0]["text"]
        assert "BATCH NO" in text.upper()
        assert "USE BY DATE" in text.upper()
        assert "NET QUANTIT" in text.upper()

    def test_neck_pointer_hints_cover_all_fields(self):
        neck = [p for p in self.out["pointers"] if p["location"] == "neck"][0]
        assert set(neck["fields"]) >= {
            "batch_number",
            "best_before",
            "manufacturing_date",
            "net_quantity",
        }

    def test_cylindrical_detected_from_neck_pointer(self):
        assert self.out["cylindrical_package"] is True

    def test_batch_associated_from_neck_surface(self):
        fields = self.out["fields"]
        assert fields["batch_number"]["value"] == "CN5255D16G26"
        assert fields["batch_number"]["source_image"] == "neck.jpg"

    def test_useby_date_not_stolen_by_manufacturing_date(self):
        """The only date on the package says USEBY - it must satisfy
        best_before, never manufacturing_date."""
        fields = self.out["fields"]
        assert fields["best_before"]["value"] is not None
        assert fields["manufacturing_date"]["value"] is None

    def test_manufacturer_is_labelled_varun_beverages(self):
        fields = self.out["fields"]
        assert fields["manufacturer"]["value"] == "VARUN BEVERAGES LIMITED"
        assert fields["manufacturer"]["confidence_level"] in ("HIGH", "MEDIUM")

    def test_mrp_found_from_fragment(self):
        fields = self.out["fields"]
        assert fields["mrp"]["value"] is not None
        assert "7" in fields["mrp"]["value"]

    def test_origin_absent_no_false_association(self):
        """No origin text and no origin label anywhere - must stay MISSING,
        never invented from the address or company names."""
        fields = self.out["fields"]
        assert fields["country_of_origin"]["value"] is None


class TestBottleRuleDecisions:
    """LabelGuard (LM(PC)R 2011) outcomes for the bottle surfaces.

    Note: the 2011 ruleset has no country-of-origin rule (that arrived with
    the 2017 amendment) - the honest open item here is the commodity name,
    which lives on the uncaptured front brand panel.
    """

    def setup_method(self):
        self.per_image = make_per_image()
        self.pipeline = InspectionPipeline()
        self.ev_out = self.pipeline.evidence_pipeline.run(self.per_image)

    def _evaluate(self):
        quality = {"usable": True, "score": 95.0, "checks": {}}
        rule_results = self.pipeline.rule_engine.evaluate(
            self.ev_out["fields"], quality, pointers=self.ev_out["pointers"]
        )
        decision = self.pipeline.rule_engine.fuse(rule_results)
        return {r.rule_id: r for r in rule_results}, decision

    def test_core_declarations_pass(self):
        by_id, _ = self._evaluate()
        assert by_id["PC2011-R06-E-001"].status == "PASS"   # MRP ₹7
        assert by_id["PC2011-R06-C-001"].status == "PASS"   # 500 ml
        assert by_id["PC2011-R06-2-001"].status == "PASS"   # care phone + email
        assert by_id["PC2011-R09-001"].status == "PASS"     # legibility proxy
        assert by_id["PC2011-R12-6-001"].status == "PASS"   # no misleading wording
        assert by_id["PC2011-R13-001"].status == "PASS"     # ml below 1 l

    def test_manufacturer_address_routed_to_review(self):
        """VARUN BEVERAGES is detected, but the label itself says the
        manufacturing-unit address is behind a QR/first-letter reference -
        Rule 6(1)(a)/Rule 10 must go to review, not pass silently."""
        by_id, _ = self._evaluate()
        for rule_id in ("PC2011-R06-A-001", "PC2011-R10-001"):
            r = by_id[rule_id]
            assert r.status == "MANUAL_REVIEW", f"{rule_id}: {r.reason}"
            assert "address" in r.reason.lower()

    def test_mfg_date_routed_to_review_via_neck_pointer(self):
        by_id, _ = self._evaluate()
        assert by_id["PC2011-R06-D-001"].status == "MANUAL_REVIEW"
        reason = by_id["PC2011-R06-D-001"].reason.lower()
        assert "neck" in reason or "elsewhere" in reason or "label states" in reason

    def test_best_before_from_neck_not_treated_as_mfg_date(self):
        fields = self.ev_out["fields"]
        assert fields["best_before"]["value"] == "12/04/27"
        assert fields["manufacturing_date"]["value"] is None

    def test_commodity_name_is_the_honest_fail(self):
        """No commodity name on neck/label surfaces (it is on the uncaptured
        front brand panel) - the one honest FAIL, mirrored by the Rule 4
        aggregate."""
        by_id, decision = self._evaluate()
        assert decision.failed_rules == ["PC2011-R06-B-001", "PC2011-R04-001"]
        assert decision.decision == "NON_COMPLIANT"
