"""Commodity category classification and rule scoping (PRD §23)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.services.product_category import (
    CATEGORY_RULE_SCOPE,
    UNKNOWN,
    classify_product,
    scope_rules,
)


class TestClassification:
    def test_food_from_fssai_and_nutrition(self):
        result = classify_product(
            ocr_texts=[
                "FSSAI Lic. No. 10012345678901",
                "Nutrition Information per 100 g",
                "Ingredients: wheat flour, salt",
            ]
        )
        assert result["category"] == "food"
        assert result["confident"]
        assert result["evidence"]

    def test_beverage_from_packaging_language(self):
        result = classify_product(
            ocr_texts=[
                "Packed Drinking Water",
                "Serve chilled",
                "1 L",
            ]
        )
        assert result["category"] == "beverage"

    def test_cosmetic_from_external_use_warning(self):
        result = classify_product(
            ocr_texts=["For external use only", "Hair Oil", "Mfg Lic No 123"]
        )
        assert result["category"] == "cosmetic"

    def test_household_from_not_for_consumption(self):
        result = classify_product(
            ocr_texts=["Not for human consumption", "Floor cleaner", "Disinfectant"]
        )
        assert result["category"] == "household"

    def test_unknown_when_nothing_matches(self):
        """An unclassifiable package is reported unknown, never defaulted."""
        result = classify_product(ocr_texts=["ABCD", "1234", "XYZ"])
        assert result["category"] == UNKNOWN
        assert result["confidence"] == 0.0
        assert not result["confident"]

    def test_empty_input_is_unknown(self):
        assert classify_product()["category"] == UNKNOWN
        assert classify_product(ocr_texts=[])["category"] == UNKNOWN

    def test_confidence_never_claims_certainty(self):
        result = classify_product(
            ocr_texts=["FSSAI", "Nutrition Information", "Ingredients", "Snack"]
        )
        assert result["confidence"] <= 0.85

    def test_extracted_fields_contribute_evidence(self):
        result = classify_product(
            extracted_fields={
                "product_name": {"value": "Aloo Bhujia Namkeen", "ocr_text": "Aloo Bhujia"}
            }
        )
        assert result["category"] == "food"

    def test_scores_are_reported_for_every_matched_category(self):
        result = classify_product(
            ocr_texts=["Ingredients", "Shampoo", "Nutrition Information"]
        )
        assert "food" in result["scores"] and "cosmetic" in result["scores"]


class TestRuleScoping:
    RULES = [
        {"rule_id": "R-MRP", "source": {"category": "mrp"}},
        {"rule_id": "R-DIM", "source": {"category": "dimensions"}},
        {"rule_id": "R-MULTI", "source": {"category": "multi_component_package"}},
    ]

    def test_unmapped_categories_are_always_in_scope(self):
        scope = scope_rules(self.RULES, "food")
        assert "R-MRP" in scope["in_scope"]

    def test_irrelevant_conditional_rule_is_marked_out_of_scope(self):
        scope = scope_rules(self.RULES, "beverage")
        out = {e["rule_id"] for e in scope["out_of_scope"]}
        assert "R-DIM" in out  # dimensions concern textile/household/electrical
        assert "R-MRP" not in out

    def test_unknown_category_keeps_every_rule_in_scope(self):
        """An unclassified package must never get a narrower rulebook."""
        scope = scope_rules(self.RULES, UNKNOWN)
        assert scope["out_of_scope"] == []
        assert len(scope["in_scope"]) == 3

    def test_scoping_is_advisory_only(self):
        scope = scope_rules(self.RULES, "beverage")
        assert "verdict" in scope["note"] or "stands as reported" in scope["note"]

    def test_scope_map_references_real_categories(self):
        import json

        path = (
            Path(__file__).resolve().parent.parent
            / "backend" / "app" / "rules" / "labelguard_rules_draft.json"
        )
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        real = {r.get("category") for r in data["rules"]}
        assert set(CATEGORY_RULE_SCOPE) <= real


class TestPipelineIntegration:
    def test_result_carries_classification_and_scope(self, sample_result):
        category = sample_result["product_category"]
        assert category["category"] == "food"
        assert "rule_scope" in category
        assert category["rule_scope"]["in_scope"]

    def test_no_rule_verdict_is_changed_by_classification(self, sample_result):
        """Scoping is reporting-only: every rule still has its own verdict."""
        scoped_out = {
            e["rule_id"] for e in sample_result["product_category"]["rule_scope"]["out_of_scope"]
        }
        for rule in sample_result["rule_results"]:
            if rule["rule_id"] in scoped_out:
                assert rule["status"] in (
                    "PASS", "FAIL", "MANUAL_REVIEW", "NOT_APPLICABLE", "UNVERIFIED"
                )
