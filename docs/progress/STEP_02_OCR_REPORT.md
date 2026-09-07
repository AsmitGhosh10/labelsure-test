# STEP 02 — OCR & Field Extraction Report

**Date:** 2026-09-06
**PRD sections:** §9 (OCR requirements), §10 (fields to extract), §20 (visual evidence)
**Status:** Complete for the 14 declared fields
**Modules:** `backend/app/services/ocr_service.py` (45 lines), `field_extraction.py` (1266 lines), `evidence.py` (900 lines)

---

## 1. OCR layer

PaddleOCR (`lang="en"`, textline orientation on), loaded lazily behind a
thread-safe singleton so the API starts without pulling model weights.
`run_ocr()` normalises the result to `{texts, confidences, bounding_boxes,
avg_confidence}` — per-line text, per-line confidence and a polygon per line,
which is what PRD §9 requires and what the evidence overlay needs.

The pipeline injects `pipeline.ocr` as an attribute, so every test can supply
deterministic OCR without the model — which is why the 374-test suite runs in
~7 seconds.

---

## 2. Fields extracted (PRD §10)

| PRD field | Status | Extractor |
|---|---|---|
| Product name | ✅ | `_extract_product_name` — most prominent non-declaration block |
| **Brand** | ✅ **added this step** | `_extract_brand` |
| Manufacturer + address | ✅ | `_extract_entity('manufacturer')` + address enrichment |
| Packer + address | ✅ | `_extract_entity('packer')` |
| Importer + address | ✅ | `_extract_entity('importer')` |
| Net quantity + unit | ✅ | `_extract_net_quantity` (nutrition-table rejection) |
| MRP | ✅ | `_extract_mrp` |
| Manufacturing date | ✅ | `_extract_date('manufacturing')` |
| Packing date | ✅ | `_extract_date('packing')` |
| Expiry / best-before / use-by | ✅ | `_extract_date('best_before')` |
| Batch number | ✅ | `_extract_batch` |
| Consumer-care phone | ✅ | `_extract_consumer_care` (4-2-4 and toll-free forms) |
| Consumer-care email | ✅ | `_extract_consumer_care` |
| Country of origin | ✅ | `_extract_country_of_origin` |

Import date is not extracted: it is not a declaration required by LM(PC)R 2011
Rule 6 and no rule in the ruleset consumes it. Adding a field no rule reads
would be noise, not compliance.

### Brand extraction (new)

Three strategies, in descending trust:

1. An explicit `Brand:` / `Marketed by` label → `HIGH`, capped at 0.92.
2. A trademark mark (`™`, `®`, `(TM)`, `ACME TM`) → `HIGH`, capped at 0.88.
3. Otherwise the most prominent proper-noun block that is *not* the block
   already claimed as the generic commodity name → `LOW`, **capped at 0.62**.

The 0.62 cap is deliberate: an inferred brand is below the 0.70 review
threshold, so it can never silently satisfy a rule. A package with only a
generic name returns `brand = None` — a brand is not a mandatory declaration
under LM(PC)R 2011 and must never be invented.

Brand is resolved *before* the commodity name and its line index excluded from
that search, so a labelled or trademarked brand line cannot be reported as both.

---

## 3. Defect found and fixed during this step

**Month/year dates were not recognised.** Rule 6(1)(d) requires the *month and
year* of manufacture — so `Mfg Date: 01/2026` is the canonical compliant form.
The date value patterns covered `dd/mm/yyyy`, `01Jan26`, `1 January 2026` and
`Jan-2026`, but not `mm/yyyy`. A perfectly compliant package therefore produced
`manufacturing_date = None` → `PC2011-R06-D-001 FAIL` → a false NON_COMPLIANT
verdict on the most correctly labelled input possible.

Fixed in two places, because both had to agree:
- `field_extraction.py` — `\b(\d{1,2}[/\-.]\d{4})\b` added **last** in
  `date_value_patterns`, so a full `dd/mm/yyyy` is never truncated to `mm/yyyy`.
- `labelguard_engine.py` — the same form added to `MONTH_YEAR_RES`, so the
  engine's date-format check accepts what the extractor now reads.

Caught by `tests/test_prd_scenarios.py::TestA_FullyCompliantPackage` — the
scenario fixtures earned their place immediately.

---

## 4. Evidence preservation

No OCR element is discarded. `EvidencePipeline` pools every element from every
surface, associates unlabelled candidates via same-line, spatial, reading-order,
cross-image and package-pointer ("see base of can") strategies, and surfaces
whatever remains as `unclaimed_evidence`. All unlabelled associations cap at
0.65 → always MANUAL_REVIEW, never a silent PASS.

Every extracted field carries: `value`, `ocr_text` (what was actually read),
`ocr_confidence`, `extraction_confidence`, `confidence_level`, `bbox`,
`source_image` and a human-readable `reason` — satisfying PRD §9's requirement
that the original OCR text travel with the normalised value.

---

## 5. Tests

| File | Tests |
|---|---|
| `tests/test_field_extraction.py` | 32 |
| `tests/test_can_regression.py` | 23 |
| `tests/test_bottle_regression.py` | 19 |
| `tests/test_multi_image.py` | 14 |

---

## 6. Known limitations

- Product name vs brand on a package whose brand and generic name are printed at
  identical prominence resolves by reading order; with real OCR the brand is
  normally the larger block, but synthetic equal-size boxes are a coin flip.
- No LLM cleanup of OCR text (PRD §22 permits it; the system deliberately runs
  deterministic-only so no extraction can be hallucinated).
- English only.
