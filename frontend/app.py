"""AI Legal Metrology Compliance Scanner — Gradio frontend.

Five workspaces:

1. **Inspect**   capture/upload up to 6 package surfaces, run the pipeline,
                 read the verdict, compliance score, findings, highlighted
                 visual evidence and the regulatory citation behind each one.
2. **Sign-off**  the inspector accepts or overrides the automated finding with
                 an ID and a reason; both decisions are stored together.
3. **Queue**     inspections awaiting a human decision, least confident first.
4. **Search**    the inspection repository by product, manufacturer, brand,
                 status, category, violation or date.
5. **Dashboard** supervisor statistics: totals, decision mix, common
                 violations, manufacturer trends, inspector activity.

Every verdict surface carries the same legal framing: this is AI-assisted
compliance screening, not automated legal enforcement.
"""

import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr

from backend.app import database
from backend.app.services import hitl, legal, pdf_report
from backend.app.services.pipeline import InspectionPipeline, MAX_SURFACES
from backend.app.services.report_generator import (
    FIELD_LABELS,
    ReportGenerator,
    RULE_STATUS_ICONS,
)

pipeline = InspectionPipeline(evidence_dir="reports/inspections/evidence")
report_gen = ReportGenerator(output_dir="reports/inspections")

VERDICT_COLORS = {
    "COMPLIANT": "#1a7f37",
    "NON_COMPLIANT": "#c62828",
    "MANUAL_REVIEW": "#b26a00",
}

SCORE_COLORS = [(90, "#1a7f37"), (75, "#5b8c00"), (60, "#b26a00"), (0, "#c62828")]

FIELDS_HEADERS = ["Field", "Value", "Level", "Confidence", "Found on"]
FINDINGS_HEADERS = ["", "Rule", "Status", "Severity", "Reason"]
REVIEW_HEADERS = ["⚠️ Field", "Check this surface", "Reason", "Source image", "Confidence"]
CITATION_HEADERS = ["Rule", "Status", "Document", "Reference", "Page", "Clause text"]
QUEUE_HEADERS = [
    "Priority", "Inspection ID", "Product", "Manufacturer", "Verdict",
    "Confidence", "Score", "When",
]
SEARCH_HEADERS = QUEUE_HEADERS + ["Reviewed", "Final verdict"]

SORT_CHOICES = [
    ("Confidence (lowest first)", "confidence"),
    ("Compliance score", "compliance_score"),
    ("Date", "timestamp"),
    ("Product", "product_name"),
    ("Manufacturer", "manufacturer"),
    ("Verdict", "decision"),
]


def _esc(value):
    return html.escape("" if value is None else str(value))


def _score_color(score):
    for floor, color in SCORE_COLORS:
        if score >= floor:
            return color
    return "#c62828"


# ----------------------------------------------------------------------
# Output builders
# ----------------------------------------------------------------------

def verdict_html(result):
    if not result:
        return ""
    decision = result.get("decision") or "—"
    emoji = result.get("decision_emoji", "🟡")
    conf = result.get("confidence")
    conf_str = f"{conf['overall'] * 100:.0f}%" if conf else "n/a"
    cov = result.get("coverage", {})
    cov_str = (
        f"{cov.get('surfaces_usable', '?')}/{cov.get('surfaces_total', '?')} "
        "surfaces readable"
    )
    color = VERDICT_COLORS.get(decision, "#555555")
    downgraded = ""
    if result.get("decision_downgraded_from"):
        downgraded = (
            f"<div style='color:#777; font-size:0.9em'>downgraded from "
            f"{_esc(result['decision_downgraded_from'].replace('_', ' '))} by the "
            "confidence guard</div>"
        )

    score_block = result.get("compliance_score") or {}
    score = score_block.get("score")
    score_html = ""
    if score is not None:
        score_html = (
            f"<div style='margin-top:10px; padding-top:10px; "
            f"border-top:1px solid #e0e0e0;'>"
            f"<span style='font-size:1.6em; font-weight:800; "
            f"color:{_score_color(score)}'>{score:.0f}"
            f"<span style='font-size:0.6em; color:inherit'>/100</span></span>"
            f"<span style='color:#555; margin-left:8px;'>compliance score · "
            f"grade {_esc(score_block.get('grade', '—'))}</span>"
            f"<div style='color:#777; font-size:0.85em'>"
            f"{_esc(score_block.get('grade_meaning', ''))}</div></div>"
        )

    category = result.get("product_category") or {}
    category_html = ""
    if category and category.get("category") != "unknown":
        category_html = (
            f"<div style='color:#555; font-size:0.9em; margin-top:4px'>"
            f"Commodity type: <b style='color:inherit'>{_esc(category.get('label'))}</b> "
            f"({category.get('confidence', 0):.0%} confidence)</div>"
        )

    # A broken OCR engine is a deployment fault, not a bad photograph. Saying
    # only "0/1 surfaces readable" sends the inspector off to recapture a
    # perfectly good pack, so the real cause gets its own alert.
    fault_html = ""
    faults = [i for i in (result.get("images") or []) if i.get("ocr_error")]
    if faults:
        fault_html = (
            "<div style='margin-top:10px; padding:8px 12px; border-radius:8px; "
            "background:#fdecea; border:1px solid #c62828; color:#7f1d1d; "
            "font-size:0.88em; text-align:left'>"
            "<b style='color:inherit'>⚠ System fault — not an image problem.</b> "
            f"The OCR engine failed on {len(faults)} surface(s); recapturing the "
            "package will not help. "
            f"<code style='color:inherit'>{_esc(faults[0]['ocr_error'])}</code>"
            "</div>"
        )

    # The reasons explain the verdict; burying them in the report tab means the
    # main screen states a conclusion without its justification.
    reasons = result.get("decision_reasons") or []
    reasons_html = ""
    if reasons:
        items = "".join(
            f"<li style='color:#444; margin:2px 0'>{_esc(r)}</li>" for r in reasons
        )
        reasons_html = (
            "<ul style='margin:10px 0 0; padding-left:20px; text-align:left; "
            f"font-size:0.88em; color:#444'>{items}</ul>"
        )

    return f"""
    <div style="border:2px solid {color}; border-radius:14px; padding:18px 22px;
                text-align:center; background:#fafafa; color:#222;">
      <div style="font-size:2.2em; line-height:1.2">{emoji}</div>
      <div style="font-size:1.7em; font-weight:800; color:{color};
                  letter-spacing:1px; margin-top:2px;">
        {_esc(decision.replace('_', ' '))}
      </div>
      <div style="margin-top:6px; color:#333; font-size:1.05em;">
        Confidence: <b style='color:inherit'>{conf_str}</b> &nbsp;·&nbsp; {cov_str}
      </div>
      {downgraded}
      {category_html}
      {score_html}
      {fault_html}
      {reasons_html}
    </div>
    """


def score_breakdown_html(result):
    """Per-category score bars (PRD §26)."""
    score_block = (result or {}).get("compliance_score") or {}
    categories = [c for c in score_block.get("categories", []) if c.get("score") is not None]
    if not categories:
        return ""
    rows = []
    for c in categories:
        color = _score_color(c["score"])
        rows.append(
            f"<div style='margin:6px 0'>"
            f"<div style='display:flex; justify-content:space-between; "
            f"font-size:0.88em; color:#333'>"
            f"<span style='color:#333'>{_esc(c['label'])}</span>"
            f"<span style='color:#333'><b style='color:inherit'>{c['score']:.0f}</b>"
            f"/100 &nbsp;"
            f"<span style='color:#777'>{c['pass']}✅ {c['fail']}❌ "
            f"{c['manual_review']}🟡 {c['not_assessable']}⚪</span></span></div>"
            f"<div style='background:#eceff1; border-radius:5px; height:9px; "
            f"margin-top:3px'>"
            f"<div style='width:{c['score']:.0f}%; background:{color}; height:9px; "
            f"border-radius:5px'></div></div></div>"
        )
    return (
        "<div style='border:1px solid #e0e0e0; border-radius:10px; padding:12px 16px; "
        "background:#fff; color:#333'>"
        "<div style='font-weight:700; margin-bottom:6px; color:#222'>"
        "Compliance score breakdown</div>"
        + "".join(rows)
        + f"<div style='font-size:0.78em; color:#777; margin-top:8px'>"
        f"{_esc(score_block.get('basis', ''))}</div></div>"
    )


def fields_rows(result):
    rows = []
    for name, f in (result.get("extracted_fields") or {}).items():
        value = f.get("value")
        conf = f.get("extraction_confidence", 0.0)
        rows.append([
            FIELD_LABELS.get(name, name),
            str(value) if value is not None else "— not found —",
            f.get("confidence_level", "MISSING"),
            f"{conf * 100:.0f}%" if value is not None else "—",
            f.get("source_image") or "—",
        ])
    return rows


def findings_rows(result):
    return [
        [
            RULE_STATUS_ICONS.get(r.get("status", ""), "?"),
            r.get("rule_id", "?"),
            r.get("status", "?"),
            r.get("severity", "?"),
            r.get("reason", ""),
        ]
        for r in result.get("rule_results") or []
    ]


def review_rows(result):
    """Targeted manual-review actions: exactly where to check, per field."""
    rows = []
    for a in result.get("review_actions") or []:
        conf = a.get("confidence")
        rows.append([
            f"⚠️ {a.get('field_label', a.get('field'))}",
            a.get("check_location", "—"),
            a.get("reason", ""),
            a.get("source_image") or "—",
            f"{conf:.0%}" if isinstance(conf, (int, float)) else "n/a",
        ])
    return rows


def citation_rows(result):
    """Document / rule / page / verbatim clause behind every actionable finding."""
    rows = []
    for entry in result.get("regulation_citations") or []:
        if not entry.get("citations"):
            rows.append([
                entry.get("rule_id", "?"), entry.get("status", "?"),
                "—", "—", "—", entry.get("note", "No regulation text retrieved"),
            ])
            continue
        for c in entry["citations"]:
            quote = str(c.get("quote", ""))
            rows.append([
                entry.get("rule_id", "?"),
                entry.get("status", "?"),
                c.get("document", "—"),
                c.get("rule", "—"),
                str(c.get("page", "—")),
                quote[:300] + ("…" if len(quote) > 300 else ""),
            ])
    return rows


def evidence_gallery(result):
    """Annotated surfaces with their highlighted declaration regions."""
    items = []
    for entry in result.get("annotated_images") or []:
        path = entry.get("path")
        if not path or not os.path.exists(path):
            continue
        caption = f"{entry.get('name')} — " + ", ".join(
            f"{b['label']} ({b['status'].replace('_', ' ').lower()})"
            for b in entry.get("boxes", [])[:6]
        )
        items.append((path, caption))
    return items


def empty_outputs():
    html_block = (
        "<div style='border:2px solid #999; border-radius:14px; padding:18px; "
        "text-align:center; color:#666; background:#fafafa;'>"
        "Capture or upload at least one package surface, then run the inspection."
        "</div>"
    )
    return html_block, [], [], [], None, "", None


# ----------------------------------------------------------------------
# Capture handlers
# ----------------------------------------------------------------------

def add_surface(capture_img, surfaces):
    if not capture_img:
        return surfaces, surfaces, "⚠️ Capture or select an image first."
    if len(surfaces) >= MAX_SURFACES:
        return surfaces, surfaces, f"⚠️ Maximum {MAX_SURFACES} surfaces per package."
    surfaces = surfaces + [capture_img]
    return surfaces, surfaces, f"✅ Added surface {len(surfaces)}/{MAX_SURFACES}."


def add_files(files, surfaces):
    if not files:
        return surfaces, surfaces, ""
    paths = [f if isinstance(f, str) else f.name for f in files]
    room = MAX_SURFACES - len(surfaces)
    if room <= 0:
        return surfaces, surfaces, f"⚠️ Maximum {MAX_SURFACES} surfaces per package."
    added = paths[:room]
    surfaces = surfaces + added
    msg = f"✅ Added {len(added)} photo(s) — {len(surfaces)}/{MAX_SURFACES} surfaces."
    if len(paths) > room:
        msg += f" ({len(paths) - room} ignored, max {MAX_SURFACES})"
    return surfaces, surfaces, msg


def clear_package():
    return [], [], "Cleared. Add surfaces for a new package."


# ----------------------------------------------------------------------
# Inspection
# ----------------------------------------------------------------------

def _failure(message):
    return (
        f"<div style='border:2px solid #c62828; border-radius:14px; padding:18px; "
        f"text-align:center; color:#c62828; background:#fff5f5;'>{_esc(message)}</div>",
        "", [], [], [], [], [], None, "", None, None, "", "", "",
    )


def run_inspection(surfaces, product_name):
    if not surfaces:
        return _failure("⚠️ No surfaces added. Capture or upload package photos first.")
    try:
        result = pipeline.run_multi(
            surfaces, product_name=(product_name or "").strip() or None
        )
    except Exception as e:
        return _failure(f"❌ Inspection failed: {e}")

    markdown = report_gen.generate(result)
    report_path = report_gen.save(result, markdown)
    database.save_inspection(result)  # best-effort history

    pdf_path = None
    pdf_note = ""
    try:
        pdf_path = pdf_report.generate_pdf_report(
            result, os.path.join("reports", "inspections", f"{result['inspection_id']}.pdf")
        )
    except pdf_report.PDFUnavailable:
        pdf_note = " · PDF unavailable (install `reportlab`)"
    except Exception as e:
        pdf_note = f" · PDF failed: {e}"

    inspection_id = result["inspection_id"]
    summary = (
        f"**Inspection ID:** `{inspection_id}` · "
        f"**Time:** {result.get('processing_time_sec', '?')}s · "
        f"**Review actions:** {len(result.get('review_actions') or [])} · "
        f"Report saved to `{report_path}`{pdf_note}"
    )
    signoff_status = (
        f"Ready to sign off inspection `{inspection_id}` "
        f"(automated verdict: **{result.get('decision', '?').replace('_', ' ')}**). "
        "Recording a decision never changes the AI result — both are stored together."
    )
    return (
        verdict_html(result),
        score_breakdown_html(result),
        fields_rows(result),
        findings_rows(result),
        review_rows(result),
        citation_rows(result),
        evidence_gallery(result),
        result,
        markdown,
        report_path,
        pdf_path,
        summary,
        inspection_id,
        signoff_status,
    )


# ----------------------------------------------------------------------
# Human-in-the-loop sign-off
# ----------------------------------------------------------------------

def submit_decision(inspection_id, inspector_id, inspector_name, action, verdict, reason, notes):
    inspection_id = (inspection_id or "").strip()
    if not inspection_id:
        return "⚠️ Run an inspection first, or paste an inspection ID.", ""
    try:
        out = hitl.record_decision(
            inspection_id=inspection_id,
            inspector_id=inspector_id or "",
            action=action,
            reason=reason or "",
            final_decision=verdict if action == "OVERRIDE" else None,
            inspector_name=(inspector_name or "").strip() or None,
            notes=(notes or "").strip() or None,
        )
    except hitl.DecisionError as e:
        return f"❌ {e}", ""
    except Exception as e:
        return f"❌ Could not record the decision: {e}", ""

    decision = out["decision"]
    verb = "accepted" if out["agreement"] else "overrode"
    message = (
        f"✅ **{_esc(decision['inspector_id'])}** {verb} the automated finding at "
        f"{decision['timestamp']}.  \n"
        f"AI decision: **{(decision.get('ai_decision') or '—').replace('_', ' ')}** · "
        f"Final verdict: **{decision['final_decision'].replace('_', ' ')}**"
    )
    if out["supersedes"]:
        message += f"  \n*Supersedes decision `{out['supersedes']}` (kept in the audit trail).*"

    trail = hitl.audit_trail(inspection_id)
    lines = ["### Audit trail", ""]
    lines.append(
        f"- 🤖 **AI decision** {trail['ai_decision']} "
        f"(confidence {trail['ai_confidence']:.0%}) at {trail['ai_timestamp']}"
        if trail.get("ai_confidence") is not None
        else f"- 🤖 **AI decision** {trail['ai_decision']} at {trail['ai_timestamp']}"
    )
    for d in trail["inspector_decisions"]:
        mark = "↩︎ superseded" if d["superseded"] else "**current**"
        lines.append(
            f"- 👤 **{d['action']}** by `{d['inspector_id']}` → "
            f"{d['final_decision'].replace('_', ' ')} at {d['timestamp']} "
            f"({mark})  \n  *{d['reason']}*"
        )
    return message, "\n".join(lines)


def load_audit(inspection_id):
    inspection_id = (inspection_id or "").strip()
    if not inspection_id:
        return "Enter an inspection ID."
    if not database.inspection_exists(inspection_id):
        return f"No inspection `{inspection_id}` in the repository."
    trail = hitl.audit_trail(inspection_id)
    lines = [f"### Audit trail — `{inspection_id}`", ""]
    lines.append(f"- 🤖 **AI decision** {trail['ai_decision']} at {trail['ai_timestamp']}")
    if not trail["inspector_decisions"]:
        lines.append("- 👤 *No inspector decision recorded yet.*")
    for d in trail["inspector_decisions"]:
        mark = "superseded" if d["superseded"] else "current"
        lines.append(
            f"- 👤 **{d['action']}** by `{d['inspector_id']}` → "
            f"{d['final_decision'].replace('_', ' ')} at {d['timestamp']} ({mark})  \n"
            f"  *{d['reason']}*"
        )
    if trail["audit_log"]:
        lines += ["", "### Logged actions", ""]
        for entry in trail["audit_log"][:20]:
            lines.append(
                f"- `{entry['timestamp']}` **{entry['action']}** by "
                f"`{entry['actor'] or 'system'}` ({entry['outcome']})"
            )
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Queue / search / dashboard
# ----------------------------------------------------------------------

def _summary_row(item, include_review=False):
    conf = item.get("confidence")
    score = item.get("compliance_score")
    row = [
        item.get("priority") or hitl.queue_bucket(conf),
        item.get("inspection_id", ""),
        item.get("product_name") or "—",
        item.get("manufacturer") or "—",
        (item.get("decision") or "—").replace("_", " "),
        f"{conf:.0%}" if isinstance(conf, (int, float)) else "—",
        f"{score:.0f}" if isinstance(score, (int, float)) else "—",
        item.get("timestamp") or "—",
    ]
    if include_review:
        row += [
            item.get("inspector_status") or "PENDING",
            (item.get("final_decision") or "—").replace("_", " "),
        ]
    return row


def load_queue(sort_by):
    items = hitl.pending_queue(sort_by=sort_by or "confidence")
    rows = [_summary_row(i) for i in items]
    if not rows:
        return rows, "No inspections are waiting for a decision."
    priority = sum(1 for i in items if hitl.queue_bucket(i.get("confidence")).startswith("🔴"))
    return rows, (
        f"**{len(rows)}** inspection(s) awaiting sign-off — "
        f"**{priority}** flagged priority review."
    )


def search_inspections(product, manufacturer, brand, status, category, violation,
                       reviewed, date_from, date_to, sort_by, descending):
    def clean(value):
        value = (value or "").strip()
        return value or None

    results = database.search_inspections(
        product=clean(product),
        manufacturer=clean(manufacturer),
        brand=clean(brand),
        status=None if status in (None, "Any") else status,
        category=None if category in (None, "Any") else category,
        violation_rule_id=clean(violation),
        inspector_status=None if reviewed in (None, "Any") else reviewed,
        date_from=clean(date_from),
        date_to=clean(date_to),
        sort_by=sort_by or "timestamp",
        descending=bool(descending),
        limit=200,
    )
    rows = [_summary_row(r, include_review=True) for r in results]
    return rows, f"**{len(rows)}** matching inspection(s)."


def _bar_chart(title, rows, value_key="count", label_key="label", suffix=""):
    """A dependency-free horizontal bar chart."""
    if not rows:
        return (
            f"<div style='border:1px solid #e0e0e0; border-radius:10px; padding:12px 16px;"
            f"background:#fff; color:#333'><b style='color:inherit'>{_esc(title)}</b>"
            f"<div style='color:#777; font-size:0.88em; margin-top:6px'>"
            f"No data yet.</div></div>"
        )
    peak = max(float(r[value_key]) for r in rows) or 1.0
    bars = []
    for r in rows:
        width = 100.0 * float(r[value_key]) / peak
        bars.append(
            f"<div style='margin:5px 0'>"
            f"<div style='display:flex; justify-content:space-between; "
            f"font-size:0.85em; color:#333'>"
            f"<span style='color:#333'>{_esc(r[label_key])}</span>"
            f"<span style='color:#333'><b style='color:inherit'>"
            f"{r[value_key]}{suffix}</b></span></div>"
            f"<div style='background:#eceff1; border-radius:5px; height:8px; margin-top:2px'>"
            f"<div style='width:{width:.1f}%; background:#37474f; height:8px; "
            f"border-radius:5px'></div></div></div>"
        )
    return (
        f"<div style='border:1px solid #e0e0e0; border-radius:10px; padding:12px 16px; "
        f"background:#fff; color:#333'><b style='color:inherit'>{_esc(title)}</b>{''.join(bars)}</div>"
    )


def _stat_tile(label, value, color="#37474f", note=""):
    return (
        f"<div style='flex:1 1 150px; border:1px solid #e0e0e0; border-radius:10px; "
        f"padding:12px 14px; background:#fff; color:#333; text-align:center'>"
        f"<div style='font-size:1.7em; font-weight:800; color:{color}'>{_esc(value)}</div>"
        f"<div style='color:#555; font-size:0.85em'>{_esc(label)}</div>"
        f"<div style='color:#999; font-size:0.75em'>{_esc(note)}</div></div>"
    )


def load_dashboard():
    stats = database.inspection_stats()
    if not stats["total_inspections"]:
        return (
            "<div style='color:#666'>No inspections recorded yet — run one from the "
            "Inspect tab.</div>",
            "", "", "", [],
        )

    avg_score = stats["average_compliance_score"]
    tiles = "".join([
        _stat_tile("Total inspections", stats["total_inspections"]),
        _stat_tile("Compliant", stats["compliant"], "#1a7f37",
                   f"{stats['compliance_rate']}% of all"),
        _stat_tile("Non-compliant", stats["non_compliant"], "#c62828"),
        _stat_tile("Manual review", stats["manual_review"], "#b26a00"),
        _stat_tile("Avg. confidence", f"{stats['average_confidence']:.0%}"),
        _stat_tile("Avg. score", f"{avg_score:.0f}" if avg_score is not None else "—"),
        _stat_tile("Human reviewed", stats["human_reviewed"], "#37474f",
                   f"{stats['overrides']} overrides ({stats['override_rate']}%)"),
    ])
    tiles_html = (
        f"<div style='display:flex; flex-wrap:wrap; gap:10px'>{tiles}</div>"
        f"<div style='margin-top:10px'>{legal.disclaimer_html()}</div>"
    )

    violations_html = _bar_chart(
        "Most common violated rules",
        [{"label": v["rule_id"], "count": v["count"]} for v in stats["common_violations"]],
    )
    manufacturers_html = _bar_chart(
        "Manufacturers by inspection volume",
        [
            {
                "label": f"{m['manufacturer'][:40]} ({m['non_compliance_rate']}% non-compliant)",
                "count": m["inspections"],
            }
            for m in stats["manufacturer_trends"]
        ],
    )
    categories_html = _bar_chart(
        "Product categories",
        [{"label": k, "count": v} for k, v in sorted(
            stats["by_category"].items(), key=lambda kv: -kv[1]
        )],
    )
    trend_rows = [
        [d["date"], d["total"], d["COMPLIANT"], d["NON_COMPLIANT"], d["MANUAL_REVIEW"]]
        for d in stats["daily_trend"][-30:]
    ]
    return tiles_html, violations_html, manufacturers_html, categories_html, trend_rows


# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------

def _theme():
    """Gradio 5 takes the theme on Blocks, Gradio 6 on launch(). Resolved once
    here so build_app() works on both."""
    try:
        return gr.themes.Soft()
    except Exception:
        return None


def build_app():
    kwargs = {}
    if int(getattr(gr, "__version__", "6").split(".")[0]) < 6:
        kwargs["theme"] = _theme()

    with gr.Blocks(title="AI Legal Metrology Compliance Scanner", **kwargs) as app:
        gr.Markdown(
            "# 📦 AI Legal Metrology Compliance Scanner\n"
            "Capture up to **6 surfaces** of one package (front · back · sides · "
            "top · bottom) — or a single flat label image — and get a "
            "rule-based compliance verdict with evidence."
        )
        gr.HTML(legal.disclaimer_html())

        current_id = gr.State("")

        with gr.Tabs():
            # ---------------------------------------------------- Inspect
            with gr.Tab("🔍 Inspect"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 1. Add package surfaces")
                        capture = gr.Image(
                            sources=["webcam", "upload"],
                            type="filepath",
                            label="Camera / pick one photo",
                            height=260,
                        )
                        add_btn = gr.Button("➕ Add this surface", variant="secondary")
                        files = gr.File(
                            file_count="multiple",
                            label="…or upload multiple photos at once",
                            file_types=["image"],
                        )
                        clear_btn = gr.Button("🗑 Clear package", variant="stop", size="sm")
                        status = gr.Markdown("")
                        gallery = gr.Gallery(
                            label="Surfaces in this package",
                            columns=3,
                            height=200,
                            preview=True,
                        )
                        surfaces_state = gr.State([])

                    with gr.Column(scale=1):
                        gr.Markdown("### 2. Run inspection")
                        product_name = gr.Textbox(
                            label="Product name (optional)",
                            placeholder="e.g. Haldiram Bhujia 500g",
                        )
                        run_btn = gr.Button("🔍 Run Inspection", variant="primary", size="lg")
                        verdict = gr.HTML(empty_outputs()[0])
                        score_html = gr.HTML("")
                        summary = gr.Markdown("")

                gr.Markdown("### 3. Results")
                with gr.Tabs():
                    with gr.Tab("Review Actions"):
                        gr.Markdown(
                            "*Unresolved fields with the exact surface to check — "
                            "no need to inspect the whole package.*"
                        )
                        reviews = gr.Dataframe(
                            headers=REVIEW_HEADERS,
                            datatype=["str"] * 5,
                            wrap=True,
                            interactive=False,
                            label="Targeted manual review",
                        )
                    with gr.Tab("Visual Evidence"):
                        gr.Markdown(
                            "*Every extracted declaration highlighted on the surface "
                            "it was read from — green passed, amber unresolved, "
                            "red failed.*"
                        )
                        evidence = gr.Gallery(
                            label="Annotated surfaces",
                            columns=2,
                            height=420,
                            preview=True,
                        )
                    with gr.Tab("Findings"):
                        findings = gr.Dataframe(
                            headers=FINDINGS_HEADERS,
                            datatype=["str"] * 5,
                            wrap=True,
                            interactive=False,
                            label="Rule evaluation results",
                        )
                    with gr.Tab("Regulatory Sources"):
                        gr.Markdown(
                            "*Document, rule, page and the verbatim clause behind "
                            "every finding that needs action.*"
                        )
                        citations = gr.Dataframe(
                            headers=CITATION_HEADERS,
                            datatype=["str"] * 6,
                            wrap=True,
                            interactive=False,
                            label="Retrieved regulation text",
                        )
                    with gr.Tab("Extracted Fields"):
                        fields = gr.Dataframe(
                            headers=FIELDS_HEADERS,
                            datatype=["str"] * 5,
                            wrap=True,
                            interactive=False,
                            label="Fields detected across all surfaces",
                        )
                    with gr.Tab("Report"):
                        with gr.Row():
                            download = gr.DownloadButton(
                                label="⬇ Download report (.md)", value=None
                            )
                            download_pdf = gr.DownloadButton(
                                label="⬇ Download report (.pdf)", value=None
                            )
                        report_md = gr.Markdown("")
                    with gr.Tab("Raw JSON"):
                        raw = gr.JSON(label="Full pipeline response")

            # ---------------------------------------------------- Sign-off
            with gr.Tab("✍️ Inspector Sign-off"):
                gr.Markdown(
                    "### Accept or override the automated finding\n"
                    "The AI decision is never modified. Your decision is stored "
                    "beside it with your ID, the reason and a timestamp, and the "
                    "pair forms the audit trail."
                )
                signoff_status = gr.Markdown("Run an inspection, or paste an inspection ID.")
                with gr.Row():
                    signoff_id = gr.Textbox(label="Inspection ID", placeholder="uuid")
                    inspector_id = gr.Textbox(
                        label="Inspector ID *", placeholder="e.g. LM-INSP-0142"
                    )
                    inspector_name = gr.Textbox(
                        label="Inspector name", placeholder="optional"
                    )
                with gr.Row():
                    action = gr.Radio(
                        ["ACCEPT", "OVERRIDE"],
                        value="ACCEPT",
                        label="Decision",
                        info="ACCEPT adopts the AI verdict; OVERRIDE replaces it.",
                    )
                    override_verdict = gr.Radio(
                        ["COMPLIANT", "NON_COMPLIANT", "MANUAL_REVIEW"],
                        value="MANUAL_REVIEW",
                        label="Final verdict (OVERRIDE only)",
                    )
                reason = gr.Textbox(
                    label="Reason *",
                    lines=2,
                    placeholder="What did you verify, and what did you find? "
                    "An override needs a substantive explanation.",
                )
                notes = gr.Textbox(label="Notes", lines=2, placeholder="optional")
                with gr.Row():
                    submit_btn = gr.Button("✅ Record decision", variant="primary")
                    audit_btn = gr.Button("📜 Load audit trail", variant="secondary")
                decision_result = gr.Markdown("")
                audit_view = gr.Markdown("")

            # ---------------------------------------------------- Queue
            with gr.Tab("📋 Review Queue"):
                gr.Markdown(
                    "### Inspections awaiting a human decision\n"
                    "Sorted least-confident first so the weakest evidence is "
                    "reviewed before the strongest."
                )
                with gr.Row():
                    queue_sort = gr.Dropdown(
                        choices=SORT_CHOICES, value="confidence", label="Sort by"
                    )
                    queue_btn = gr.Button("🔄 Refresh queue", variant="primary")
                queue_summary = gr.Markdown("")
                queue_table = gr.Dataframe(
                    headers=QUEUE_HEADERS,
                    datatype=["str"] * len(QUEUE_HEADERS),
                    wrap=True,
                    interactive=False,
                    label="Pending inspections",
                )

            # ---------------------------------------------------- Search
            with gr.Tab("🔎 Search"):
                gr.Markdown("### Search the inspection repository")
                with gr.Row():
                    s_product = gr.Textbox(label="Product")
                    s_manufacturer = gr.Textbox(label="Manufacturer")
                    s_brand = gr.Textbox(label="Brand")
                with gr.Row():
                    s_status = gr.Dropdown(
                        ["Any", "COMPLIANT", "NON_COMPLIANT", "MANUAL_REVIEW"],
                        value="Any",
                        label="Verdict",
                    )
                    s_category = gr.Dropdown(
                        ["Any", "food", "beverage", "cosmetic", "drug", "household",
                         "textile", "electrical", "unknown"],
                        value="Any",
                        label="Commodity type",
                    )
                    s_violation = gr.Textbox(
                        label="Violated rule id", placeholder="e.g. PC2011-R06-E-001"
                    )
                    s_reviewed = gr.Dropdown(
                        ["Any", "PENDING", "ACCEPT", "OVERRIDE"],
                        value="Any",
                        label="Review state",
                    )
                with gr.Row():
                    s_from = gr.Textbox(label="Date from", placeholder="YYYY-MM-DD")
                    s_to = gr.Textbox(label="Date to", placeholder="YYYY-MM-DD")
                    s_sort = gr.Dropdown(
                        choices=SORT_CHOICES, value="timestamp", label="Sort by"
                    )
                    s_desc = gr.Checkbox(value=True, label="Descending")
                search_btn = gr.Button("🔎 Search", variant="primary")
                search_summary = gr.Markdown("")
                search_table = gr.Dataframe(
                    headers=SEARCH_HEADERS,
                    datatype=["str"] * len(SEARCH_HEADERS),
                    wrap=True,
                    interactive=False,
                    label="Results",
                )

            # ---------------------------------------------------- Dashboard
            with gr.Tab("📊 Dashboard"):
                gr.Markdown("### Supervisor overview")
                dash_btn = gr.Button("🔄 Refresh statistics", variant="primary")
                dash_tiles = gr.HTML("")
                with gr.Row():
                    dash_violations = gr.HTML("")
                    dash_manufacturers = gr.HTML("")
                dash_categories = gr.HTML("")
                gr.Markdown("#### Daily trend")
                dash_trend = gr.Dataframe(
                    headers=["Date", "Total", "Compliant", "Non-compliant", "Manual review"],
                    datatype=["str", "number", "number", "number", "number"],
                    interactive=False,
                    label="Inspections per day",
                )

        # ------------------------------------------------------------------
        # wiring
        # ------------------------------------------------------------------
        add_btn.click(
            add_surface,
            inputs=[capture, surfaces_state],
            outputs=[surfaces_state, gallery, status],
        )
        files.change(
            add_files,
            inputs=[files, surfaces_state],
            outputs=[surfaces_state, gallery, status],
        )
        clear_btn.click(clear_package, outputs=[surfaces_state, gallery, status])
        run_btn.click(
            run_inspection,
            inputs=[surfaces_state, product_name],
            outputs=[
                verdict, score_html, fields, findings, reviews, citations, evidence,
                raw, report_md, download, download_pdf, summary, signoff_id,
                signoff_status,
            ],
        )
        submit_btn.click(
            submit_decision,
            inputs=[
                signoff_id, inspector_id, inspector_name, action, override_verdict,
                reason, notes,
            ],
            outputs=[decision_result, audit_view],
        )
        audit_btn.click(load_audit, inputs=[signoff_id], outputs=[audit_view])
        queue_btn.click(load_queue, inputs=[queue_sort], outputs=[queue_table, queue_summary])
        search_btn.click(
            search_inspections,
            inputs=[
                s_product, s_manufacturer, s_brand, s_status, s_category, s_violation,
                s_reviewed, s_from, s_to, s_sort, s_desc,
            ],
            outputs=[search_table, search_summary],
        )
        dash_btn.click(
            load_dashboard,
            outputs=[
                dash_tiles, dash_violations, dash_manufacturers, dash_categories,
                dash_trend,
            ],
        )

    return app


if __name__ == "__main__":
    demo = build_app()
    launch_kwargs = {"server_name": "127.0.0.1", "server_port": 7860, "show_error": True}
    if int(getattr(gr, "__version__", "6").split(".")[0]) >= 6:
        launch_kwargs["theme"] = _theme()
    demo.launch(**launch_kwargs)
