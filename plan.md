# 2-Day Build Plan — AI Legal Metrology Compliance Scanner (Bare-Bones MVP)

## Constraint
- **Timeline:** 2 days
- **Goal:** Working end-to-end scanner with deterministic rule engine, tests passing
- **Style:** Absolute bare bones. No auth, no dashboard charts, no RAG, no multi-image.

---

## Day 1 — Backend Core

### Morning (4h)
| Task | Output |
|------|--------|
| Scaffold FastAPI project, PostgreSQL models, config | `backend/` running, DB connected |
| Image quality gate (blur, brightness, contrast, glare, perspective) | `/assess-quality` endpoint |
| PaddleOCR integration + bounding boxes | `/ocr` endpoint returning structured text |

### Afternoon (4h)
| Task | Output |
|------|--------|
| Field extraction service (MRP, Net Qty, Manufacturer, Date, Consumer Care, etc.) | Normalized fields with confidence |
| Deterministic rule engine with JSON rule definitions | `PASS`/`REVIEW`/`FAIL` per rule |
| Font measurement heuristic (pixel height → estimated pt size, else MANUAL_REVIEW) | Placement check (expected region heuristics) |
| Confidence engine combining OCR + rule + image quality | Overall confidence score |

### Evening (2h)
| Task | Output |
|------|--------|
| Write unit tests for quality gate, OCR wrapper, field extraction, rule engine | `pytest` green |
| Markdown report generation | Template producing structured MD |

---

## Day 2 — Integration, Frontend, PDF, Tests

### Morning (4h)
| Task | Output |
|------|--------|
| md-to-pdf Node.js microservice (single endpoint: POST markdown → PDF) | `pdf-service/` running on port 3000 |
| Inspection storage API (save result to PostgreSQL) | `/inspections` CRUD |
| Integration tests (upload → quality → OCR → rules → report) | `pytest` green |

### Afternoon (4h)
| Task | Output |
|------|--------|
| Gradio frontend: image upload/camera, display results, download MD/PDF | `frontend/app.py` |
| Wire frontend to backend API | End-to-end flow working |
| Error handling for OCR failure, quality failure, PDF failure | Graceful degradation |

### Evening (2h)
| Task | Output |
|------|--------|
| Final integration test with real package images (or mocked) | All tests pass |
| README with run instructions | `README.md` |
| Bug fixes, polish | Stable MVP |

---

## Architecture

```
[Gradio Frontend]  ←→  [FastAPI Backend]  ←→  [PostgreSQL]
                              ↓
                    [PaddleOCR / OpenCV]
                              ↓
                    [Rule Engine (JSON rules)]
                              ↓
                    [Markdown Report]
                              ↓
                    [Node.js PDF Service]
```

---

## Rule Engine (Deterministic, JSON-based)

Rules stored in `backend/rules/legal_metrology_rules.json`:

```json
[
  {
    "rule_id": "MRP_001",
    "field": "mrp",
    "rule_type": "MANDATORY",
    "validation": "PRESENT_AND_NUMERIC",
    "severity": "HIGH",
    "source": {"document": "LM(PC)R, 2011", "rule": "Rule 6", "page": 12}
  },
  {
    "rule_id": "NET_QTY_001",
    "field": "net_quantity",
    "rule_type": "MANDATORY",
    "validation": "PRESENT_AND_VALID_UNIT",
    "severity": "HIGH",
    "source": {"document": "LM(PC)R, 2011", "rule": "Rule 6", "page": 12}
  },
  {
    "rule_id": "MANUF_001",
    "field": "manufacturer",
    "rule_type": "MANDATORY",
    "validation": "PRESENT",
    "severity": "HIGH",
    "source": {"document": "LM(PC)R, 2011", "rule": "Rule 6", "page": 12}
  },
  {
    "rule_id": "DATE_001",
    "field": "date",
    "rule_type": "MANDATORY",
    "validation": "PRESENT_AND_VALID_FORMAT",
    "severity": "HIGH",
    "source": {"document": "LM(PC)R, 2011", "rule": "Rule 6", "page": 12}
  },
  {
    "rule_id": "CONSUMER_CARE_001",
    "field": "consumer_care",
    "rule_type": "MANDATORY",
    "validation": "PRESENT",
    "severity": "HIGH",
    "source": {"document": "LM(PC)R, 2011", "rule": "Rule 10", "page": 18}
  },
  {
    "rule_id": "FONT_001",
    "field": "font_height_mm",
    "rule_type": "MEASUREMENT",
    "validation": "MIN_FONT_HEIGHT",
    "threshold_mm": 2.0,
    "severity": "MEDIUM",
    "fallback": "MANUAL_REVIEW",
    "source": {"document": "LM(PC)R, 2011", "rule": "Rule 8", "page": 15}
  },
  {
    "rule_id": "PLACEMENT_001",
    "field": "mrp_placement",
    "rule_type": "PLACEMENT",
    "validation": "NOT_BOTTOM_10_PERCENT",
    "severity": "MEDIUM",
    "fallback": "MANUAL_REVIEW",
    "source": {"document": "LM(PC)R, 2011", "rule": "Rule 6(3)", "page": 13}
  }
]
```

### Decision Logic
```
IF any HIGH severity rule FAILS:
    → NON_COMPLIANT
ELSE IF any rule returns MANUAL_REVIEW:
    → MANUAL_REVIEW
ELSE:
    → COMPLIANT
```

---

## Font Measurement Heuristic

1. Get bounding box pixel height from OCR
2. Estimate physical scale:
   - If package dimensions known (standard sizes) → calculate mm per pixel
   - Else → `MANUAL_REVIEW` (scale unknown)
3. If scale known → compare to `MIN_FONT_HEIGHT` (e.g., 2mm)
4. If below threshold → `FAIL`, else `PASS`

## Placement Heuristic

1. Divide image into regions (top 50%, bottom 50%, bottom 10%)
2. Check if MRP / key declarations are in bottom 10% → `MANUAL_REVIEW`
3. Otherwise → `PASS`

---

## Confidence Components

- OCR confidence (from PaddleOCR)
- Field extraction confidence (regex/pattern match quality)
- Image quality score (composite of blur, brightness, contrast)
- Rule applicability confidence (did we have enough info to check?)

Formula (simple weighted average):
```
confidence = 0.4 * ocr_conf + 0.3 * extraction_conf + 0.2 * image_quality + 0.1 * rule_conf
```

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/inspect` | Full inspection flow |
| POST | `/assess-quality` | Image quality only |
| POST | `/ocr` | OCR only |
| POST | `/extract-fields` | Field extraction only |
| POST | `/evaluate-rules` | Rule evaluation only |
| GET | `/inspections/{id}` | Retrieve inspection |
| POST | `/reports/md` | Generate markdown report |
| POST | `/reports/pdf` | Generate PDF (proxies to Node service) |

---

## Test Strategy

**Unit Tests:**
- `test_quality_gate.py` — blur, brightness, contrast, glare, perspective
- `test_field_extraction.py` — regex/pattern matching for MRP, qty, dates
- `test_rule_engine.py` — each rule type, decision logic
- `test_confidence.py` — confidence calculation

**Integration Tests:**
- `test_inspection_flow.py` — upload image → full flow → correct decision
- `test_report_generation.py` — MD and PDF generation

---

## File Structure

```
backend/
  app/
    __init__.py
    main.py
    config.py
    models.py
    database.py
    routers/
      inspection.py
      report.py
    services/
      quality_gate.py
      ocr_service.py
      field_extraction.py
      rule_engine.py
      confidence.py
      report_generator.py
  rules/
    legal_metrology_rules.json
  tests/
    test_quality_gate.py
    test_field_extraction.py
    test_rule_engine.py
    test_confidence.py
    test_inspection_flow.py
frontend/
  app.py          # Gradio app
  requirements.txt
pdf-service/
  package.json
  index.js        # Express server: POST /convert → PDF
reports/          # Generated reports land here
```

---

## Success Criteria (Definition of Done)

- [ ] Upload image via Gradio → get PASS/REVIEW/FAIL in < 10s
- [ ] Every finding has visual evidence (bounding box + OCR text)
- [ ] Markdown report generated with all fields, confidence, violations
- [ ] PDF generated from markdown via Node service
- [ ] All pytest tests pass
- [ ] Font measurement and placement checks return MANUAL_REVIEW when scale unknown
- [ ] No hardcoded rules in Python code — rules live in JSON

---

## Risk Mitigation for 2-Day Sprint

| Risk | Mitigation |
|------|------------|
| PaddleOCR install issues | Use `paddleocr` CPU wheel, test install first hour |
| Font measurement too hard | Immediately fallback to MANUAL_REVIEW if no scale reference |
| PDF service fails | Fallback to markdown download only |
| Tests take too long | Write tests alongside code, not at end |
| Scope creep | Strict no to anything outside this plan |
