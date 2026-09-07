import os
from typing import Dict, Any, List, Optional

from backend.app.services import legal

STATUS_ICONS = {
    "PASS": "✅ PASS",
    "FAIL": "❌ FAIL",
    "MANUAL_REVIEW": "🟡 MANUAL REVIEW",
    "NOT_APPLICABLE": "⚪ NOT APPLICABLE",
    "UNVERIFIED": "❓ UNVERIFIED",
}

RULE_STATUS_ICONS = {
    "PASS": "✅",
    "FAIL": "❌",
    "MANUAL_REVIEW": "🟡",
    "NOT_APPLICABLE": "⚪",
    "UNVERIFIED": "❓",
}

FIELD_LABELS = {
    "mrp": "MRP",
    "product_name": "Product Name",
    "brand": "Brand",
    "net_quantity": "Net Quantity",
    "manufacturer": "Manufacturer",
    "packer": "Packer",
    "importer": "Importer",
    "manufacturing_date": "Manufacturing Date",
    "packing_date": "Packing Date",
    "best_before": "Best Before",
    "batch_number": "Batch Number",
    "consumer_care": "Consumer Care",
    "country_of_origin": "Country of Origin",
}


class ReportGenerator:
    """Render a multi-image inspection result as a human-readable markdown
    report. Every finding carries its rule, reason and evidence trail."""

    def __init__(self, output_dir: str = "reports/inspections"):
        self.output_dir = output_dir

    # ------------------------------------------------------------------

    def generate(
        self,
        result: Dict[str, Any],
        inspector_decision: Optional[Dict[str, Any]] = None,
    ) -> str:
        lines: List[str] = []
        lines.append("# Compliance Inspection Report")
        lines.append("")
        lines.append(legal.disclaimer_block())
        lines.append("")
        lines.append(
            f"**Inspection ID:** `{result.get('inspection_id', 'n/a')}`  "
        )
        lines.append(f"**Date:** {result.get('timestamp', 'n/a')}  ")
        product = result.get("product_name") or "Unknown"
        lines.append(f"**Product:** {product}  ")
        category = result.get("product_category") or {}
        if category:
            lines.append(
                f"**Commodity type:** {category.get('label', 'Unknown')} "
                f"(confidence {category.get('confidence', 0):.0%})  "
            )
        ruleset = result.get("ruleset", {})
        lines.append(f"**Ruleset:** {ruleset.get('id', '?')} v{ruleset.get('version', '?')}")
        if not ruleset.get("verified", False):
            lines.append("")
            lines.append(
                "> ⚠️ **DRAFT RULESET** — rule definitions are pending verification "
                "against the official Legal Metrology documents. Do not use this "
                "report for enforcement decisions."
            )
        lines.append("")

        # Overall result
        lines.append("## Overall Result")
        lines.append("")
        decision = result.get("decision", "MANUAL_REVIEW")
        emoji = result.get("decision_emoji", "🟡")
        conf = result.get("confidence")
        conf_str = f"{conf['overall']:.0%}" if conf else "n/a"
        lines.append(f"### {emoji} {decision.replace('_', ' ')}")
        lines.append(f"**Confidence:** {conf_str}")
        coverage = result.get("coverage", {})
        lines.append(
            f"**Coverage:** {coverage.get('surfaces_usable', '?')}/"
            f"{coverage.get('surfaces_total', '?')} captured surfaces readable"
        )
        if result.get("decision_downgraded_from"):
            lines.append(
                f"**Note:** downgraded from {result['decision_downgraded_from']} "
                "by the confidence guard (evidence below review threshold)."
            )
        lines.append("")
        reasons = result.get("decision_reasons") or []
        if reasons:
            lines.append("**Reasons:**")
            lines.append("")
            for reason in reasons:
                lines.append(f"- {reason}")
            lines.append("")

        # Compliance score (PRD 26)
        score_block = result.get("compliance_score") or {}
        if score_block.get("score") is not None:
            lines.append("## Compliance Score")
            lines.append("")
            lines.append(
                f"### {score_block['score']:.0f} / 100 "
                f"(grade {score_block.get('grade', '-')})"
            )
            lines.append("")
            lines.append(score_block.get("grade_meaning", ""))
            lines.append("")
            lines.append("| Category | Score | Pass | Fail | Review | Not assessable |")
            lines.append("|---|---|---|---|---|---|")
            for c in score_block.get("categories", []):
                score_cell = (
                    f"{c['score']:.0f}/100" if c.get("score") is not None else "-"
                )
                lines.append(
                    f"| {c['label']} | {score_cell} | {c['pass']} | {c['fail']} "
                    f"| {c['manual_review']} | {c['not_assessable']} |"
                )
            lines.append("")
            lines.append(f"*{score_block.get('basis', '')}*")
            lines.append("")
            lines.append(
                "> This score is a screening aid. It does not replace statutory "
                "inspection and carries no legal finding."
            )
            lines.append("")

        # Extracted information
        lines.append("## Extracted Information")
        lines.append("")
        lines.append("| Field | Value | Confidence | Level | Found on |")
        lines.append("|---|---|---|---|---|")
        fields = result.get("extracted_fields", {})
        for name, f in fields.items():
            label = FIELD_LABELS.get(name, name)
            value = f.get("value")
            value_str = str(value) if value is not None else "— not found —"
            level = f.get("confidence_level", "MISSING")
            conf_val = f.get("extraction_confidence", 0.0)
            conf_cell = f"{conf_val:.0%}" if value is not None else "—"
            source = f.get("source_image") or "—"
            lines.append(
                f"| {label} | {value_str} | {conf_cell} | {level} | {source} |"
            )
        lines.append("")

        # Compliance findings
        lines.append("## Compliance Findings")
        lines.append("")
        rule_results = result.get("rule_results", [])
        for r in rule_results:
            icon = RULE_STATUS_ICONS.get(r.get("status", ""), "?")
            lines.append(f"### {icon} {r.get('rule_id', '?')} — {r.get('status', '?')}")
            lines.append("")
            lines.append(f"**Requirement:** {r.get('requirement', '')}  ")
            lines.append(f"**Severity:** {r.get('severity', '')}  ")
            reason = r.get("reason", "")
            lines.append(f"**Reason:** {reason}")
            source = r.get("source", {})
            if source:
                src_str = source.get("document", "?")
                if source.get("rule"):
                    src_str += f", {source['rule']}"
                if source.get("page"):
                    src_str += f" (p.{source['page']})"
                if source.get("status"):
                    src_str += f" [{source['status']}]"
                lines.append(f"**Source:** {src_str}  ")
                if source.get("evidence_text"):
                    quote = str(source["evidence_text"]).strip()
                    if len(quote) > 160:
                        quote = quote[:157] + "..."
                    lines.append(f"> *\"{quote}\"*")
                    lines.append("")
            evidence = r.get("evidence", {})
            ev_parts: List[str] = []
            if isinstance(evidence, dict) and evidence.get("detected"):
                ev_parts.append(f"value `{evidence.get('value')}`")
                if evidence.get("ocr_text"):
                    ev_parts.append(f"OCR text: \"{evidence.get('ocr_text')}\"")
                ev_parts.append(
                    f"OCR conf {evidence.get('ocr_confidence', 0):.2f}, "
                    f"extraction conf {evidence.get('extraction_confidence', 0):.2f}"
                )
                if evidence.get("bbox"):
                    ev_parts.append("bounding box captured")
            elif isinstance(evidence, dict) and evidence.get("detected") is False:
                ev_parts.append("not detected on any captured surface")
                rp = evidence.get("reference_pointer")
                if rp:
                    ev_parts.append(
                        f"label pointer: \"{str(rp.get('text', ''))[:60]}\" "
                        f"(see {rp.get('location', '?')} of package)"
                    )
            elif isinstance(evidence, dict) and evidence:
                for k, v in evidence.items():
                    if isinstance(v, dict) and v.get("detected"):
                        ev_parts.append(f"{k}: `{v.get('value')}`")
            if ev_parts:
                lines.append(f"**Evidence:** {'; '.join(ev_parts)}")
            lines.append("")

        # Targeted review actions - tell the reviewer exactly where to look
        actions = result.get("review_actions") or []
        if actions:
            lines.append("## Targeted Review Actions")
            lines.append("")
            lines.append(
                f"{len(actions)} unresolved item(s) - each points to the exact "
                "surface to check. Verified (PASS) fields are not repeated here."
            )
            lines.append("")
            for a in actions:
                lines.append(f"### ⚠️ {a.get('field_label', a.get('field'))}")
                lines.append("")
                conf = a.get("confidence")
                conf_str = f"{conf:.0%}" if isinstance(conf, (int, float)) else "n/a"
                lines.append(f"**Check:** {a.get('check_location', '—')}  ")
                if a.get("source_image"):
                    lines.append(f"**Surface:** {a['source_image']}  ")
                lines.append(f"**Reason:** {a.get('reason', '—')}  ")
                if a.get("current_value"):
                    lines.append(f"**Detected value:** `{a['current_value']}` (confidence {conf_str})  ")
                else:
                    lines.append(f"**Evidence confidence:** {conf_str}  ")
                if a.get("rule_reference"):
                    lines.append(f"**Rule:** {a['rule_reference']}  ")
                lines.append("")

        # Reference pointers ("see base of can" etc.)
        pointers = result.get("reference_pointers") or []
        if pointers:
            lines.append("## Reference Pointers on Label")
            lines.append("")
            lines.append(
                "The label states that some mandatory information is located on "
                "another part of the package. Fields depending on those locations "
                "are routed to manual review unless the referenced surface was "
                "captured and readable."
            )
            lines.append("")
            lines.append("| Pointer text | Points to | Field hints | Surface |")
            lines.append("|---|---|---|---|")
            for p in pointers:
                fields_str = ", ".join(p.get("fields") or []) or "—"
                lines.append(
                    f"| \"{p.get('text', '')[:80]}\" | {p.get('location', '?')} "
                    f"| {fields_str} | {p.get('image', '?')} |"
                )
            lines.append("")

        # Unclaimed evidence - nothing detected by OCR is discarded
        unclaimed = result.get("unclaimed_evidence") or []
        if unclaimed:
            lines.append("## Unclaimed Evidence (Manual Review)")
            lines.append("")
            lines.append(
                f"OCR detected {len(unclaimed)} value(s) that could not be "
                "confidently associated with a mandatory field. They are retained "
                "here so no captured information is wasted."
            )
            lines.append("")
            lines.append("| Type | Value | OCR text | Surface | OCR conf | Note |")
            lines.append("|---|---|---|---|---|---|")
            for c in unclaimed[:30]:
                note = c.get("hint") or ""
                if c.get("in_base_region"):
                    note = (note + " — in base region").strip(" —")
                if not c.get("surface_usable", True):
                    note = (note + " — surface unreadable (hint only)").strip(" —")
                lines.append(
                    f"| {c.get('kind', '?')} | `{c.get('value', '')}` "
                    f"| \"{str(c.get('text', ''))[:40]}\" | {c.get('image', '?')} "
                    f"| {c.get('confidence', 0):.2f} | {note} |"
                )
            lines.append("")

        # Image quality
        lines.append("## Image Quality")
        lines.append("")
        lines.append("| Surface | Score | Usable | OCR lines | OCR confidence |")
        lines.append("|---|---|---|---|---|")
        for img in result.get("images", []):
            usable = "yes" if img.get("usable") else "no"
            ocr_conf = img.get("ocr_avg_confidence")
            ocr_conf_str = f"{ocr_conf:.3f}" if ocr_conf is not None else "—"
            lines.append(
                f"| {img.get('name', '?')} | {img.get('quality', {}).get('score', 0):.0f}/100 "
                f"| {usable} | {img.get('num_lines', 0)} | {ocr_conf_str} |"
            )
        lines.append("")

        # Visual evidence overlays (PRD 20)
        annotated = result.get("annotated_images") or []
        if annotated:
            lines.append("## Visual Evidence")
            lines.append("")
            lines.append(
                "Each captured surface below has the OCR region of every "
                "extracted declaration highlighted, colour-coded by the verdict "
                "of the rules that use it."
            )
            lines.append("")
            for entry in annotated:
                lines.append(f"### {entry.get('name', 'surface')}")
                lines.append("")
                lines.append(f"![Annotated {entry.get('name')}]({entry.get('path')})")
                lines.append("")
                lines.append("| Field | Value | Rule verdict |")
                lines.append("|---|---|---|")
                for box in entry.get("boxes", []):
                    lines.append(
                        f"| {box.get('label')} | `{box.get('value')}` "
                        f"| {box.get('status', '').replace('_', ' ')} |"
                    )
                lines.append("")

        # Regulatory citations (PRD 8)
        citations = result.get("regulation_citations") or []
        if citations:
            lines.append("## Regulatory Sources")
            lines.append("")
            lines.append(
                "Every finding that needs action is traced to the regulation it "
                "rests on - document, rule, page and the verbatim clause text."
            )
            lines.append("")
            for entry in citations:
                lines.append(
                    f"### {entry.get('rule_id', '?')} - {entry.get('status', '?')}"
                )
                lines.append("")
                if entry.get("note"):
                    lines.append(f"> {entry['note']}")
                    lines.append("")
                for citation in entry.get("citations", []):
                    page = f", p.{citation['page']}" if citation.get("page") else ""
                    lines.append(
                        f"**{citation.get('document', '?')}** - "
                        f"{citation.get('rule', '?')}{page}  "
                    )
                    if citation.get("effective_date"):
                        lines.append(
                            f"*Effective date:* {citation['effective_date']}  "
                        )
                    quote = str(citation.get("quote", "")).strip()
                    if quote:
                        if len(quote) > 400:
                            quote = quote[:397] + "..."
                        lines.append(f"> \"{quote}\"")
                    lines.append("")

        # Commodity scoping (PRD 23)
        category = result.get("product_category") or {}
        scope = category.get("rule_scope") or {}
        if scope.get("out_of_scope"):
            lines.append("## Commodity Scoping")
            lines.append("")
            lines.append(
                f"Classified as **{category.get('label', 'Unknown')}** from: "
                + ", ".join(f"`{e}`" for e in category.get("evidence", [])[:5])
            )
            lines.append("")
            lines.append(
                f"{len(scope['out_of_scope'])} conditional rule(s) concern other "
                "commodity types. They were still evaluated and their verdicts "
                "stand as reported - this list only tells the inspector which "
                "physical checks are unlikely to be relevant."
            )
            lines.append("")
            for entry in scope["out_of_scope"]:
                lines.append(f"- `{entry['rule_id']}` - {entry['reason']}")
            lines.append("")

        # Manual verification & inspector sign-off (PRD 21)
        lines.append("## Manual Verification & Inspector Sign-off")
        lines.append("")
        lines.append(legal.MANUAL_VERIFICATION_NOTE)
        lines.append("")
        if inspector_decision:
            lines.append("| | |")
            lines.append("|---|---|")
            lines.append(
                f"| Inspector | {inspector_decision.get('inspector_name') or inspector_decision.get('inspector_id', '')} |"
            )
            lines.append(f"| Inspector ID | `{inspector_decision.get('inspector_id', '')}` |")
            lines.append(f"| Decision | **{inspector_decision.get('action', '')}** |")
            lines.append(
                f"| AI decision | {(inspector_decision.get('ai_decision') or '-').replace('_', ' ')} |"
            )
            lines.append(
                f"| Final verdict | **{(inspector_decision.get('final_decision') or '-').replace('_', ' ')}** |"
            )
            lines.append(f"| Reason | {inspector_decision.get('reason', '')} |")
            lines.append(f"| Recorded at | {inspector_decision.get('timestamp', '')} |")
            if inspector_decision.get("notes"):
                lines.append(f"| Notes | {inspector_decision['notes']} |")
            lines.append("")
        else:
            lines.append(
                "**No inspector decision recorded.** This report describes an "
                "automated screening result only. It becomes an inspection record "
                "when an authorised inspector accepts or overrides the finding "
                "below."
            )
            lines.append("")
            lines.append("| Field | Entry |")
            lines.append("|---|---|")
            lines.append("| Inspector name | |")
            lines.append("| Inspector ID | |")
            lines.append("| Accept / Override | |")
            lines.append("| Final verdict | |")
            lines.append("| Reason | |")
            lines.append("| Signature | |")
            lines.append("| Date | |")
            lines.append("")

        conf = result.get("confidence")
        if conf:
            lines.append("## Confidence Breakdown")
            lines.append("")
            comps = conf.get("components", {})
            lines.append("| Component | Value |")
            lines.append("|---|---|")
            lines.append(f"| OCR confidence | {comps.get('ocr', 0):.2f} |")
            lines.append(f"| Field extraction | {comps.get('extraction', 0):.2f} |")
            lines.append(f"| Image quality | {comps.get('image_quality', 0):.2f} |")
            lines.append(f"| Rule applicability | {comps.get('rule_applicability', 0):.2f} |")
            lines.append(f"| **Overall** | **{conf.get('overall', 0):.2f}** |")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(legal.disclaimer_block())
        lines.append("")
        lines.append(
            f"*Generated by AI Legal Metrology Compliance Scanner - "
            f"processing time {result.get('processing_time_sec', '?')}s - "
            f"schema {result.get('response_schema', '?')}*"
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------

    def save(
        self,
        result: Dict[str, Any],
        markdown: Optional[str] = None,
        inspector_decision: Optional[Dict[str, Any]] = None,
    ) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        md = (
            markdown
            if markdown is not None
            else self.generate(result, inspector_decision=inspector_decision)
        )
        filename = f"{result.get('inspection_id', 'inspection')}.md"
        path = os.path.join(self.output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return path
