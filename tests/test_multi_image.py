import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.app.services.pipeline import InspectionPipeline


def make_entry(idx, name, usable=True, score=90.0, fields=None, ocr_avg=0.95, n_lines=10):
    return {
        "idx": idx,
        "name": name,
        "usable": usable,
        "quality": {"usable": usable, "score": score},
        "ocr": (
            {"texts": ["x"] * n_lines, "avg_confidence": ocr_avg} if usable else None
        ),
        "fields": fields or {},
    }


def field(name, value, ext=0.9, ocr=0.95, level="HIGH"):
    return {
        "field_name": name,
        "value": value,
        "ocr_text": f"{name}: {value}",
        "ocr_confidence": ocr,
        "extraction_confidence": ext,
        "confidence_level": level,
        "bbox": [[0, 0], [10, 0], [10, 10], [0, 10]],
        "reason": "",
        "line_index": 0,
    }


class TestMergeFields:
    def setup_method(self):
        self.pipeline = InspectionPipeline()

    def test_field_found_only_on_second_surface(self):
        entries = [
            make_entry(0, "front.jpg", fields={"mrp": field("mrp", "₹20.00")}),
            make_entry(1, "back.jpg", fields={"batch_number": field("batch_number", "B05P")}),
        ]
        merged = self.pipeline._merge_fields(entries)
        assert merged["mrp"]["value"] == "₹20.00"
        assert merged["mrp"]["source_image"] == "front.jpg"
        assert merged["batch_number"]["value"] == "B05P"
        assert merged["batch_number"]["source_image"] == "back.jpg"
        assert merged["consumer_care"]["value"] is None
        assert merged["consumer_care"]["source_image"] is None

    def test_best_confidence_detection_wins(self):
        weak = field("mrp", "₹20", ext=0.6, level="LOW")
        strong = field("mrp", "₹20.00", ext=0.9, level="HIGH")
        entries = [
            make_entry(0, "front.jpg", fields={"mrp": weak}),
            make_entry(1, "back.jpg", fields={"mrp": strong}),
        ]
        merged = self.pipeline._merge_fields(entries)
        assert merged["mrp"]["value"] == "₹20.00"
        assert merged["mrp"]["source_image"] == "back.jpg"

    def test_tie_goes_to_earlier_surface(self):
        entries = [
            make_entry(0, "front.jpg", fields={"mrp": field("mrp", "₹20.00", ext=0.9)}),
            make_entry(1, "back.jpg", fields={"mrp": field("mrp", "₹20.00", ext=0.9)}),
        ]
        merged = self.pipeline._merge_fields(entries)
        assert merged["mrp"]["source_image"] == "front.jpg"

    def test_missing_stub_has_all_keys(self):
        merged = self.pipeline._merge_fields([make_entry(0, "front.jpg")])
        stub = merged["net_quantity"]
        for key in ("field_name", "value", "confidence_level", "bbox", "source_image"):
            assert key in stub
        assert stub["confidence_level"] == "MISSING"


class TestMergedQualityAndOCR:
    def setup_method(self):
        self.pipeline = InspectionPipeline()

    def test_one_unusable_surface_blocks_absence_trust(self):
        entries = [
            make_entry(0, "front.jpg", usable=True, score=90.0),
            make_entry(1, "back.jpg", usable=False, score=40.0),
        ]
        merged = self.pipeline._merged_quality(entries)
        assert merged["usable"] is False
        assert merged["surfaces_usable"] == 1
        assert merged["score"] == pytest.approx(65.0)

    def test_all_usable(self):
        entries = [make_entry(0, "a.jpg", score=80.0), make_entry(1, "b.jpg", score=90.0)]
        merged = self.pipeline._merged_quality(entries)
        assert merged["usable"] is True
        assert merged["score"] == pytest.approx(85.0)

    def test_weighted_ocr_confidence(self):
        entries = [
            make_entry(0, "a.jpg", ocr_avg=0.90, n_lines=10),
            make_entry(1, "b.jpg", ocr_avg=0.98, n_lines=30),
        ]
        merged = self.pipeline._merged_ocr(entries)
        assert merged["avg_confidence"] == pytest.approx((0.90 * 10 + 0.98 * 30) / 40)
        assert len(merged["texts"]) == 40

    def test_no_text(self):
        entries = [make_entry(0, "a.jpg", ocr_avg=0.0, n_lines=0)]
        merged = self.pipeline._merged_ocr(entries)
        assert merged["avg_confidence"] == 0.0
        assert merged["texts"] == []


class TestRunMultiIntegration:
    """End-to-end run_multi with the OCR step mocked (real extraction/rules)."""

    def setup_method(self):
        self.pipeline = InspectionPipeline()

    def _bbox(self, y):
        return [[0, y], [200, y], [200, y + 40], [0, y + 40]]

    def test_front_back_merge_produces_correct_verdict(self):
        front_texts = ["DEMO SNACK", "MRP: Rs. 20.00", "Net Qty: 100 g"]
        back_texts = [
            "Manufactured By: ABC Foods Pvt Ltd",
            "Plot 5, Industrial Estate, Mumbai, Maharashtra",
            "Mfg. Date: 15/01/2026",
            "Batch No.: A25X77",
            "Customer Care: 1800-123-4567",
            "Product of India",
        ]

        def fake_ocr(path):
            if "front" in path:
                texts, y0 = front_texts, 0
            else:
                texts, y0 = back_texts, 0
            return {
                "texts": texts,
                "confidences": [0.99] * len(texts),
                "bounding_boxes": [self._bbox(y0 + i * 60) for i in range(len(texts))],
                "avg_confidence": 0.99,
            }

        self.pipeline.assess_quality = lambda path: {
            "usable": True, "score": 90.0, "checks": {}
        }
        self.pipeline.ocr = fake_ocr

        result = self.pipeline.run_multi(
            ["fake_front.jpg", "fake_back.jpg"],
            image_names=["front.jpg", "back.jpg"],
            product_name="Test Snack",
        )

        assert result["coverage"] == {"surfaces_total": 2, "surfaces_usable": 2}
        assert result["extracted_fields"]["mrp"]["source_image"] == "front.jpg"
        assert result["extracted_fields"]["net_quantity"]["source_image"] == "front.jpg"
        assert result["extracted_fields"]["product_name"]["source_image"] == "front.jpg"
        assert (
            result["extracted_fields"]["manufacturing_date"]["source_image"]
            == "back.jpg"
        )
        assert result["extracted_fields"]["batch_number"]["source_image"] == "back.jpg"

        by_id = {r["rule_id"]: r for r in result["rule_results"]}
        assert by_id["PC2011-R06-E-001"]["status"] == "PASS"   # MRP
        assert by_id["PC2011-R06-B-001"]["status"] == "PASS"   # commodity name
        assert by_id["PC2011-R06-C-001"]["status"] == "PASS"   # net quantity
        assert by_id["PC2011-R06-D-001"]["status"] == "PASS"   # mfg date
        assert by_id["PC2011-R06-A-001"]["status"] == "PASS"   # manufacturer + address
        assert by_id["PC2011-R06-2-001"]["status"] == "PASS"   # consumer contact
        assert by_id["PC2011-R10-001"]["status"] == "PASS"     # complete address
        assert result["decision"] == "COMPLIANT"

    def test_unreadable_surface_softens_absence_fail(self):
        """MRP missing everywhere + one blurry surface -> MANUAL_REVIEW."""
        back_texts = ["Manufactured By: ABC Foods Pvt Ltd"]

        def fake_ocr(path):
            return {
                "texts": back_texts,
                "confidences": [0.99],
                "bounding_boxes": [self._bbox(0)],
                "avg_confidence": 0.99,
            }

        self.pipeline.ocr = fake_ocr

        def fake_quality(path):
            if "front" in path:
                return {"usable": False, "score": 40.0, "checks": {}}
            return {"usable": True, "score": 90.0, "checks": {}}

        self.pipeline.assess_quality = fake_quality

        result = self.pipeline.run_multi(
            ["fake_front.jpg", "fake_back.jpg"],
            image_names=["front.jpg", "back.jpg"],
        )
        assert result["coverage"] == {"surfaces_total": 2, "surfaces_usable": 1}
        by_id = {r["rule_id"]: r for r in result["rule_results"]}
        assert by_id["PC2011-R06-E-001"]["status"] == "MANUAL_REVIEW"
        assert result["decision"] == "MANUAL_REVIEW"

    def test_all_surfaces_unusable(self):
        self.pipeline.assess_quality = lambda path: {
            "usable": False, "score": 30.0, "checks": {}
        }
        self.pipeline.ocr = lambda path: {
            "texts": [], "confidences": [], "bounding_boxes": [], "avg_confidence": 0.0
        }
        result = self.pipeline.run_multi(["fake.jpg"], image_names=["front.jpg"])
        assert result["decision"] == "MANUAL_REVIEW"
        assert result["rule_results"] == []

    def test_ocr_evidence_rescues_gate_rejected_surface(self):
        """A photo the blur metric rejects but OCR reads cleanly must not be
        discarded - its evidence counts (bottle-photo regression)."""
        texts = ["MRP. 7 (INCL. OF ALL", "L TAXES), USP.", "NET QUANTITY: 500ml"]

        def fake_ocr(path):
            return {
                "texts": texts,
                "confidences": [0.97] * len(texts),
                "bounding_boxes": [self._bbox(i * 60) for i in range(len(texts))],
                "avg_confidence": 0.97,
            }

        self.pipeline.assess_quality = lambda path: {
            "usable": False, "score": 55.0, "checks": {"blur": {"pass": False}}
        }
        self.pipeline.ocr = fake_ocr
        result = self.pipeline.run_multi(["fake_bottle.jpg"], image_names=["label.jpg"])
        assert result["coverage"]["surfaces_usable"] == 1
        img = result["images"][0]
        assert img["usability_basis"] == "ocr_evidence"
        assert img["usable"] is True and img["gate_usable"] is False
        # the readable evidence was actually used
        assert result["extracted_fields"]["mrp"]["value"] is not None

    def test_low_conf_ocr_does_not_rescue_surface(self):
        """Junk OCR on a gate-rejected surface must not make it usable."""
        texts = ["MRF", "sqme", "unr9adable", "fragrnents"]

        def fake_ocr(path):
            return {
                "texts": texts,
                "confidences": [0.55] * len(texts),
                "bounding_boxes": [self._bbox(i * 60) for i in range(len(texts))],
                "avg_confidence": 0.55,
            }

        self.pipeline.assess_quality = lambda path: {
            "usable": False, "score": 45.0, "checks": {}
        }
        self.pipeline.ocr = fake_ocr
        result = self.pipeline.run_multi(["fake_base.jpg"], image_names=["base.jpg"])
        assert result["coverage"]["surfaces_usable"] == 0
        assert result["decision"] == "MANUAL_REVIEW"

    def test_rejects_too_many_surfaces(self):
        with pytest.raises(ValueError):
            self.pipeline.run_multi(["a.jpg"] * 7)
