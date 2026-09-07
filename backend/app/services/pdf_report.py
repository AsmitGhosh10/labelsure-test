"""PDF inspection report (PRD §29).

Renders the same inspection result the markdown report describes, as a
paginated PDF an inspector can file: header, verdict and compliance score,
the annotated package images, the extracted declarations table, every finding
with its regulatory citation, and a manual-verification section carrying the
inspector's sign-off (or blank lines to sign, when no decision is recorded
yet).

ReportLab is an optional dependency. If it is not installed,
:func:`generate_pdf_report` raises :class:`PDFUnavailable` and callers fall
back to the markdown report rather than failing the inspection.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from backend.app.services import legal
from backend.app.services.report_generator import FIELD_LABELS

try:  # optional dependency
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image,
        KeepTogether,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without reportlab
    REPORTLAB_AVAILABLE = False


class PDFUnavailable(RuntimeError):
    """ReportLab is not installed, so no PDF can be produced."""


VERDICT_COLORS = {
    "COMPLIANT": "#1a7f37",
    "NON_COMPLIANT": "#c62828",
    "MANUAL_REVIEW": "#b26a00",
}

STATUS_COLORS = {
    "PASS": "#1a7f37",
    "FAIL": "#c62828",
    "MANUAL_REVIEW": "#b26a00",
    "NOT_APPLICABLE": "#777777",
    "UNVERIFIED": "#777777",
}

MAX_IMAGE_WIDTH_MM = 150
MAX_IMAGE_HEIGHT_MM = 110


def _escape(value: Any) -> str:
    """Escape text for ReportLab's mini-HTML paragraph markup."""
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "LGTitle", parent=base["Title"], fontSize=18, spaceAfter=2, alignment=TA_LEFT
        ),
        "subtitle": ParagraphStyle(
            "LGSubtitle", parent=base["Normal"], fontSize=9,
            textColor=colors.HexColor("#555555"), spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "LGH2", parent=base["Heading2"], fontSize=13, spaceBefore=12, spaceAfter=4,
            textColor=colors.HexColor("#1f2933"),
        ),
        "h3": ParagraphStyle(
            "LGH3", parent=base["Heading3"], fontSize=10.5, spaceBefore=8, spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "LGBody", parent=base["Normal"], fontSize=9, leading=12.5,
        ),
        "small": ParagraphStyle(
            "LGSmall", parent=base["Normal"], fontSize=7.6, leading=10,
            textColor=colors.HexColor("#444444"),
        ),
        "quote": ParagraphStyle(
            "LGQuote", parent=base["Normal"], fontSize=8, leading=11,
            leftIndent=10, textColor=colors.HexColor("#333333"),
            fontName="Helvetica-Oblique",
        ),
        "cell": ParagraphStyle(
            "LGCell", parent=base["Normal"], fontSize=8, leading=10.5,
        ),
        "cellhead": ParagraphStyle(
            "LGCellHead", parent=base["Normal"], fontSize=8, leading=10.5,
            textColor=colors.white, fontName="Helvetica-Bold",
        ),
    }


def _table(data: List[List[Any]], col_widths: List[float], header: bool = True) -> "Table":
    table = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474f")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f7f9")]),
        ]
    table.setStyle(TableStyle(style))
    return table


class _Numbered:
    """Draws the running footer: disclaimer + 'Page N of M'."""

    def __init__(self, inspection_id: str):
        self.inspection_id = inspection_id

    def __call__(self, canvas, doc):
        canvas.saveState()
        width, _ = A4
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(
            18 * mm, 12 * mm, legal.SHORT_DISCLAIMER
        )
        canvas.drawRightString(
            width - 18 * mm, 12 * mm, f"Page {canvas.getPageNumber()}"
        )
        canvas.drawString(18 * mm, 8 * mm, f"Inspection {self.inspection_id}")
        canvas.setStrokeColor(colors.HexColor("#dddddd"))
        canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
        canvas.restoreState()


def _fit_image(path: str) -> Optional["Image"]:
    try:
        reader = ImageReader(path)
        iw, ih = reader.getSize()
    except Exception:
        return None
    if not iw or not ih:
        return None
    max_w, max_h = MAX_IMAGE_WIDTH_MM * mm, MAX_IMAGE_HEIGHT_MM * mm
    scale = min(max_w / iw, max_h / ih, 1.0)
    try:
        return Image(path, width=iw * scale, height=ih * scale)
    except Exception:
        return None


def generate_pdf_report(
    result: Dict[str, Any],
    output_path: str,
    inspector_decision: Optional[Dict[str, Any]] = None,
    original_images: Optional[Dict[str, str]] = None,
) -> str:
    """Write the inspection PDF and return its path.

    ``inspector_decision`` is the recorded human sign-off (from
    :mod:`backend.app.services.hitl`); when absent, the manual-verification
    section is rendered as blank sign-off lines.
    ``original_images`` maps surface name -> file path, used when no annotated
    overlay exists for that surface.
    """
    if not REPORTLAB_AVAILABLE:
        raise PDFUnavailable(
            "ReportLab is not installed - run `pip install reportlab` to enable "
            "PDF reports (the markdown report is unaffected)"
        )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    st = _styles()
    inspection_id = str(result.get("inspection_id", "n/a"))

    doc = BaseDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title=f"Compliance Inspection Report {inspection_id}",
        author="AI Legal Metrology Compliance Scanner",
        subject=legal.SYSTEM_ROLE,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body"
    )
    doc.addPageTemplates(
        [PageTemplate(id="main", frames=[frame], onPage=_Numbered(inspection_id))]
    )

    story: List[Any] = []
    content_width = doc.width

    # ---------------- header ----------------
    story.append(Paragraph("Compliance Inspection Report", st["title"]))
    story.append(
        Paragraph(
            "Legal Metrology (Packaged Commodities) Rules, 2011 — "
            f"{_escape(legal.SYSTEM_ROLE)}",
            st["subtitle"],
        )
    )

    ruleset = result.get("ruleset", {}) or {}
    header_rows = [
        [
            Paragraph("Inspection ID", st["cell"]),
            Paragraph(_escape(inspection_id), st["cell"]),
            Paragraph("Date", st["cell"]),
            Paragraph(_escape(result.get("timestamp", "n/a")), st["cell"]),
        ],
        [
            Paragraph("Product", st["cell"]),
            Paragraph(_escape(result.get("product_name") or "Unknown"), st["cell"]),
            Paragraph("Ruleset", st["cell"]),
            Paragraph(
                _escape(f"{ruleset.get('id', '?')} v{ruleset.get('version', '?')}"),
                st["cell"],
            ),
        ],
    ]
    category = result.get("product_category") or {}
    if category:
        header_rows.append(
            [
                Paragraph("Commodity type", st["cell"]),
                Paragraph(_escape(category.get("label", "Unknown")), st["cell"]),
                Paragraph("Surfaces", st["cell"]),
                Paragraph(
                    _escape(
                        f"{(result.get('coverage') or {}).get('surfaces_usable', '?')}"
                        f"/{(result.get('coverage') or {}).get('surfaces_total', '?')} readable"
                    ),
                    st["cell"],
                ),
            ]
        )
    story.append(
        _table(
            header_rows,
            [content_width * 0.18, content_width * 0.34, content_width * 0.16, content_width * 0.32],
            header=False,
        )
    )
    story.append(Spacer(1, 8))

    # ---------------- legal disclaimer ----------------
    disclaimer_table = Table(
        [[Paragraph(f"<b>{_escape(legal.SYSTEM_ROLE.upper())}</b><br/>{_escape(legal.DISCLAIMER)}", st["small"])]],
        colWidths=[content_width],
    )
    disclaimer_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff8e1")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b26a00")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(disclaimer_table)

    if not ruleset.get("verified", False):
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                "<b>DRAFT RULESET</b> — rule definitions are pending verification "
                "against the official Legal Metrology documents. Do not use this "
                "report for enforcement decisions.",
                st["small"],
            )
        )

    # ---------------- verdict + score ----------------
    story.append(Paragraph("Overall Result", st["h2"]))
    decision = result.get("decision") or "MANUAL_REVIEW"
    confidence = result.get("confidence") or {}
    score_block = result.get("compliance_score") or {}
    score = score_block.get("score")

    verdict_cell = Paragraph(
        f"<font size=15 color='{VERDICT_COLORS.get(decision, '#555555')}'><b>"
        f"{_escape(decision.replace('_', ' '))}</b></font><br/>"
        f"<font size=8>Confidence {confidence.get('overall', 0) * 100:.0f}%</font>",
        st["body"],
    )
    score_cell = Paragraph(
        (
            f"<font size=15><b>{score:.0f}/100</b></font><br/>"
            f"<font size=8>Grade {_escape(score_block.get('grade', '—'))} — "
            f"{_escape(score_block.get('grade_meaning', ''))}</font>"
            if score is not None
            else "<font size=10>No compliance score — nothing assessable</font>"
        ),
        st["body"],
    )
    verdict_table = Table(
        [[verdict_cell, score_cell]], colWidths=[content_width * 0.42, content_width * 0.58]
    )
    verdict_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(VERDICT_COLORS.get(decision, "#555555"))),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(verdict_table)

    if result.get("decision_downgraded_from"):
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"Downgraded from {_escape(result['decision_downgraded_from'])} by the "
                "confidence guard — evidence was below the review threshold.",
                st["small"],
            )
        )

    reasons = result.get("decision_reasons") or []
    if reasons:
        story.append(Spacer(1, 6))
        for reason in reasons:
            story.append(Paragraph(f"• {_escape(reason)}", st["body"]))

    # score breakdown
    categories = [c for c in score_block.get("categories", []) if c.get("score") is not None]
    if categories:
        story.append(Paragraph("Compliance score breakdown", st["h3"]))
        rows = [
            [
                Paragraph("Category", st["cellhead"]),
                Paragraph("Score", st["cellhead"]),
                Paragraph("Pass", st["cellhead"]),
                Paragraph("Fail", st["cellhead"]),
                Paragraph("Review", st["cellhead"]),
                Paragraph("Not assessable", st["cellhead"]),
            ]
        ]
        for c in categories:
            rows.append(
                [
                    Paragraph(_escape(c["label"]), st["cell"]),
                    Paragraph(f"{c['score']:.0f}/100", st["cell"]),
                    Paragraph(str(c["pass"]), st["cell"]),
                    Paragraph(str(c["fail"]), st["cell"]),
                    Paragraph(str(c["manual_review"]), st["cell"]),
                    Paragraph(str(c["not_assessable"]), st["cell"]),
                ]
            )
        story.append(
            _table(
                rows,
                [
                    content_width * 0.34,
                    content_width * 0.14,
                    content_width * 0.1,
                    content_width * 0.1,
                    content_width * 0.13,
                    content_width * 0.19,
                ],
            )
        )
        story.append(Spacer(1, 3))
        story.append(Paragraph(_escape(score_block.get("basis", "")), st["small"]))

    # ---------------- images ----------------
    annotated = result.get("annotated_images") or []
    image_entries: List[Any] = []
    for entry in annotated:
        img = _fit_image(entry.get("path", ""))
        if img is None:
            continue
        caption = ", ".join(
            f"{b['label']} ({b['status'].replace('_', ' ').lower()})"
            for b in entry.get("boxes", [])[:8]
        )
        image_entries.append(
            KeepTogether(
                [
                    Paragraph(f"<b>{_escape(entry.get('name', 'surface'))}</b> — highlighted evidence", st["h3"]),
                    img,
                    Paragraph(_escape(caption), st["small"]),
                    Spacer(1, 6),
                ]
            )
        )
    if not image_entries and original_images:
        for name, path in list(original_images.items())[:4]:
            img = _fit_image(path)
            if img is None:
                continue
            image_entries.append(
                KeepTogether(
                    [
                        Paragraph(f"<b>{_escape(name)}</b> — captured surface", st["h3"]),
                        img,
                        Spacer(1, 6),
                    ]
                )
            )
    if image_entries:
        story.append(Paragraph("Package Images & Visual Evidence", st["h2"]))
        story.extend(image_entries)

    # ---------------- extracted declarations ----------------
    story.append(Paragraph("Extracted Declarations", st["h2"]))
    rows = [
        [
            Paragraph("Field", st["cellhead"]),
            Paragraph("Value read from the package", st["cellhead"]),
            Paragraph("Confidence", st["cellhead"]),
            Paragraph("Found on", st["cellhead"]),
        ]
    ]
    for name, f in (result.get("extracted_fields") or {}).items():
        value = f.get("value")
        conf = f.get("extraction_confidence", 0.0)
        rows.append(
            [
                Paragraph(_escape(FIELD_LABELS.get(name, name)), st["cell"]),
                Paragraph(
                    _escape(value) if value is not None else "<i>not found</i>", st["cell"]
                ),
                Paragraph(f"{conf:.0%}" if value is not None else "—", st["cell"]),
                Paragraph(_escape(f.get("source_image") or "—"), st["cell"]),
            ]
        )
    story.append(
        _table(
            rows,
            [content_width * 0.22, content_width * 0.44, content_width * 0.14, content_width * 0.20],
        )
    )

    # ---------------- findings ----------------
    story.append(PageBreak())
    story.append(Paragraph("Compliance Findings", st["h2"]))

    citations_by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for entry in result.get("regulation_citations") or []:
        if entry.get("rule_id"):
            citations_by_rule[entry["rule_id"]] = entry.get("citations") or []

    actionable = [
        r for r in (result.get("rule_results") or [])
        if r.get("status") in ("FAIL", "MANUAL_REVIEW")
    ]
    passed = [r for r in (result.get("rule_results") or []) if r.get("status") == "PASS"]
    out_of_scope = [
        r for r in (result.get("rule_results") or [])
        if r.get("status") not in ("FAIL", "MANUAL_REVIEW", "PASS")
    ]

    if actionable:
        story.append(
            Paragraph(
                f"{len(actionable)} finding(s) require attention. "
                f"{len(passed)} rule(s) passed and {len(out_of_scope)} could not be "
                "evaluated from photographs.",
                st["body"],
            )
        )
        for rule in actionable:
            status = rule.get("status", "")
            block = [
                Paragraph(
                    f"<font color='{STATUS_COLORS.get(status, '#333')}'><b>"
                    f"{_escape(status.replace('_', ' '))}</b></font> — "
                    f"{_escape(rule.get('rule_id', '?'))} "
                    f"({_escape(rule.get('severity', ''))})",
                    st["h3"],
                ),
                Paragraph(f"<b>Requirement:</b> {_escape(rule.get('requirement', ''))}", st["body"]),
                Paragraph(f"<b>Finding:</b> {_escape(rule.get('reason', ''))}", st["body"]),
            ]
            evidence = rule.get("evidence") or {}
            if isinstance(evidence, dict) and evidence.get("detected"):
                block.append(
                    Paragraph(
                        f"<b>Evidence:</b> read \"{_escape(evidence.get('ocr_text', ''))}\" → "
                        f"<b>{_escape(evidence.get('value'))}</b> "
                        f"(OCR {float(evidence.get('ocr_confidence', 0)):.0%}, "
                        f"extraction {float(evidence.get('extraction_confidence', 0)):.0%})",
                        st["body"],
                    )
                )
            elif isinstance(evidence, dict) and evidence.get("detected") is False:
                block.append(
                    Paragraph(
                        "<b>Evidence:</b> not detected on any captured surface", st["body"]
                    )
                )
            for citation in citations_by_rule.get(rule.get("rule_id", ""), [])[:1]:
                page = f", p.{citation['page']}" if citation.get("page") else ""
                block.append(
                    Paragraph(
                        f"<b>Source:</b> {_escape(citation.get('document', ''))} — "
                        f"{_escape(citation.get('rule', ''))}{_escape(page)}",
                        st["small"],
                    )
                )
                if citation.get("quote"):
                    quote = str(citation["quote"])
                    if len(quote) > 320:
                        quote = quote[:317] + "…"
                    block.append(Paragraph(f"“{_escape(quote)}”", st["quote"]))
            block.append(Spacer(1, 4))
            story.append(KeepTogether(block))
    else:
        story.append(
            Paragraph(
                "No failures or unresolved findings among the rules that could be "
                "evaluated from the captured imagery.",
                st["body"],
            )
        )

    if passed:
        story.append(Paragraph("Rules passed", st["h3"]))
        story.append(
            Paragraph(
                ", ".join(_escape(r.get("rule_id", "?")) for r in passed), st["small"]
            )
        )
    if out_of_scope:
        story.append(Paragraph("Not assessable from photographs", st["h3"]))
        story.append(
            Paragraph(
                ", ".join(_escape(r.get("rule_id", "?")) for r in out_of_scope),
                st["small"],
            )
        )

    # ---------------- targeted review actions ----------------
    actions = result.get("review_actions") or []
    if actions:
        story.append(Paragraph("Targeted Review Actions", st["h2"]))
        story.append(
            Paragraph(
                f"{len(actions)} unresolved item(s). Each names the exact surface "
                "to check — verified fields are not repeated.",
                st["body"],
            )
        )
        rows = [
            [
                Paragraph("Field", st["cellhead"]),
                Paragraph("Where to check", st["cellhead"]),
                Paragraph("Why", st["cellhead"]),
                Paragraph("Surface", st["cellhead"]),
            ]
        ]
        for a in actions:
            rows.append(
                [
                    Paragraph(_escape(a.get("field_label", a.get("field"))), st["cell"]),
                    Paragraph(_escape(a.get("check_location", "—")), st["cell"]),
                    Paragraph(_escape(a.get("reason", "")), st["cell"]),
                    Paragraph(_escape(a.get("source_image") or "—"), st["cell"]),
                ]
            )
        story.append(
            _table(
                rows,
                [content_width * 0.18, content_width * 0.24, content_width * 0.40, content_width * 0.18],
            )
        )

    # ---------------- manual verification / sign-off ----------------
    story.append(Paragraph("Manual Verification & Inspector Sign-off", st["h2"]))
    story.append(Paragraph(_escape(legal.MANUAL_VERIFICATION_NOTE), st["body"]))
    story.append(Spacer(1, 6))

    if inspector_decision:
        action = inspector_decision.get("action", "")
        verdict = inspector_decision.get("final_decision", "")
        rows = [
            [Paragraph("Inspector", st["cell"]),
             Paragraph(
                 _escape(
                     inspector_decision.get("inspector_name")
                     or inspector_decision.get("inspector_id", "")
                 ),
                 st["cell"],
             )],
            [Paragraph("Inspector ID", st["cell"]),
             Paragraph(_escape(inspector_decision.get("inspector_id", "")), st["cell"])],
            [Paragraph("Decision", st["cell"]),
             Paragraph(
                 f"<b>{_escape(action)}</b> — final verdict "
                 f"<font color='{VERDICT_COLORS.get(verdict, '#333')}'><b>"
                 f"{_escape(verdict.replace('_', ' '))}</b></font>",
                 st["cell"],
             )],
            [Paragraph("AI decision", st["cell"]),
             Paragraph(
                 _escape((inspector_decision.get("ai_decision") or "—").replace("_", " ")),
                 st["cell"],
             )],
            [Paragraph("Reason", st["cell"]),
             Paragraph(_escape(inspector_decision.get("reason", "")), st["cell"])],
            [Paragraph("Recorded at", st["cell"]),
             Paragraph(_escape(inspector_decision.get("timestamp", "")), st["cell"])],
        ]
        if inspector_decision.get("notes"):
            rows.append(
                [Paragraph("Notes", st["cell"]),
                 Paragraph(_escape(inspector_decision["notes"]), st["cell"])]
            )
        story.append(
            _table(rows, [content_width * 0.22, content_width * 0.78], header=False)
        )
    else:
        story.append(
            Paragraph(
                "<b>No inspector decision recorded.</b> This report describes an "
                "automated screening result only. It becomes an inspection record "
                "when an authorised inspector signs below.",
                st["body"],
            )
        )
        story.append(Spacer(1, 14))
        blank = [
            [Paragraph("Inspector name", st["cell"]), Paragraph("", st["cell"]),
             Paragraph("Inspector ID", st["cell"]), Paragraph("", st["cell"])],
            [Paragraph("Accept / Override", st["cell"]), Paragraph("", st["cell"]),
             Paragraph("Final verdict", st["cell"]), Paragraph("", st["cell"])],
            [Paragraph("Reason", st["cell"]), Paragraph("", st["cell"]),
             Paragraph("", st["cell"]), Paragraph("", st["cell"])],
            [Paragraph("Signature", st["cell"]), Paragraph("", st["cell"]),
             Paragraph("Date", st["cell"]), Paragraph("", st["cell"])],
        ]
        signoff = Table(
            blank,
            colWidths=[
                content_width * 0.18, content_width * 0.32,
                content_width * 0.16, content_width * 0.34,
            ],
            rowHeights=[18 * mm] * 4,
        )
        signoff.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f4f6")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f2f4f6")),
                    ("SPAN", (1, 2), (3, 2)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(signoff)

    # ---------------- provenance ----------------
    story.append(Paragraph("Provenance", st["h2"]))
    images = result.get("images") or []
    rows = [
        [
            Paragraph("Surface", st["cellhead"]),
            Paragraph("Quality", st["cellhead"]),
            Paragraph("Usable", st["cellhead"]),
            Paragraph("OCR lines", st["cellhead"]),
            Paragraph("OCR confidence", st["cellhead"]),
        ]
    ]
    for img in images:
        ocr_conf = img.get("ocr_avg_confidence")
        rows.append(
            [
                Paragraph(_escape(img.get("name", "?")), st["cell"]),
                Paragraph(f"{(img.get('quality') or {}).get('score', 0):.0f}/100", st["cell"]),
                Paragraph("yes" if img.get("usable") else "no", st["cell"]),
                Paragraph(str(img.get("num_lines", 0)), st["cell"]),
                Paragraph(f"{ocr_conf:.3f}" if ocr_conf is not None else "—", st["cell"]),
            ]
        )
    story.append(
        _table(
            rows,
            [
                content_width * 0.34, content_width * 0.14, content_width * 0.12,
                content_width * 0.18, content_width * 0.22,
            ],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            f"Ruleset {_escape(ruleset.get('id', '?'))} v{_escape(ruleset.get('version', '?'))} · "
            f"schema {_escape(result.get('response_schema', '?'))} · "
            f"processing time {_escape(result.get('processing_time_sec', '?'))}s · "
            f"evidence pool {_escape(result.get('evidence_pool_size', 0))} OCR elements",
            st["small"],
        )
    )

    doc.build(story)
    return output_path
