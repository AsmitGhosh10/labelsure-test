# STEP 04 — Rule Engine, Confidence & Compliance Score Report

**Date:** 2026-09-06
**PRD sections:** §11–§18 (rules, states, decision logic, confidence), §23 (product context), §26 (compliance score), §35 (legal safety)
**Status:** Complete
**Modules:** `labelguard_engine.py` (705), `rule_engine.py` (454), `confidence.py` (184), `compliance_score.py` (199), `product_category.py` (239), `legal.py` (49)

---

## 1. Rule engine

`LabelGuardEngine` evaluates the 31-rule LM(PC)R 2011 ruleset deterministically.
No model, no LLM, no probability — the same fields in produce the same verdicts
out. Five states: `PASS`, `FAIL`, `MANUAL_REVIEW`, `NOT_APPLICABLE`,
`UNVERIFIED`.

The honesty model is the important part: rules that **cannot** be evaluated from
photographs (physical measurement, Second Schedule lookup, dealer/export/
advertisement scope) return `NOT_APPLICABLE` with an explicit scope reason
rather than a fabricated verdict. Of the 31 rules, 23 validation types are
distinct and 14 are outside image-inspection scope by construction.

Rule 26's exemption gate runs *before* the declaration rules, as the statute
requires.

---

## 2. Confidence engine (PRD §15–§18)

Weighted fusion: OCR 0.4, extraction 0.3, image quality 0.2, rule applicability
0.1. Thresholds are configurable in `backend/app/config.py` (defaults: high
0.90, review 0.70, matching the PRD).

The guardrail is **bidirectional**, which is easy to get half-right and this
system does not:

- `NON_COMPLIANT` with confidence < 0.70 → downgraded to `MANUAL_REVIEW`.
  Low confidence must never auto-FAIL.
- `COMPLIANT` with confidence < 0.70 → downgraded to `MANUAL_REVIEW`.
  Low confidence must never auto-PASS either.

Every downgrade records `decision_downgraded_from` and appends the reason, so
the UI, the report and the PDF all say why.

---

## 3. Compliance score (PRD §26) — new this step

`compute_compliance_score()` turns rule results into 0–100 with a per-category
breakdown, so an inspector sees *how far* from compliant a package is.

```
credit  = PASS 1.0 | MANUAL_REVIEW 0.5 | FAIL 0.0
weight  = CRITICAL 3.0 | HIGH 2.0 | MEDIUM 1.5 | LOW 1.0
score   = 100 × Σ(weight × credit) / Σ(weight)
```

Four reporting buckets, mapped from the ruleset's own categories: mandatory
declarations, formatting, readability & placement, other/contextual.

Two design decisions worth stating:

1. **`NOT_APPLICABLE` and `UNVERIFIED` are excluded from the denominator** and
   reported separately as `not_assessable`. A package must not look compliant
   because most rules happened to be out of scope. Enforced by
   `test_not_applicable_is_excluded_from_the_denominator`.
2. **No assessable rules → `score = None`, not `0`.** A package nothing could be
   assessed on gets no number, not a failing one.

`test_every_ruleset_category_is_mapped` fails the build if a new rule category
is added to the ruleset without being deliberately assigned to a bucket — no
silent dumping into "other".

Every score payload ships with `system_role` and `disclaimer` attached, so the
number cannot be rendered anywhere without its caveat.

---

## 4. Commodity classification (PRD §23) — new this step

`classify_product()` infers the commodity type (food, beverage, cosmetic, drug,
household, textile, electrical, or `unknown`) from keyword evidence in the
extracted fields and raw OCR text, returning the matched evidence strings and a
confidence **capped at 0.85**.

`scope_rules()` then reports which conditional rules the category makes relevant.

The boundary is explicit and enforced by test: **classification never changes a
rule verdict.** The deterministic engine keeps ownership of PASS/FAIL/
MANUAL_REVIEW; the category only tells the inspector which conditional physical
checks are worth doing. An `unknown` category keeps *every* rule in scope — an
unclassified package is never given a narrower rulebook
(`test_unknown_category_keeps_every_rule_in_scope`).

---

## 5. Legal safety (PRD §35) — new this step

`backend/app/services/legal.py` holds one canonical wording — "AI-assisted
compliance screening" — used by the API description and `/health`, the markdown
report (header and footer), the PDF (banner and every page footer), the Gradio
header and the dashboard, and the compliance-score payload. One place to amend
if legal review changes the text.

The phrase "automated legal enforcement" appears nowhere in any output.

---

## 6. Tests

| File | Tests |
|---|---|
| `tests/test_labelguard_engine.py` | 23 |
| `tests/test_rule_engine.py` | 22 |
| `tests/test_confidence.py` | 16 |
| `tests/test_compliance_score.py` | 12 |
| `tests/test_product_category.py` | 16 |

---

## 7. Known limitations

- The ruleset is `status: DRAFT`, `verified: false`. Every report carries the
  draft warning. Rule verification against the official Gazette text is a
  legal-review task, not an engineering one, and remains open.
- Font-height, placement and spacing rules (§11's "font" and "placement" types)
  return `NOT_APPLICABLE`: they need a physical scale reference that a
  photograph does not provide. This is a deliberate refusal, not a gap in
  implementation.
- Category keywords are English and India-market specific.
