# Phase 5 — Rule Engine + Confidence Fusion Report

**Date:** 2026-09-03
**Status:** Completed (draft ruleset — pending official document verification)
**Depends on:** Phase 4 field extraction (all tests passing)
**Rev 0.2:** Spatial (bbox) extraction upgrade after image4 ground-truth review — see §8

---

## 1. What Was Implemented

The full decision pipeline: **quality gate → OCR → field extraction → deterministic rule engine → confidence fusion → final verdict**, plus a FastAPI service exposing every step.

### Components

| Component | File | Purpose |
|-----------|------|---------|
| Draft ruleset | `backend/app/rules/legal_metrology_rules.json` | 9 JSON-defined rules, all marked `verified: false` with DRAFT source status |
| Rule engine | `backend/app/services/rule_engine.py` | Deterministic evaluation: PASS / FAIL / MANUAL_REVIEW / NOT_APPLICABLE / UNVERIFIED |
| Confidence engine | `backend/app/services/confidence.py` | Signal fusion + decision guardrails |
| Inspection pipeline | `backend/app/services/pipeline.py` | Orchestrates the full flow, returns complete JSON result |
| OCR service | `backend/app/services/ocr_service.py` | Lazy PaddleOCR singleton (API starts fast) |
| FastAPI app | `backend/app/main.py` + `routers/inspection.py` | 7 endpoints incl. full `/inspect` |
| Batch runner | `run_pipeline.py` | Full pipeline over a directory of images |
| Tests | `tests/test_rule_engine.py`, `tests/test_confidence.py` | 38 new unit tests |

---

## 2. Ruleset (DRAFT)

| Rule ID | Type | Fields | Severity | Validation |
|---------|------|--------|----------|------------|
| MRP_001 | MANDATORY | mrp | HIGH | PRESENT_AND_VALID_PRICE |
| NET_QTY_001 | MANDATORY | net_quantity | HIGH | PRESENT_AND_VALID_UNIT |
| ENTITY_001 | MANDATORY_ANY | manufacturer / packer / importer | HIGH | PRESENT |
| DATE_001 | MANDATORY_ANY | manufacturing_date / packing_date | HIGH | PRESENT |
| CONSUMER_CARE_001 | MANDATORY | consumer_care | HIGH | PRESENT |
| ORIGIN_001 | MANDATORY | country_of_origin | HIGH | PRESENT |
| BATCH_001 | MANDATORY | batch_number | MEDIUM | PRESENT |
| IMPORTER_001 | CONDITIONAL | importer | HIGH | PRESENT (when origin ≠ India) |
| BEST_BEFORE_001 | CONDITIONAL | best_before | MEDIUM | VALID_DATE (when field present) |

**Honesty guardrails built into the ruleset:**

- `ruleset_verified: false` + every rule `verified: false` — no legal citation is claimed yet
- `enforce_verification` flag: when flipped to `true` (after official doc review), any unverified rule evaluates to `UNVERIFIED` and is routed to MANUAL_REVIEW — the engine can never issue a PASS/FAIL on an unverified rule in that mode
- All sources currently read `"TBD - pending official document review"`

**When the official LM(PC)R documents arrive:** update citations + `verified` flags in the JSON only. Zero engine changes required.

---

## 3. Rule Engine Logic

### Statuses

```
PASS            field declared, valid, MEDIUM+ confidence
FAIL            mandatory field absent (good image) or mandatory-any fully absent
MANUAL_REVIEW   LOW confidence candidate | unparseable value | bad image (absence untrustworthy)
                | indeterminate applicability | unverified rule (in verified mode)
NOT_APPLICABLE  conditional rule whose condition excludes it (e.g. origin = India → importer not required)
UNVERIFIED      rule not verified against official docs (only in enforce_verification mode)
```

### Guardrails (the important ones)

1. **Absence is not evidence on a bad image.** If quality gate says unusable (or score < 60), a missing mandatory field becomes MANUAL_REVIEW, not FAIL.
2. **LOW confidence never FAILs.** A LOW-confidence extraction routes to MANUAL_REVIEW.
3. **Garbled values never FAIL.** Declared-but-unparseable (e.g. MRP "Rs. ???", quantity "49.7" without unit) → MANUAL_REVIEW — OCR garble is indistinguishable from actual non-compliance, so a human decides.
4. **Indeterminate applicability → MANUAL_REVIEW.** E.g. importer rule when country of origin wasn't detected: "cannot determine applicability".
5. **No legal invention.** Engine only checks presence + mechanical validity; all legal semantics live in the JSON rules pending verification.

### Decision Fusion

```
any FAIL (any severity)      → NON_COMPLIANT
else any REVIEW/UNVERIFIED   → MANUAL_REVIEW
else                          → COMPLIANT
```

---

## 4. Confidence Engine

### Components (weighted)

```
overall = 0.4 × ocr_avg_confidence
        + 0.3 × mean_extraction_confidence (detected fields only)
        + 0.2 × image_quality_score / 100
        + 0.1 × rule_applicability (share of rules reaching definitive PASS/FAIL)
```

### Decision Fusion Guardrails (Phase 6 behavior)

| Rule engine says | Overall confidence | Final decision |
|------------------|--------------------|----------------|
| NON_COMPLIANT | ≥ 70% | 🔴 NON_COMPLIANT |
| NON_COMPLIANT | < 70% | 🟡 MANUAL_REVIEW (**downgraded** — low confidence must never auto-FAIL) |
| COMPLIANT | ≥ 70% | 🟢 COMPLIANT |
| COMPLIANT | < 70% | 🟡 MANUAL_REVIEW (**downgraded** — low confidence must never auto-PASS either) |
| MANUAL_REVIEW | any | 🟡 MANUAL_REVIEW |

Every downgrade is recorded (`downgraded_from`) with the reason, so the evidence trail is preserved.

---

## 5. API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| POST | `/inspect` | Full pipeline: upload image → complete verdict JSON |
| POST | `/assess-quality` | Quality gate only |
| POST | `/ocr` | OCR only (texts + confidences + bboxes) |
| POST | `/extract-fields` | Extraction from pre-computed OCR output |
| POST | `/evaluate-rules` | Rules + confidence from extracted fields |
| GET | `/rules` | Loaded ruleset (transparency: severity, source, verification status) |

Verified live: `uvicorn backend.app.main:app` → `/health` OK, `/rules` returns 9 draft rules, `/inspect` on `sample_package.jpg` returned 🔴 NON_COMPLIANT @ 93% confidence in 4.4s (matches batch runner output exactly).

---

## 6. Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| Field extraction (Phase 4 + spatial upgrade) | 32 | PASS |
| Rule engine (new) | 22 | PASS |
| Confidence engine (new) | 16 | PASS |
| **Total** | **70** | **PASS** |

New coverage includes: every status path, all three guardrails, mandatory-any logic, both conditional rules (all three applicability outcomes), verified-mode blocking, draft JSON loading, dataclass input support, all fusion downgrade paths, component math, columnar label\|value layouts, and care-instruction false-positive rejection.

---

## 7. Real Image Results (6 images, full pipeline)

| Image | Quality | OCR conf | Overall conf | Decision | Failed (HIGH) | Review |
|-------|---------|----------|--------------|----------|---------------|--------|
| image.jpg | 85 | 0.905 | 86% | 🔴 NON_COMPLIANT | MRP, NET_QTY, DATE, ORIGIN | IMPORTER |
| image2.jpg | 85 | 0.917 | 83% | 🔴 NON_COMPLIANT | MRP, DATE, CARE, ORIGIN | NET_QTY, IMPORTER |
| image3.jpg | 100 | 0.988 | 95% | 🔴 NON_COMPLIANT | MRP, NET_QTY, DATE | — |
| image4.jpg | 100 | 0.919 | 90% | 🟡 MANUAL_REVIEW | — | NET_QTY |
| image5.jpg | 100 | 0.991 | 93% | 🔴 NON_COMPLIANT | MRP, CARE, ORIGIN | NET_QTY, IMPORTER |
| sample_package.jpg | 85 | 0.995 | 93% | 🔴 NON_COMPLIANT | ORIGIN | IMPORTER |

*(Rev 0.2 results, after the spatial extraction upgrade in §8. Full JSON: `ocr_test_results/phase5_pipeline_results.json`. Processing time: 2.6–31s per image, PaddleOCR dominated.)*

### Analysis — why all 6 are NON_COMPLIANT

**The engine is behaving correctly given its inputs.** The dominant failure mode is absence-based FAIL caused by **single-side capture** (known Phase 4 limitation §7.5): MRP, dates and batch numbers are usually on a different panel of the package than the photographed side. "Not found on this image" ≠ "not on the package".

Notable correct behaviors:

- **image4** → 🟡 MANUAL_REVIEW after the spatial fix (§8): date `15Nov28` and batch `B05P` now correctly extracted from the columnar `MFD. | BATCH NO.` layout; the only open item is net quantity (48g found with LOW confidence — honestly routed to review)
- **image4 NET_QTY** → MANUAL_REVIEW (the 48g nutrition slip from Phase 4 got LOW confidence — guardrail #2 caught it instead of FAILing/PASSing)
- **image5 / sample_package IMPORTER_001** → MANUAL_REVIEW "origin not detected — cannot determine applicability" (guardrail #4)
- **image3 / image4 IMPORTER_001** → NOT_APPLICABLE (origin = India)
- **sample_package** → only ORIGIN + BATCH fail; every field the synthetic image actually contains passed

### What this exposes (by design)

For a real inspection workflow, a FAIL from this system must currently be read as **"not found on the captured surface — verify remaining surfaces"**. That framing is honest but not yet inspection-grade.

---

## 8. Rev 0.2 — Spatial Extraction Upgrade (image4 ground-truth fix)

**Trigger:** manual review showed image4's manufacturing date is printed under `BATCH NO.` in a two-column layout, but DATE_001 and BATCH_001 returned FAIL.

**Root cause:** the extractor matched label→value by **OCR line order** only. In columnar layouts (labels left column, values right column), OCR interleaves other columns (the address column at x=654-926) between a label and its value in reading order, so (a) the value fell outside the ±2-line window or (b) the ±2-line *context* address check rejected a valid date because an address line sat between them.

**Fix — spatial candidate matching in `field_extraction.py`:**

1. New `_vertical_overlap()` helper: two boxes on the same visual row (overlap ≥ 0.2 of the shorter height) → candidate ranked by bbox distance (MEDIUM confidence, "spatially aligned" reason)
2. Date extraction order: same line → **same visual row** → line-order fallback → batch-embedded
3. Address rejection now checks the candidate's **own line** only (a date token like `15Nov28` is not an address; the old ±2 context check punished valid dates sitting near address columns)
4. Cross-type protection: a date candidate on the same row as a *different* date-type label can't be stolen by line-order fallback
5. Batch extraction gained a label-only strategy: standalone alphanumeric codes (`B05P`) spatially aligned with the batch label; rejects date-like strings, quantity values (`48g`), lic/FSSAI/PIN, nutrition words
6. Care-instruction lines ("For Feedback & queries (mention batch no. ...)") no longer act as batch labels — this fixed an image2 false positive where `Protein` (nutrition row header) was extracted as a batch number

**Result on image4:** `manufacturing_date = 15Nov28` (MEDIUM), `batch_number = B05P` (MEDIUM) → DATE_001 PASS, BATCH_001 PASS → overall 🟡 MANUAL_REVIEW (net qty only). All other images unchanged except image2's false batch positive removed. 8 new unit tests; 70/70 passing.

---

## 9. Recommended Next Steps (priority order)

1. **Multi-image inspection (highest impact).** Accept 2–4 images as one package (front/back/sides). Field extraction merges detections across images; absence-based FAIL only fires when ALL captured surfaces lack the field. This directly fixes the false-FAIL mode above and is required for the 50-image evaluation dataset (Phase 13).
2. **Rules verification (blocked on official documents).** When LM(PC)R 2011 + amendments arrive: fill in citations, flip `verified` flags, set `enforce_verification: true`. Engine needs zero changes.
3. **Evidence report generation (Phase 9/11).** The data is already in the pipeline output (bboxes, ocr_text, reasons, sources) — a markdown/PDF report generator is the next quick win.

---

## 10. Verification Checklist

- [x] Draft ruleset JSON (9 rules, verification-honest)
- [x] Rule engine with 5 statuses + 5 guardrails
- [x] Confidence engine with weighted fusion + downgrade guardrails (both directions)
- [x] Full pipeline orchestrator with complete JSON output
- [x] FastAPI app with 7 endpoints, live-tested
- [x] 70/70 unit tests passing (46 new across rule/confidence/spatial extraction)
- [x] 6 real images run end-to-end with decisions + evidence saved
- [x] image4 ground-truth fix verified (date + batch via spatial alignment)
- [x] Report generated
