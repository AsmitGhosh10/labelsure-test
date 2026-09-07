# Phase 4 — Field Extraction Report

**Date:** 2026-09-01
**Status:** Completed
**Test Engine:** PaddleOCR v3.7.0 (PP-OCRv6_medium)

---

## 1. What Was Implemented

A new `FieldExtractor` class in `backend/app/services/field_extraction.py` that transforms raw PaddleOCR output into structured, confidence-scored field extractions.

### Fields Supported

| Field | Variations Supported |
|-------|---------------------|
| MRP | MRP, M.R.P., MAX RETAIL PRICE, Unit Selling Price, MAX RETAIL PR |
| Net Quantity | NET WT., NET WEIGHT, NET QTY., Qty, Quantity when packed |
| Manufacturer | Manufactured By, Mfg By, Marketed By, Manufactured & Marketed By |
| Packer | Packed By, Pkd By, Packed & Marketed By, Packed On |
| Importer | Imported By, Imp By |
| Manufacturing Date | Mfg Date, Mfd, Manufacturing Date |
| Packing Date | Pkd, Packed On, Date of Packing |
| Best Before | Best Before, Use By, Expiry, Exp Date |
| Batch Number | Batch No, B.No, Lot No |
| Consumer Care | Customer Care, Consumer Care, Helpline, Toll Free, Call Us, Write to Us |
| Country of Origin | Country of Origin, Product of, Made In |

### Confidence Levels

| Level | Criteria |
|-------|----------|
| **HIGH** | Strong label + valid value + good OCR confidence (≥ 0.85) |
| **MEDIUM** | Probable match with some ambiguity or nearby context |
| **LOW** | Weak match, no explicit label, or marginal context |
| **MISSING** | No reliable evidence found |

### Output Format (per field)

```json
{
  "field_name": "mrp",
  "value": "₹20.00",
  "ocr_text": "M.R.P. (Inclusive of ail taxes).20.00",
  "ocr_confidence": 0.959,
  "extraction_confidence": 0.85,
  "confidence_level": "HIGH",
  "bbox": [[...]],
  "reason": "Price value '20.00' found on MRP declaration line",
  "line_index": 75
}
```

---

## 2. Files Changed

| File | Action | Description |
|------|--------|-------------|
| `backend/app/services/field_extraction.py` | **Created** | New robust field extraction engine |
| `tests/test_field_extraction.py` | **Created** | 24 unit tests covering MRP, net qty, dates, manufacturer, batch, consumer care |
| `test_ocr.py` | **Modified** | Replaced old `_detect_fields` with new `FieldExtractor` integration |

---

## 3. Extraction Logic

### MRP Extraction

**Strategies (in order):**
1. Find MRP keyword → extract price on same line
2. Find MRP keyword → search adjacent lines (±2) for price value
3. Find "Inclusive of all taxes" → search nearby for price
4. Detect unusual formats like `.20.00` attached to MRP text

**Rejection Guards:**
- Nutrition values (mg, g, kcal, %)
- FSSAI licence numbers
- PIN codes
- Phone numbers
- Barcodes
- Values < ₹1 or > ₹50,000

### Net Quantity Extraction

**Strategies:**
1. Find explicit label (NET WT., NET QTY.) → extract value on same or adjacent lines (±3)
2. Fallback: find standalone quantity values NOT in nutrition context

**Rejection Guards:**
- Nutrition table context (Total Fat, Protein, Calories, etc.)
- Small values (< 20g) without explicit label
- Values from serving size lines

### Date Extraction

**Formats Supported:**
- DD/MM/YYYY, DD/MM/YY
- DD-MM-YYYY, DD-MM-YY
- DD Mon YY, DD Mon YYYY
- Embedded batch dates: `17Jul28`, `15Nov28`

**Rejection Guards:**
- Address context (Road, Street, PIN, Industrial Area)
- Manufacturing date labels skipped when searching for Best Before

### Manufacturer/Packer/Importer Extraction

**Logic:**
1. Find keyword (Manufactured By, Packed By, etc.)
2. If name is on same line → HIGH confidence
3. If keyword-only line → search next 3 lines for company name indicators (Ltd, Pvt, Foods, etc.)
4. Reject nutrition lines (Protein, Fat, Calories) even if they follow the keyword
5. Fallback to next line with MEDIUM confidence if no company indicator found

---

## 4. Confidence Logic

```
HIGH   = min(ocr_confidence, 0.95)
MEDIUM = min(ocr_confidence, 0.85)
LOW    = min(ocr_confidence, 0.70)
```

Extraction confidence is capped based on strategy reliability:
- Same-line extraction → capped at 0.95
- Adjacent-line extraction → capped at 0.85
- Fallback / standalone → capped at 0.70

**LOW confidence results are flagged for MANUAL_REVIEW** and should not be auto-passed by the rule engine.

---

## 5. Tests Added

| Test | Status |
|------|--------|
| MRP standard format (Rs. 250.00) | PASS |
| MRP with rupee symbol (₹20) | PASS |
| M.R.P. dot format with taxes | PASS |
| MRP no space (MRP:Rs.20) | PASS |
| Reject nutrition value as MRP | PASS |
| Reject FSSAI number as MRP | PASS |
| Missing MRP | PASS |
| MAX RETAIL PRICE format | PASS |
| MRP surrounded by unrelated numbers | PASS |
| Net Qty explicit label | PASS |
| Reject nutrition table qty | PASS |
| Net Qty 500g | PASS |
| Date DD/MM/YYYY | PASS |
| Batch-embedded date (17Jul28) | PASS |
| Reject address date | PASS |
| Best Before date | PASS |
| Manufacturer found | PASS |
| Marketed By distinction | PASS |
| Batch number extraction | PASS |
| Consumer care phone + email | PASS |
| Consumer care missing | PASS |
| Country of origin | PASS |
| Full pipeline compliant package | PASS |
| Full pipeline missing MRP | PASS |

**Result: 24/24 tests passed**

---

## 6. Test Results on Real Images

### Before vs After (Summary)

| Metric | Before (Phase 3) | After (Phase 4) |
|--------|-----------------|-----------------|
| MRP false positives | 2 (1.1mg iron, barcode) | 0 |
| Net Qty false positives | 2 (11.23g Total Fat, 49.7g nutrition) | 1 (49.7g still slipping through on image5) |
| Manufacturer accuracy | 4/6 correct | 4/6 correct (2 OCR layout issues) |
| Date detection | 1/6 (only sample_package) | 1/6 (batch-embedded dates working) |
| Batch false positives | N/A | 0 (was "and", "ne", "NO" — all fixed) |
| Consumer Care | 5/6 | 4/6 (image2 phone missed due to OCR split) |
| Country of Origin | N/A | 2/6 (was "a facility that processes Peanuts" — fixed) |

### Per-Image Results

| Image | MRP | Net Qty | Mfg | Packer | Date | Batch | Care | Origin | Notes |
|-------|-----|---------|-----|--------|------|-------|------|--------|-------|
| **image.jpg** | MISSING | MISSING | MEDIUM | MEDIUM | MISSING | MISSING | HIGH | MISSING | MRP value not on this side; Net Wt value not visible |
| **image2.jpg** | MISSING | LOW(20g) | MEDIUM | MISSING | MISSING | MISSING | MISSING | MISSING | Back of package; MRP on front; OCR layout puts nutrition before company name |
| **image3.jpg** | MISSING | MISSING | MEDIUM | MISSING | MISSING | MISSING | HIGH | HIGH | MRP value not captured by OCR; Net Weight value on next line missed |
| **image4.jpg** | HIGH(₹20) | LOW(48g) | MEDIUM | MEDIUM | MISSING | MISSING | HIGH | HIGH | Manufacturer MEDIUM because OCR puts "Energy" before company name |
| **image5.jpg** | MISSING | LOW(49.7g) | HIGH | MISSING | HIGH | HIGH | MISSING | MISSING | Fake product; nutrition value slips through; consumer care email domain not matched |
| **sample_package.jpg** | HIGH | HIGH | HIGH | MISSING | MEDIUM | MISSING | HIGH | MISSING | Synthetic image; all core fields correct |

---

## 7. Known Limitations

### 1. OCR Layout Order Issues
When OCR reads text in an unexpected order (e.g., "Marketed By:" followed by "Energy" before the actual company name), the extractor falls back to the wrong line. This affects **image2.jpg** and **image4.jpg**.

**Mitigation:** The extractor now skips nutrition lines when searching for company names, but fallback still triggers if no valid company name is found within 3 lines.

### 2. Multi-Line Label-Value Separation
When a label (e.g., "NET WT. :") and its value (e.g., "85 g") are more than 3 lines apart, the explicit label strategy misses the value. This affects **image5.jpg**.

**Mitigation:** Increased search window from 2 to 3 lines. Could be increased further but risks false positives.

### 3. Nutrition Table Values Slipping Through
Small nutrition values like "49.7 g" can still be matched by the standalone quantity pattern when no explicit label is found. This affects **image5.jpg**.

**Mitigation:** Strategy 2 now scans bottom-up and rejects nutrition context, but explicit label strategy must find the value first.

### 4. Consumer Care Email Domain Matching
The fallback email detection requires the domain to contain care-related keywords (care, support, feedback). Generic domains like "YUMMYSNACKS.COM" are missed. This affects **image5.jpg**.

**Mitigation:** Added "write to us" and "feedback" keywords, but domain heuristic is intentionally conservative.

### 5. Missing Fields on Single-Side Capture
Real packages often have MRP, dates, and batch numbers on different sides. Single-image capture cannot capture all fields. This affects **image.jpg**, **image2.jpg**, **image3.jpg**.

**Mitigation:** This is expected behavior. The system correctly reports MISSING rather than inventing values.

### 6. Best Before Without Specific Date
"Best Before: 6 months from Mfg." does not contain a parseable date. The system correctly reports MISSING for best_before rather than guessing.

---

## 8. Recommended Next Step

**Build the deterministic rule engine (Phase 5).**

The field extractor is now producing structured, confidence-scored output. The next step is to:

1. Define JSON rule definitions for mandatory field presence
2. Build a rule engine that evaluates: `PASS` / `REVIEW` / `FAIL` for each field
3. Combine field-level decisions into an overall package decision
4. Generate a markdown compliance report

This will turn the extraction output into actual compliance decisions.

---

## 9. Verification Checklist

- [x] Field extraction service implemented
- [x] 11 fields supported with multiple variation patterns
- [x] Confidence scoring implemented (HIGH/MEDIUM/LOW/MISSING)
- [x] Bounding boxes retained in output
- [x] OCR + extraction confidence retained
- [x] False positive rejection guards implemented
- [x] Unit tests written (24 tests)
- [x] Unit tests pass (24/24)
- [x] Existing test images re-run
- [x] Results saved to `ocr_test_results/phase4_extraction_results.json`
- [x] Report generated
