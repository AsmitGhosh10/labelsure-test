"""Frontend smoke tests.

Gradio itself is not exercised beyond "the app graph builds"; what matters
here is that every handler the UI wires up returns the shape its component
expects, including on the empty and error paths.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

pytest.importorskip("gradio", reason="gradio is required for the frontend")

from backend.app import database  # noqa: E402
from backend.app.services import hitl  # noqa: E402
import frontend.app as ui  # noqa: E402


@pytest.fixture
def stored(sample_result):
    database.save_inspection(sample_result)
    return sample_result


class TestAppGraph:
    def test_build_app_succeeds(self):
        assert ui.build_app() is not None


class TestOutputBuilders:
    def test_verdict_html_shows_the_verdict_and_score(self, sample_result):
        markup = ui.verdict_html(sample_result)
        assert sample_result["decision"].replace("_", " ") in markup
        assert "compliance score" in markup

    def test_verdict_html_handles_no_result(self):
        assert ui.verdict_html(None) == ""

    def test_verdict_html_escapes_untrusted_text(self):
        """OCR-derived text reaches the page - it must never be live markup."""
        hostile = {
            "decision": "MANUAL_REVIEW",
            "product_category": {
                "category": "food",
                "label": "<img src=x onerror=alert(1)>",
                "confidence": 0.5,
            },
        }
        markup = ui.verdict_html(hostile)
        assert "<img src=x" not in markup
        assert "&lt;img src=x" in markup

    def test_score_breakdown_renders_every_scored_category(self, sample_result):
        import html as html_module

        markup = ui.score_breakdown_html(sample_result)
        for category in sample_result["compliance_score"]["categories"]:
            if category["score"] is not None:
                # labels are HTML-escaped on the way in ("&" -> "&amp;")
                assert html_module.escape(category["label"]) in markup

    def test_score_breakdown_is_empty_without_a_score(self):
        assert ui.score_breakdown_html({"compliance_score": {"categories": []}}) == ""
        assert ui.score_breakdown_html(None) == ""

    def test_table_builders_match_their_headers(self, sample_result):
        for rows, headers in (
            (ui.fields_rows(sample_result), ui.FIELDS_HEADERS),
            (ui.findings_rows(sample_result), ui.FINDINGS_HEADERS),
            (ui.review_rows(sample_result), ui.REVIEW_HEADERS),
            (ui.citation_rows(sample_result), ui.CITATION_HEADERS),
        ):
            for row in rows:
                assert len(row) == len(headers)

    def test_citation_rows_carry_the_page_number(self, sample_result):
        rows = ui.citation_rows(sample_result)
        assert rows
        assert any(row[4] not in ("—", "None") for row in rows)

    def test_evidence_gallery_skips_missing_files(self):
        result = {"annotated_images": [{"path": "/no/such/file.png", "name": "front.jpg"}]}
        assert ui.evidence_gallery(result) == []


class TestInspectionHandler:
    def test_no_surfaces_returns_the_full_output_tuple(self):
        outputs = ui.run_inspection([], "")
        assert len(outputs) == 14
        assert "No surfaces added" in outputs[0]

    def test_pipeline_failure_is_reported_not_raised(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("OCR model unavailable")

        monkeypatch.setattr(ui.pipeline, "run_multi", boom)
        outputs = ui.run_inspection(["front.jpg"], "Test")
        assert "Inspection failed" in outputs[0]
        assert "OCR model unavailable" in outputs[0]

    def test_failure_tuple_matches_the_success_tuple_width(self, monkeypatch):
        """Both paths feed the same Gradio outputs list."""
        monkeypatch.setattr(
            ui.pipeline, "run_multi", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
        )
        assert len(ui.run_inspection(["f.jpg"], "")) == len(ui.run_inspection([], ""))


class TestSurfaceHandlers:
    def test_add_surface_requires_an_image(self):
        surfaces, gallery, message = ui.add_surface(None, [])
        assert surfaces == [] and "Capture or select" in message

    def test_add_surface_enforces_the_limit(self):
        full = ["s.jpg"] * ui.MAX_SURFACES
        surfaces, _, message = ui.add_surface("extra.jpg", full)
        assert len(surfaces) == ui.MAX_SURFACES
        assert "Maximum" in message

    def test_add_files_truncates_to_the_limit(self):
        surfaces, _, message = ui.add_files(["a.jpg"] * 10, [])
        assert len(surfaces) == ui.MAX_SURFACES
        assert "ignored" in message

    def test_clear_package(self):
        assert ui.clear_package()[0] == []


class TestSignOffHandler:
    def test_missing_inspection_id_is_reported(self):
        message, trail = ui.submit_decision("", "insp-1", "", "ACCEPT", "COMPLIANT", "why", "")
        assert "Run an inspection first" in message
        assert trail == ""

    def test_missing_reason_is_reported(self, stored):
        message, _ = ui.submit_decision(
            stored["inspection_id"], "insp-1", "", "ACCEPT", "COMPLIANT", "", ""
        )
        assert message.startswith("❌")

    def test_accept_records_and_renders_the_trail(self, stored):
        message, trail = ui.submit_decision(
            stored["inspection_id"], "ui-insp-1", "UI Inspector", "ACCEPT",
            "COMPLIANT", "Checked on the shelf", "note",
        )
        assert message.startswith("✅")
        assert "Audit trail" in trail
        assert "ui-insp-1" in trail

    def test_override_renders_both_decisions(self, stored):
        target = next(
            v for v in ("NON_COMPLIANT", "COMPLIANT", "MANUAL_REVIEW")
            if v != stored["decision"]
        )
        message, trail = ui.submit_decision(
            stored["inspection_id"], "ui-insp-2", "", "OVERRIDE", target,
            "The declaration is absent on the physical pack", "",
        )
        assert message.startswith("✅")
        assert "AI decision" in message
        assert target.replace("_", " ") in message

    def test_load_audit_for_an_unknown_id(self):
        assert "No inspection" in ui.load_audit("not-a-real-id")

    def test_load_audit_with_no_id(self):
        assert "Enter an inspection ID" in ui.load_audit("  ")

    def test_load_audit_renders_the_trail(self, stored):
        hitl.record_decision(
            inspection_id=stored["inspection_id"],
            inspector_id="ui-insp-3",
            action="ACCEPT",
            reason="Verified",
        )
        trail = ui.load_audit(stored["inspection_id"])
        assert "ui-insp-3" in trail
        assert "AI decision" in trail


class TestQueueSearchDashboard:
    def test_queue_rows_match_the_headers(self, stored):
        rows, summary = ui.load_queue("confidence")
        for row in rows:
            assert len(row) == len(ui.QUEUE_HEADERS)
        assert summary

    def test_search_rows_match_the_headers(self, stored):
        rows, summary = ui.search_inspections(
            "", "", "", "Any", "Any", "", "Any", "", "", "timestamp", True
        )
        for row in rows:
            assert len(row) == len(ui.SEARCH_HEADERS)
        assert "matching inspection" in summary

    def test_search_filters_actually_narrow(self, stored):
        all_rows, _ = ui.search_inspections(
            "", "", "", "Any", "Any", "", "Any", "", "", "timestamp", True
        )
        none_rows, _ = ui.search_inspections(
            "zzz-no-such-product", "", "", "Any", "Any", "", "Any", "", "",
            "timestamp", True,
        )
        assert len(none_rows) == 0 < len(all_rows)

    def test_dashboard_returns_five_panels(self, stored):
        panels = ui.load_dashboard()
        assert len(panels) == 5
        assert "Total inspections" in panels[0]
        assert isinstance(panels[4], list)

    def test_dashboard_carries_the_disclaimer(self, stored):
        assert "AI-ASSISTED COMPLIANCE SCREENING" in ui.load_dashboard()[0].upper()

    def test_bar_chart_handles_no_data(self):
        assert "No data yet" in ui._bar_chart("Empty", [])


class TestCardContrast:
    """A card that paints its own light background must also declare its own
    text colour.

    Gradio's dark theme sets a near-white default colour (and its own rule for
    `b`). Any card that painted `background:#fff` and left `color` to
    inheritance rendered white-on-white and was unreadable — that shipped once
    for the chart panels and the disclaimer heading. These tests fail if it
    comes back.
    """

    LIGHT_BACKGROUNDS = ("#fff'", "#fff;", "#fafafa", "#fff8e1")

    def _cards(self, markup):
        """Split markup into the opening tags that set a light background."""
        import re

        return [
            tag
            for tag in re.findall(r"<div[^>]*style=['\"][^'\"]*['\"][^>]*>", markup)
            if any(bg in tag for bg in self.LIGHT_BACKGROUNDS)
        ]

    def _assert_readable(self, markup, label):
        cards = self._cards(markup)
        assert cards, f"{label}: expected at least one light-background card"
        for tag in cards:
            assert "color:" in tag, (
                f"{label}: a light-background card does not set its own text "
                f"colour, so it inherits the dark theme's near-white: {tag[:160]}"
            )

    def test_disclaimer_banner_sets_its_colour(self):
        from backend.app.services import legal

        self._assert_readable(legal.disclaimer_html(), "disclaimer")

    def test_verdict_card_sets_its_colour(self, sample_result):
        self._assert_readable(ui.verdict_html(sample_result), "verdict")

    def test_score_breakdown_sets_its_colour(self, sample_result):
        self._assert_readable(ui.score_breakdown_html(sample_result), "score breakdown")

    def test_bar_chart_sets_its_colour_populated_and_empty(self):
        self._assert_readable(
            ui._bar_chart("Violations", [{"label": "R1", "count": 3}]), "bar chart"
        )
        self._assert_readable(ui._bar_chart("Violations", []), "empty bar chart")

    def test_stat_tile_sets_its_colour(self):
        self._assert_readable(ui._stat_tile("Total", 7), "stat tile")

    def test_dashboard_panels_set_their_colour(self, stored):
        tiles, violations, manufacturers, categories, _ = ui.load_dashboard()
        for markup, label in (
            (tiles, "dashboard tiles"),
            (violations, "violations chart"),
            (manufacturers, "manufacturers chart"),
            (categories, "categories chart"),
        ):
            self._assert_readable(markup, label)

    def _all_markup(self, sample_result):
        from backend.app.services import legal

        return (
            (legal.disclaimer_html(), "disclaimer"),
            (ui.verdict_html(sample_result), "verdict"),
            (ui.score_breakdown_html(sample_result), "score breakdown"),
            (ui._bar_chart("Violations", [{"label": "R1", "count": 3}]), "bar chart"),
            (ui._bar_chart("Violations", []), "empty bar chart"),
            (ui._stat_tile("Total", 7), "stat tile"),
        )

    def test_no_bare_bold_or_span(self, sample_result):
        """Gradio's `.prose` rules colour `b` and `span` *directly*, so a
        colour set on the card never reaches them by inheritance. Every such
        tag must carry its own colour."""
        for markup, label in self._all_markup(sample_result):
            for tag in ("<b>", "<span>"):
                assert tag not in markup, (
                    f"{label}: a bare {tag} takes the dark theme's near-white "
                    "on a light card - give it an explicit colour"
                )

    def test_every_span_declares_a_colour(self, sample_result):
        import re

        for markup, label in self._all_markup(sample_result):
            for tag in re.findall(r"<span[^>]*>", markup):
                assert "color:" in tag, f"{label}: span without a colour: {tag}"


class TestVerdictExplains:
    """The main screen must carry the *why*, not just the verdict.

    Reasons used to live only in the report tab, so a MANUAL_REVIEW caused by
    a broken OCR engine appeared on screen as nothing but
    "0/1 surfaces readable" — which reads as "your photo was bad".
    """

    def _engine_failure(self):
        from backend.app.services.pipeline import InspectionPipeline

        pipeline = InspectionPipeline(annotate=False)
        pipeline.assess_quality = lambda _p: {"usable": True, "score": 95.0, "checks": {}}

        def boom(_path):
            raise ImportError("No module named 'paddleocr'")

        pipeline.ocr = boom
        return pipeline.run_multi(["f.jpg"], image_names=["front.jpg"])

    def test_reasons_are_rendered_on_the_verdict_card(self, sample_result):
        markup = ui.verdict_html(sample_result)
        for reason in sample_result["decision_reasons"] or []:
            import html as html_module

            assert html_module.escape(reason) in markup

    def test_engine_failure_shows_a_system_fault_alert(self):
        markup = ui.verdict_html(self._engine_failure())
        assert "System fault" in markup
        assert "recapturing the package will not help" in markup.lower()
        assert "paddleocr" in markup.lower()

    def test_a_healthy_result_shows_no_fault_alert(self, sample_result):
        assert "System fault" not in ui.verdict_html(sample_result)

    def test_the_fault_alert_escapes_the_error_text(self):
        hostile = {
            "decision": "MANUAL_REVIEW",
            "images": [{"ocr_error": "<script>alert(1)</script>"}],
        }
        markup = ui.verdict_html(hostile)
        assert "<script>" not in markup
        assert "&lt;script&gt;" in markup
