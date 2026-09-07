# STEP 05 — Human-in-the-Loop, Dashboard, Search & Reports

**Date:** 2026-09-06
**PRD sections:** §19 (inspector queue), §21 (human-in-the-loop), §27 (supervisor dashboard), §28 (inspection repository), §29 (PDF report)
**Status:** Complete
**Modules:** `hitl.py` (188), `database.py` (816), `pdf_report.py` (734), `routers/review.py`, `routers/dashboard.py`, `frontend/app.py` (915)

---

## 1. Human-in-the-loop (PRD §21) — the largest gap, now closed

`hitl.record_decision()` records an inspector **accepting** or **overriding** the
automated finding. Stored together in `inspector_decisions`: inspector ID,
inspector name, action, the AI decision it responds to, the final verdict, the
reason, free-text notes, a UTC timestamp, and a `superseded` flag.

Rules the service enforces:

| Rule | Why |
|---|---|
| Inspector ID required | Decisions are attributable or they are not decisions |
| Reason required, always | An audit trail without a reason is a log, not an audit |
| Override reason ≥ 10 chars | "ok" does not explain a disagreement |
| `ACCEPT` adopts the AI verdict; supplying a different one is rejected | A verdict must not be smuggled past the ACCEPT path |
| Overriding *to the same verdict* is recorded as `ACCEPT` | The record describes what happened, not what was typed |
| Final verdict must be one of the three compliance states | No free-text verdicts |
| A new decision supersedes the previous one, which is **kept** | Append-only history |
| **Recording a decision never mutates the stored AI result** | The machine's answer stays exactly as produced |

That last one is asserted directly by
`test_recording_a_decision_does_not_mutate_the_ai_result`.

Unlike inspection persistence (best-effort by design — an inspection must not
fail because the DB is down), decision writes are **not** best-effort: a
sign-off that did not persist surfaces as a 500, never as a success.

### Audit trail (PRD §30)

`audit_log` is append-only: no application path updates or deletes a row. Every
inspection run, decision, login, failed login and access denial is recorded with
actor, role, entity, outcome and structured details. `hitl.audit_trail()` returns
the AI decision, every inspector decision (including superseded ones) and the
logged actions for one inspection.

`test_failed_logins_are_audited_without_the_password` asserts the attempted
password never reaches the log.

---

## 2. Inspector queue (PRD §19)

`GET /review-queue` and the Gradio **Review Queue** tab list inspections with no
recorded decision, **sorted ascending by confidence** so the weakest evidence is
reviewed first. Sortable by confidence, compliance score, date, product,
manufacturer or verdict. Each row carries its PRD §17 tier: 🟢 AUTO ACCEPT
(≥ 90%), 🟡 REVIEW (70–89%), 🔴 PRIORITY REVIEW (< 70%).

Legacy rows written before the review columns existed have `NULL` review state;
the PENDING filter treats `NULL` as pending, so nothing silently disappears from
the queue.

---

## 3. Inspection repository search (PRD §28)

`GET /inspections/search` and the **Search** tab filter by product,
manufacturer, brand, inspection ID, verdict, commodity category, violated rule
id, review state and date range, with confidence bounds and six sort keys. All
filters AND-combine; text filters are case-insensitive substring matches.

Seven columns were added to `inspections` to make this searchable without
deserialising every payload: `brand`, `manufacturer`, `product_category`,
`compliance_score`, `violation_rule_ids`, `inspector_status`, `final_decision`.
`_migrate_added_columns()` adds them to an existing SQLite file on start-up, so
an old `inspections.db` keeps working.

Re-saving an inspection never clobbers a recorded human decision
(`test_resaving_never_clobbers_a_recorded_decision`).

---

## 4. Supervisor dashboard (PRD §27)

`GET /stats` and the **Dashboard** tab: total inspections, compliant /
non-compliant / manual-review counts, compliance rate, average confidence,
average compliance score, most common violated rules, manufacturer trends with
per-manufacturer non-compliance rate, product-category mix, daily trend, and
inspector activity with **override rate** — the number that tells a supervisor
whether the automation is trusted.

`GET /stats/violations` joins the violation counts to their regulation
citations, so "the most-violated rule" comes with its document, rule reference
and page.

Charts are rendered as inline HTML/CSS bars — no charting dependency, no CDN,
works offline. The dashboard carries the §35 disclaimer.

---

## 5. PDF report (PRD §29)

`generate_pdf_report()` (ReportLab, paginated A4) produces:

1. Header — inspection ID, date, product, commodity type, ruleset, surface coverage
2. The legal disclaimer banner, plus the DRAFT-ruleset warning when applicable
3. Verdict + compliance score side by side, with the score breakdown table
4. **The annotated package images** with their highlighted declaration regions
5. Extracted declarations table (value, confidence, source surface)
6. Every actionable finding with its evidence **and its regulatory citation** —
   document, rule, page and the verbatim clause quoted
7. Targeted review actions — which surface to check and why
8. **Manual verification & inspector sign-off** — the recorded decision, or
   blank ruled sign-off boxes when none exists
9. Provenance — per-surface quality and OCR confidence, ruleset version, schema
   version, processing time
10. Running footer on every page: the disclaimer, inspection ID and page number

Untrusted OCR text is escaped before it reaches ReportLab's paragraph markup —
`test_markup_in_a_field_value_cannot_break_the_pdf` feeds `<font size=99>` and
`<unclosed` through a field value and asserts the PDF still builds.

ReportLab is an optional import: without it, `PDFUnavailable` is raised, the API
answers 503 with an actionable message, and the markdown report is unaffected.

---

## 6. Frontend (PRD §3, §19, §20, §21)

Five workspaces: **Inspect** (verdict, score breakdown, review actions, visual
evidence gallery, findings, regulatory sources, extracted fields, markdown + PDF
download, raw JSON), **Inspector Sign-off**, **Review Queue**, **Search**,
**Dashboard**. The disclaimer sits under the title on every screen.

All UI text derived from OCR or classification is HTML-escaped —
`test_verdict_html_escapes_untrusted_text` feeds `<img src=x onerror=...>`
through a label and asserts it renders inert.

---

## 7. Tests

| File | Tests |
|---|---|
| `tests/test_hitl.py` | 26 |
| `tests/test_api.py` | 39 |
| `tests/test_frontend.py` | 29 |
| `tests/test_visual_evidence.py` | 19 |

---

## 8. Known limitations

- The dashboard aggregates in Python over all rows; at ~10⁵ inspections this
  wants SQL aggregation or a materialised summary table.
- Gradio holds no session identity, so the frontend sign-off form asks the
  inspector to type their ID. With `AUTH_ENABLED=true` the **API** attributes
  decisions to the authenticated token and ignores the submitted ID; wiring the
  Gradio UI to that login is not done.
- Charts are static HTML; there is no drill-down.
