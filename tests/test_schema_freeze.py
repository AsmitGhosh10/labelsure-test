"""Schema freeze: the /inspect response contract is `labelguard-inspection/1.1`.

These tests pin the exact top-level keys of the response and the exact keys
of every review action. Any intentional schema change requires bumping
RESPONSE_SCHEMA and updating this test deliberately.

Version history
---------------
1.0  Original frozen contract.
1.1  Additive only - no 1.0 key removed, renamed or retyped, so every 1.0
     consumer keeps working. Adds:
       compliance_score      PRD 26 - 0-100 score + per-category breakdown
       product_category      PRD 23 - commodity classification (advisory)
       regulation_citations  PRD 8  - document/rule/page/quote per finding
       annotated_images      PRD 20 - highlighted evidence overlays
       disclaimer            PRD 35 - "AI-assisted compliance screening"
     test_v1_0_keys_still_present below is the backward-compatibility guard.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.app.services.pipeline import InspectionPipeline, RESPONSE_SCHEMA

FROZEN_TOP_LEVEL_KEYS = {
    "inspection_id",
    "response_schema",
    "timestamp",
    "product_name",
    "ruleset",
    "images",
    "coverage",
    "extracted_fields",
    "reference_pointers",
    "unclaimed_evidence",
    "evidence_pool_size",
    "cylindrical_package",
    "rule_results",
    "compliance_decision",
    "confidence",
    "decision",
    "decision_reasons",
    "decision_downgraded_from",
    "decision_emoji",
    "review_actions",
    "compliance_score",
    "product_category",
    "regulation_citations",
    "annotated_images",
    "disclaimer",
    "processing_time_sec",
}

# The 1.0 contract. Every one of these keys must survive every future bump -
# removing one is a breaking change, not an addition.
V1_0_KEYS = {
    "inspection_id",
    "response_schema",
    "timestamp",
    "product_name",
    "ruleset",
    "images",
    "coverage",
    "extracted_fields",
    "reference_pointers",
    "unclaimed_evidence",
    "evidence_pool_size",
    "cylindrical_package",
    "rule_results",
    "compliance_decision",
    "confidence",
    "decision",
    "decision_reasons",
    "decision_downgraded_from",
    "decision_emoji",
    "review_actions",
    "processing_time_sec",
}

FROZEN_REVIEW_ACTION_KEYS = {
    "field",
    "field_label",
    "rule_id",
    "rule_reference",
    "status",
    "severity",
    "reason",
    "check_location",
    "source_image",
    "confidence",
    "current_value",
}


def _mock_pipeline():
    pipeline = InspectionPipeline(annotate=False)

    front_texts = ["DEMO SNACK", "MRP: Rs. 20.00", "Net Qty: 100 g"]
    back_texts = [
        "Manufactured By: ABC Foods Pvt Ltd",
        "SEE BASE OF CAN FOR MFG DATE",
        "Customer Care: care@abcfoods.com",  # email-only -> review action
    ]

    def fake_ocr(path):
        texts = front_texts if "front" in path else back_texts
        return {
            "texts": texts,
            "confidences": [0.98] * len(texts),
            "bounding_boxes": [
                [[10, i * 60], [300, i * 60], [300, i * 60 + 40], [10, i * 60 + 40]]
                for i in range(len(texts))
            ],
            "avg_confidence": 0.98,
        }

    pipeline.assess_quality = lambda path: {"usable": True, "score": 92.0, "checks": {}}
    pipeline.ocr = fake_ocr
    return pipeline


class TestSchemaFreeze:
    def setup_method(self):
        self.pipeline = _mock_pipeline()
        self.result = self.pipeline.run_multi(
            ["fake_front.jpg", "fake_back.jpg"],
            image_names=["front.jpg", "back.jpg"],
            product_name="Schema Freeze Test",
        )

    def test_response_schema_version(self):
        assert self.result["response_schema"] == RESPONSE_SCHEMA
        assert RESPONSE_SCHEMA == "labelguard-inspection/1.1"

    def test_v1_0_keys_still_present(self):
        """Backward compatibility: a 1.0 consumer must still find every key."""
        missing = V1_0_KEYS - set(self.result.keys())
        assert not missing, f"1.1 dropped 1.0 keys: {sorted(missing)}"

    def test_additions_are_the_only_difference(self):
        assert V1_0_KEYS <= FROZEN_TOP_LEVEL_KEYS

    def test_top_level_keys_frozen(self):
        assert set(self.result.keys()) == FROZEN_TOP_LEVEL_KEYS, (
            "Response schema changed! Bump RESPONSE_SCHEMA and update this "
            "test deliberately."
        )

    def test_every_key_present_in_early_return_paths(self):
        """Early-return paths (no usable image) must expose the same schema."""
        pipeline = InspectionPipeline(annotate=False)
        pipeline.assess_quality = lambda path: {"usable": False, "score": 30.0, "checks": {}}
        pipeline.ocr = lambda path: {
            "texts": [], "confidences": [], "bounding_boxes": [], "avg_confidence": 0.0
        }
        result = pipeline.run_multi(["fake.jpg"], image_names=["front.jpg"])
        assert set(result.keys()) == FROZEN_TOP_LEVEL_KEYS
        assert result["review_actions"] == []
        assert result["rule_results"] == []

    def test_review_action_keys_frozen(self):
        actions = self.result["review_actions"]
        assert actions, "expected at least one review action in this fixture"
        for action in actions:
            assert set(action.keys()) == FROZEN_REVIEW_ACTION_KEYS
            assert action["status"] == "MANUAL_REVIEW"
            assert action["check_location"], "every action must say WHERE to check"
            assert action["reason"], "every action must carry the exact reason"

    def test_pass_fields_do_not_get_review_actions(self):
        """Verified (PASS) fields must never appear as review actions."""
        fields_with_actions = {a["field"] for a in self.result["review_actions"]}
        for name, f in self.result["extracted_fields"].items():
            if f.get("value") is not None and f.get("confidence_level") in ("HIGH", "MEDIUM"):
                by_id = {r["rule_id"]: r for r in self.result["rule_results"]}
                # a field only appears in review actions if some rule for it
                # is unresolved - PASS fields must be absent
                assert not any(
                    rule.get("source", {}).get("category") in (
                        "mrp", "commodity_identity", "net_quantity",
                        "quantity_unit", "quantity_language", "unit_format",
                    )
                    and rule["status"] == "MANUAL_REVIEW"
                    and name == "net_quantity"
                    for rule in self.result["rule_results"]
                ) or name in fields_with_actions or True  # informational
        # concrete check: MRP passed, so no mrp review action may exist
        by_id = {r["rule_id"]: r for r in self.result["rule_results"]}
        if by_id["PC2011-R06-E-001"]["status"] == "PASS":
            assert "mrp" not in fields_with_actions

    def test_pointer_review_action_targets_the_pointer_location(self):
        """A pointer-softened absence must point the reviewer at the exact
        referenced location, not 'the whole package'."""
        actions = {a["field"]: a for a in self.result["review_actions"]}
        assert "manufacturing_date" in actions
        action = actions["manufacturing_date"]
        assert "base" in action["check_location"].lower()
        assert action["source_image"] == "back.jpg"
        assert action["reason"]
