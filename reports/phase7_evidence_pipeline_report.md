# Phase 7 — Evidence-Preserving Pipeline Report

**Date:** 2026-09-03
**Status:** Completed
**Trigger:** real can package (`test_images/img_can/`) falsely failed — MRP/date/batch live on the can base, labels say "see base of can", base photo too blurry to read
**Depends on:** Phase 6 (multi-image, reports, frontend)

---

## 1. What Was Implemented

### A. Evidence preservation — no OCR information is discarded

New `backend/app/services/evidence.py`:

- **EvidencePool**: every OCR text element from every surface is retained with confidence, bounding box, image index, source surface and preprocessing variant (`variant` field ready for additional OCR passes; currently `base`)
- **Generic candidate detection** (label-independent): currency values, quantities, dates, phone numbers, emails, addresses, entity names, batch-style codes (must contain a digit — pure-alpha uppercase strings are words, not codes), country names, package reference pointers
- **Vertical text chains**: short numeric fragments stacked in a narrow x-column (base-of-can rim text read vertically by OCR) are chained into combined codes with a base-region hint
- Elements from unusable surfaces stay in the pool flagged `surface_usable: false` — hint-only, never auto-associated

### B. Association engine (in association order)

1. Labelled same-line extraction (existing `FieldExtractor`, per surface)
2. Spatial same-row / reading-order adjacency (Phase 5 Rev 0.2, per surface)
3. **Cross-image association**: labels on one surface anchor values detected on another surface (kind-matched: currency→MRP, code→batch, entity→manufacturer, etc.)
4. **Pointer-gated**: label says "see base of can" → matching-kind candidates on any surface become valid evidence
5. **Base-region**: cylindrical package (pointer text or vertical-fragment signature) + candidate in bottom 30% of a surface → base-carried fields (MRP/date/batch)
6. **Anchor-gated** (false-positive guard): unlabelled care/entity/country candidates only associate when a matching label anchor exists somewhere in the pool — e.g. "India" inside a company name or address can never become country of origin on its own

All unlabelled associations cap at **0.65 confidence (LOW)** → always MANUAL_REVIEW, never a silent PASS.

### C. Rules run only after full evidence merge

`run_multi` now: pool → merge labelled → associate unlabelled across ALL surfaces → **then** rules. A field is no longer "missing" just because the primary surface lacks a label — relevant evidence anywhere counts.

### D. Pointer-aware rule engine

When a field is absent and the label itself states the information is elsewhere ("...EXPIRY DATE ON THE BASE OF CAN", "NO., - SEE BASE OF CAN"), absence-FAIL is replaced by MANUAL_REVIEW citing the pointer text and surface. Generic base/lid/bottom pointers cover the base-carried field set (MRP, batch, dates, best-before). Specific pointers only soften their own fields.

### E. Extraction bug fixes (backward compatible)

- `_extract_entity`: licence numbers / FSSAI / "see base of can" pointer lines / certification marks can never be returned as entity names; extended reject-aware search window (10 lines); company-name continuation ("DEL MONTE FOODS" + "PRIVATE LIMITED")
- `_extract_consumer_care`: "consumer relations / relations representative / consumer cell / contact us" keywords; toll-free phone patterns (3-3-4); `info@`-style local parts accepted
- MRP triggers extended to OCR fragments ("UNIT SALE", "ALL TAXES")

### F. Report + API

- Report gains **Reference Pointers** and **Unclaimed Evidence (Manual Review)** sections — every retained value is shown with its surface, confidence and hint
- Result JSON gains `reference_pointers`, `unclaimed_evidence`, `evidence_pool_size`, `cylindrical_package`
- API `/inspect` unchanged (multi-file), backward compatible

---

## 2. Measurement — Before vs After

### The failing can package (3 surfaces: front / blurry base / back label)

| Aspect | Before | After |
|---|---|---|
| manufacturer | **'FSSAI'** (licence text, wrong) | **'DEL MONTE FOODS'** ✓ |
| consumer_care | MISSING | Phone 800-040-1274 + INFO@MONSTERENERGY.COM ✓ |
| batch_number | MISSING | '2897036' — vertical base-rim chain, LOW → review ✓ |
| net_quantity | '350 ml' LOW | '350 ml' LOW (stable) |
| MRP_001 / DATE_001 / BATCH_001 | generic "insufficient quality" review | review with pointer-cited reasons ("label states this is on the base of can") + evidence |
| False-FAIL on back-only run | MRP/DATE/BATCH **FAIL → false 🔴 NON_COMPLIANT** (the user-reported bug) | all pointer-covered fields → 🟡 review; only ORIGIN_001 fails (honest: no origin declaration or pointer on the readable label) |
| Information retained | extracted fields only | 99-element evidence pool + 16 unclaimed candidates + 2 pointers |
| Decision (3-surface) | 🟡 80% | 🟡 83% — same verdict, now with correct fields and cited evidence |

### Full dataset (no regressions)

| Image | Before | After |
|---|---|---|
| image.jpg | 🔴 86% | 🔴 87% (unchanged — genuine absences, no pointers) |
| image2.jpg | 🔴 83% | 🔴 83% |
| image3.jpg | 🔴 95% | 🔴 93% |
| image4.jpg | 🟡 90% | 🟡 91% (date + batch still pass) |
| image5.jpg | 🔴 93% | 🔴 91% |
| sample_package.jpg | 🔴 93% | 🔴 93% |
| demo_snack (front+back) | 🟢 97% | 🟢 97% |

Net effect: **+2 correctly extracted fields on the can, 1 garbage extraction removed, 3 false-FAIL paths eliminated (pointer-covered fields), 0 regressions.**

---

## 3. Guardrails Preserved

- Unlabelled associations are always LOW → MANUAL_REVIEW (never silent PASS)
- Anchor gating prevents company/address text becoming origin
- Code candidates must contain digits (no 'PREGN'/'CAFFEINE' as batch)
- Bare 6-digit numbers are not addresses unless in address context
- Licence/BIS numbers are not phones
- No LLM/VLM — fully deterministic, auditable

---

## 4. Tests

| Suite | Count | Status |
|---|---|---|
| All previous suites | 82 | PASS |
| Can regression (new) | 23 | PASS |
| **Total** | **105** | **PASS** |

`tests/test_can_regression.py` transcribes the REAL OCR output of the failing can surfaces (front + blurry base + back label) so the exact production failure cannot reappear: entity-not-FSSAI, care via relations-representative, pointer detection, cylindrical detection, vertical-chain retention, no-false-FAIL for pointer-covered fields (3-surface AND back-only), pool completeness, plus rule-engine pointer unit tests.

---

## 5. Next Steps

1. Retest real products via Gradio (report + JSON now show pointers & unclaimed evidence)
2. Optional preprocessing variants (rotated OCR passes for base text) — schema already supports `variant`
3. Rules verification when official documents arrive (unchanged plan)
4. The retained evidence pool is the natural input for the future AI agent / RAG layer

---

## 6. Verification Checklist

- [x] Every OCR element retained (pool of 99 on the can; zero discarded)
- [x] Generic candidates detected without labels (currency, qty, date, phone, email, address, entity, code, country)
- [x] Spatial + reading-order + cross-image + pointer + base-region association
- [x] Rules run only after full multi-image evidence merge
- [x] No field marked missing when evidence exists elsewhere (pointer/cross-image)
- [x] Pointer-aware rule engine (specific + generic base pointers)
- [x] Can regression tests transcribed from the real failing images (23 tests)
- [x] 105/105 tests passing; no regressions across all datasets
- [x] API backward compatible (live-tested with the can surfaces)
- [x] No LLM/VLM introduced
