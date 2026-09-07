# STEP 01 — Image Processing Report

**Date:** 2026-09-06
**PRD sections:** §24 (image quality gate), §25 (multi-image support), §31 (performance), §33 (error handling)
**Status:** Complete
**Modules:** `backend/app/services/quality_gate.py` (80 lines), `backend/app/services/pipeline.py` (multi-surface merge), `backend/app/services/annotate.py` (211 lines)

---

## 1. What was implemented

### A. Quality gate — five checks before any legal reasoning

`ImageQualityGate.assess()` returns `{usable, score, checks}` for one surface:

| Check | Metric | Default threshold | Weight |
|---|---|---|---|
| Blur | Laplacian variance | ≥ 100.0 | 25 |
| Brightness | Mean grey value | 50–240 | 25 |
| Contrast | Grey standard deviation | ≥ 30.0 | 20 |
| Glare | Fraction of pixels > 250 | ≤ 0.15 | 15 |
| Perspective | Mean Hough line skew / 90° | ≤ 0.30 | 15 |

`usable = score >= 60 and blur_pass and brightness_pass`. Blur and brightness are
hard gates: a sharp-but-glary photo can still be read, an out-of-focus one cannot.

Thresholds live in `backend/app/config.py`, not in the gate — PRD §36 requires
configurable thresholds.

### B. "Never decide from unusable imagery"

When no captured surface is usable, `InspectionPipeline.run_multi` returns early
with `MANUAL_REVIEW`, an explicit reason, an empty `rule_results` list and
`compliance_score = None`. No rule is evaluated and no score is invented —
verified by `tests/test_prd_scenarios.py::TestF_UnusableImagery`.

### C. OCR evidence can override the gate, in one direction only

A surface the gate rejected but whose OCR returned ≥ 2 lines at ≥ 0.90 average
confidence is promoted to usable, recorded as `usability_basis: "ocr_evidence"`.
Readable text is evidence regardless of what a synthetic blur metric says. The
reverse is never done: a usable-looking surface with unreadable text is not
forced through.

### D. Multi-surface merge (§25)

Up to 6 surfaces per package. Each is quality-assessed and OCR'd independently,
then merged by `EvidencePipeline`. Absence-based FAIL only fires when a field is
missing on *every* surface **and every surface is usable* — one unreadable
surface routes absence findings to MANUAL_REVIEW instead.

### E. Visual evidence overlays (§20)

`annotate.py` draws every extracted declaration's OCR bounding box onto the
surface it came from, colour-coded by the worst verdict of the rules consuming
that field (green PASS / amber MANUAL_REVIEW / red FAIL / grey unconsumed), with
the field label and the value that was read. Output lands in
`reports/inspections/evidence/` and is embedded in the PDF report.

`plan_annotations()` is pure logic with no image I/O, so the grouping and colour
rules are unit-tested without Pillow.

---

## 2. Defects found and fixed during this step

**`cv2.HoughLinesP` result shape.** The perspective check unpacked `line[0]`
unconditionally. OpenCV 4 returns `(N, 1, 4)`; OpenCV 5 returns `(N, 4)`, where
`line[0]` is a scalar — raising `TypeError: cannot unpack non-iterable
numpy.int32 object` and taking the whole quality gate down for any image with
detectable straight edges (i.e. most package photographs) on OpenCV 5. Fixed in
`quality_gate.py:49-51` by branching on `ndim`; regression-covered by
`tests/test_prd_scenarios.py::TestF_UnusableImagery::test_glare_and_perspective_are_actually_checked`.

---

## 3. Tests

| File | Tests | Covers |
|---|---|---|
| `tests/test_multi_image.py` | 14 | surface merge, absence semantics, coverage |
| `tests/test_visual_evidence.py` | 19 | overlay planning, drawing, PDF embedding |
| `tests/test_prd_scenarios.py` (Test F) | 6 | unusable imagery, glare/perspective |

All pass. Overlay tests assert the annotated file's pixels actually differ from
the source — a silently no-op overlay would fail.

---

## 4. Performance (measured, mocked OCR excluded)

Quality assessment is ~15 ms per 1000×1000 image on the dev machine; overlay
rendering ~40 ms per surface. Both are far below the PRD §31 budget; the OCR
model dominates end-to-end time.

---

## 5. Known limitations

- Perspective skew is inferred from Hough line angles, which is a proxy: a
  photograph of a genuinely skewed *label* on a square package reads as skew.
- Glare is measured as global overexposed-pixel fraction, so a small intense
  specular highlight over the MRP can pass while a large soft one fails.
- No dewarping or perspective correction is applied; surfaces are OCR'd as
  captured.
