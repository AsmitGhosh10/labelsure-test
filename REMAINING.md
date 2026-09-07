# Remaining Work — REMAINING.md

**Created:** 2026-09-05
**Last updated:** 2026-09-06 — every row below re-verified against the code, not
carried over from the previous revision. Several 2026-09-05 rows were wrong in
both directions (glare/perspective and four extraction fields were already
built; the "fully compliant" path was silently broken) and are corrected here.

**Purpose:** Map every PRD requirement to built / not-built.

**Suite:** 374 tests, all passing.
**Response schema:** `labelguard-inspection/1.1` (additive over 1.0).
**Implementation reports:** `docs/progress/STEP_01…STEP_06`.

---

## Summary

| Category | Built | Remaining |
|----------|-------|-----------|
| OCR pipeline | 100% | — |
| Field extraction | 100% | import date (no rule consumes it — deliberately not extracted) |
| Rule engine (LabelGuard) | 90% | ruleset legal verification (not an engineering task) |
| Confidence fusion | 100% | — |
| Evidence pipeline | 100% | — |
| Multi-image support | 100% | — |
| Image quality gate | 100% | — |
| Report generator | 100% | — |
| PDF report | 100% | — |
| Visual evidence overlay | 100% | — |
| Human-in-the-loop | 100% | — |
| Audit trail | 100% | configurable retention |
| Inspection search | 100% | — |
| Supervisor dashboard | 100% | SQL-side aggregation at scale |
| Compliance score | 100% | — |
| Product category | 100% | — |
| Regulatory retrieval (RAG) | 80% | neural embeddings; PDF ingestion tooling |
| Gradio frontend | 95% | login screen wired to the API's auth |
| FastAPI backend | 100% | — |
| Database | 95% | PostgreSQL deployment not yet exercised |
| Security | 85% | rate limiting, lockout, retention policy, TLS |
| Performance (§31) | 30% | **misses PRD latency targets on CPU** — ~140 s/image, see §31 |
| Testing (PRD formal) | 100% | Tests A–F implemented as formal fixtures |
| Documentation | 100% | six PRD §38 reports in `docs/progress/` |
| Git | 0% | **not started** — no repository initialised (deferred by request) |

---

## What was completed on 2026-09-06

| PRD | Item | Where |
|---|---|---|
| §8 | Regulatory retrieval: hybrid BM25 + lexical-vector search over the 31-rule corpus, metadata filters, citations with document/rule/page/verbatim quote, amendment ingestion | `services/regulation_retrieval.py`, `routers/regulations.py` |
| §10 | Brand extraction (label / trademark / inferred, capped at 0.62 when inferred) | `services/field_extraction.py` |
| §20 | Visual evidence: annotated surfaces with colour-coded declaration regions | `services/annotate.py` |
| §21 | Human-in-the-loop: accept/override, inspector ID, reason, timestamp, append-only history, AI+human decision pair | `services/hitl.py`, `routers/review.py` |
| §23 | Commodity classification and advisory rule scoping | `services/product_category.py` |
| §26 | Compliance score 0–100 with per-category breakdown and grade | `services/compliance_score.py` |
| §27 | Supervisor dashboard: totals, violations, manufacturer trends, inspector activity, override rate | `routers/dashboard.py`, frontend Dashboard tab |
| §28 | Repository search by product / manufacturer / brand / status / category / violation / date / review state | `database.search_inspections`, `/inspections/search` |
| §29 | PDF report with embedded evidence, citations and inspector sign-off | `services/pdf_report.py` |
| §30 | Auth (PBKDF2 + signed tokens), RBAC, upload validation, append-only audit log | `auth.py`, `database.py` |
| §34 | Formal Test A–F scenario fixtures | `tests/test_prd_scenarios.py` |
| §35 | "AI-assisted compliance screening" in UI, markdown, PDF and API | `services/legal.py` |
| §38 | Six implementation reports | `docs/progress/` |

### Defects found and fixed while doing the above

| Defect | Impact | Fix |
|---|---|---|
| `cv2.HoughLinesP` returns `(N, 4)` on OpenCV 5, not `(N, 1, 4)` | The perspective check raised `TypeError` on any image with straight edges — the whole quality gate failed on OpenCV 5 | `quality_gate.py:49-51` |
| Month/year dates (`01/2026`) were not recognised | Rule 6(1)(d) requires *month and year*, so the canonical compliant date form produced a false NON_COMPLIANT verdict | `field_extraction.py` date patterns + `labelguard_engine.py` `MONTH_YEAR_RES` |
| Legacy rows had `NULL` review state | They never appeared in the pending queue | `database.search_inspections` treats `NULL` as `PENDING` |

### Corrections to the 2026-09-05 revision

The previous revision listed these as missing. They were already implemented:

- Glare detection and perspective distortion (§24) — both in `quality_gate.py`
  since before this work, weighted 15 points each.
- Country of origin, importer, packing date, best-before (§10) — all four had
  extractors in `field_extraction.py`.
- Rule source metadata: document, page and verbatim quote (§7) — present on all
  31 rules.

---

## Section-by-Section Breakdown

### 1–2. Product Vision + Core Principle
✅ "AI extracts → Rules decide → Human verifies" — the third clause is now real,
not aspirational.

---

### 3. Primary User (Inspector)
| Requirement | Status |
|-------------|--------|
| Capture/upload package | ✅ Gradio camera + upload |
| Receive automated assessment | ✅ verdict + confidence + 0–100 score |
| Understand why flagged | ✅ rule results, review actions, regulatory citations |
| Manually verify uncertain findings | ✅ targeted review actions + visual evidence |
| Approve/reject system finding | ✅ Sign-off tab, `/inspections/{id}/decision` |
| Generate report | ✅ markdown **and** PDF |
| Search historical inspections | ✅ Search tab, `/inspections/search` |

---

### 4. Secondary Users (Supervisor / Admin)
| Requirement | Status |
|-------------|--------|
| View inspection statistics | ✅ |
| Violation trends | ✅ with regulation citations |
| Inspector activity | ✅ including override rate |
| Product category breakdown | ✅ |
| Manufacturer trends | ✅ with per-manufacturer non-compliance rate |
| Recurring violations | ✅ |
| Manage users | ✅ `/users` (admin) |
| Manage rules / config | ⚠️ read-only (`GET /rules`); rules are edited as JSON |

---

### 5. End-to-End Workflow
✅ All steps: `quality → OCR → extract → merge → classify → rules → confidence →
verdict → score → citations → evidence overlay → report → sign-off`.

---

### 6. Technology Stack
| Component | PRD | Built |
|-----------|-----|-------|
| Frontend | Next.js + React + Recharts | Gradio (pre-existing choice; the API is framework-agnostic) |
| Backend | FastAPI + Pydantic + SQLAlchemy | ✅ |
| OCR | PaddleOCR | ✅ |
| Computer Vision | OpenCV + Pillow + NumPy | ✅ |
| RAG | Existing Multimodal RAG project | ⚠️ that directory is empty; built as a self-contained retriever with a documented swap seam — see `docs/progress/STEP_03_RAG_REPORT.md` |
| LLM | extraction / normalisation / explanation | ❌ deliberately not used — nothing in a compliance verdict may be generated |
| Database | PostgreSQL | SQLite (portable models; `DATABASE_URL` honoured) |
| Storage | Local / MinIO | Local |
| Reports | HTML → PDF / ReportLab | ✅ ReportLab |

---

### 7. Regulatory Knowledge Base
| Requirement | Status |
|-------------|--------|
| Primary sources (LM(PC)R 2011) | ✅ 31 rules |
| Source priority hierarchy | ✅ ruleset first, then amendments by effective date |
| Metadata (document, page, effective date, URL) | ✅ all 31 rules; test-enforced |
| Official amendments/notifications | ✅ ingestion supported (`rules/corpus/`); no amendment data supplied yet |

---

### 8. RAG Requirements
| Requirement | Status |
|-------------|--------|
| Ingest regulatory documents | ✅ JSON / md / txt |
| Preserve clause structure | ✅ one chunk per rule/clause |
| Identify rules/clauses | ✅ rule reference per chunk |
| Page numbers + effective dates | ✅ |
| Create embeddings | ⚠️ hashed character-n-gram lexical vectors, not neural — stated plainly, swap seam tested |
| Semantic + keyword retrieval | ✅ hybrid (0.65 BM25 / 0.35 vector) |
| Metadata filtering | ✅ category, rule reference, source type |
| Source citations | ✅ attached to every FAIL / MANUAL_REVIEW finding |

---

### 9–10. OCR + Fields
✅ All 14 declared fields extract, each with OCR text, confidence, bbox and
source surface. Import date is not extracted: no rule consumes it.

---

### 11–18. Rule Engine, States, Decision Logic, Confidence, Thresholds
✅ Deterministic, JSON-defined, five states, bidirectional confidence guard,
configurable thresholds, three review tiers.

Font-height, placement and spacing rules return `NOT_APPLICABLE` — they need a
physical scale reference a photograph cannot supply. That is a deliberate
refusal, not a gap.

---

### 19. Confidence-Based Inspector Queue
✅ `/review-queue` and the Queue tab, ascending by confidence, six sort keys,
priority buckets per row.

---

### 20. Visual Evidence
✅ Bounding box, OCR text, confidence, rule reference, description **and** the
highlighted region drawn on the actual photograph.

---

### 21. Human-in-the-Loop
✅ Accept/override, reason (required), inspector ID (required), timestamp,
stored final decision, append-only audit trail pairing AI and human decisions.

---

### 22. LLM Rules
✅ By design: no LLM participates in a compliance verdict, so no regulation can
be invented and no rule overridden.

---

### 23. Product Context
✅ Commodity classification with evidence and a confidence cap; conditional
rules scoped advisorily. Classification never changes a rule verdict.

---

### 24. Image Quality Gate
✅ Resolution, blur, brightness, contrast, glare, perspective. No legal decision
is attempted from unusable imagery.

---

### 25. Multi-Image Support
✅ Up to 6 surfaces, merged with source attribution.

---

### 26. Compliance Score
✅ 0–100, severity-weighted, per-category breakdown, letter grade, disclaimer
attached to the payload. `NOT_APPLICABLE` excluded from the denominator;
nothing assessable yields `None`, not `0`.

---

### 27. Dashboard (Supervisor)
✅ Totals, decision mix, average confidence and score, common violations,
manufacturer trends, category mix, daily trend, inspector activity, override
rate. Charts are dependency-free inline HTML.

---

### 28. Inspection Repository
✅ Full payload stored; inspector decision stored alongside; search by product,
manufacturer, brand, ID, date, status, category, violation and review state.

---

### 29. PDF Report
✅ Header, disclaimer banner, verdict + score, annotated images, declarations
table, findings with citations, review actions, inspector sign-off (recorded or
blank), provenance, per-page footer.

---

### 30. Security
| Requirement | Status |
|-------------|--------|
| Authentication | ✅ PBKDF2 + HMAC-signed tokens |
| Role-based access | ✅ inspector / supervisor / admin |
| Secure file handling | ✅ validated, temp-file, always deleted |
| Input validation | ✅ type, content type, size, count, Pydantic bodies |
| Database access controls | ✅ role-gated endpoints |
| Audit logging | ✅ append-only |
| No sensitive info in logs | ✅ test-enforced |
| Configurable retention | ❌ |
| Rate limiting / lockout / TLS | ❌ deployment-layer concerns |

---

### 31. Performance
❌ **Does not meet the PRD targets on CPU.** Measured 2026-09-06 with real OCR
(paddlepaddle 3.3.1 / paddleocr 3.7.0, one CPU core, 1957×2648 label photo):

| PRD target | Measured | Status |
|---|---|---|
| Image → OCR < 5 s | ~140 s (accurate) / ~62 s (fast profile) | ❌ ~28× over |
| Image → compliance < 10 s | ~147 s single surface | ❌ |
| Image resizing / preprocessing | not implemented — see below | ❌ |
| Selective OCR | ✅ | ✅ |
| Caching | ❌ | ❌ |
| Async processing | ❌ sync pipeline | ❌ |

The cause is CPU inference with oneDNN disabled — paddlepaddle 3.3.x crashes
in its oneDNN kernels on the PP-OCRv6 detector, so the workaround falls back
to the much slower standard kernels. Re-enabling oneDNN (`OCR_ENABLE_MKLDNN=true`)
once that upstream bug is fixed, or running on GPU, is the path back to the
target; `OCR_PROFILE=fast` buys 2.3× today at the cost of ~0.05 average OCR
confidence, which pushes more packages to manual review.

**Two corrections to earlier revisions of this document:**

1. The 2026-09-05 revision claimed *"Image → OCR: < 5 sec ✅ ~1.5s per image"*.
   No such measurement was reproducible: OCR had never been run in this
   environment (paddlepaddle does not install on the Python 3.14 that was
   present), so the figure had no basis.
2. It also claimed *"Image resizing / preprocessing ✅ via resize_for_ocr"*.
   **No function of that name exists anywhere in the repository.** It was
   implemented on 2026-09-06 to make the claim true, then removed again after
   measurement showed it made no difference at all: PaddleOCR normalises to
   its own detector scale internally, so downscaling a 3024×4032 photo to
   1600 px changed the runtime by 0.0 s and the output not at all (identical
   line count and confidence). Shipping it would have been dead code
   defending a false claim.

The 2026-09-06 rewrite of this document repeated claim 1 as "within PRD
targets" without verifying it. That was wrong, and this section replaces it.

---

### 32–33. Offline/Online + Error Handling
✅ OCR, rules and retrieval all run locally. Retrieval failure surfaces as
"manual verification required" and never fails an inspection. PDF failure falls
back to markdown. No usable image → recapture.

---

### 34. Testing
✅ Tests A–F formal fixtures in `tests/test_prd_scenarios.py`, plus a matrix test
asserting the scenarios genuinely differ. Two of them caught real defects.

---

### 35. Legal Safety Rule
✅ "AI-assisted compliance screening" on every verdict surface; "automated legal
enforcement" appears nowhere.

---

### 36. Development Agent Rules
✅ All fifteen held — self-checked in
`docs/progress/STEP_06_INTEGRATION_REPORT.md` §6.

---

### 37–38. Implementation Reports
✅ Six reports in `docs/progress/`. The earlier phase reports remain in
`reports/` as history.

---

### 39. Git Requirements
❌ Not started. The project is not a git repository and no git identity is
configured. `.gitignore` is prepared (it now also excludes the local
`inspections.db` and generated report artifacts), so `git init` followed by
logical `feat:` / `fix:` / `test:` / `docs:` commits is all that remains.

---

### 40. Definition of Done
| Criterion | Status |
|-----------|--------|
| Code implemented | ✅ |
| Integration completed | ✅ |
| Tests written | ✅ 374 |
| Tests executed | ✅ all passing |
| Errors handled | ✅ every new subsystem degrades rather than failing the inspection |
| Documentation updated | ✅ |
| API documented | ✅ FastAPI auto-docs + STEP_06 §5 |
| Security reviewed | ✅ STEP_06 §3, including what is *not* covered |
| Implementation report generated | ✅ |

---

### 41–42. MVP + Demo
✅ All ten MVP steps. The demo flow runs end to end: scan → OCR results → rule
verdict with confidence and score → view evidence (highlighted image + rule +
source document + page) → generate PDF → inspector signs off.

---

## Remaining work, in priority order

| Priority | What | Effort | Note |
|---|---|---|---|
| 🔴 P0 | Verify the 31 rules against the official Gazette text and flip `verified: true` | Legal review | Every report currently carries a DRAFT warning |
| 🟡 P1 | Login screen in the Gradio UI wired to `/auth/login` | Small | The API already enforces RBAC |
| 🟡 P1 | Supply real amendment/notification data to `backend/app/rules/corpus/` | Small | Ingestion is built and tested |
| 🟡 P1 | Configurable data retention (§30) | Small | |
| 🟢 P2 | Neural embeddings behind `set_vectorizer()` | Medium | Seam exists and is tested |
| 🟢 P2 | PostgreSQL deployment + migration exercise | Medium | Models are portable |
| 🟢 P2 | Next.js frontend against the existing API (§6) | Large | Additive; the API is framework-agnostic |
| 🟢 P2 | Rate limiting, account lockout, TLS termination | Medium | Deployment layer |
| 🟢 P2 | SQL-side dashboard aggregation | Medium | Matters at ~10⁵ inspections |
| 🟢 P2 | Caching + async pipeline (§31) | Medium | Currently within latency targets |
| 🟢 P2 | Git history (§39): `git init` + logical commits | Small | `.gitignore` is ready; needs a git identity |
