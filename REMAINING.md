# Remaining Work — REMAINING.md

**Created:** 2026-09-05
**Last updated:** 2026-09-10 — verified against the code, not against the
previous revision of this document.

**Purpose:** Map every PRD requirement to built / not-built, honestly.

**Suite:** 480 tests, all passing.
**Response schema:** `labelguard-inspection/1.1`.
**Implementation reports:** `docs/progress/STEP_01…STEP_06`.

> **How to read this file.** Every ✅ below was checked against the code or a
> live endpoint on 2026-09-10. Where an earlier revision claimed something that
> turned out to be false, the claim and its correction are both recorded rather
> than quietly edited away. A document that only ever reports success is not
> worth reading.

---

## Corrections to the 2026-09-07 revision

That revision contradicted itself in several places, and its header was stale.

| Claim | Reality |
|---|---|
| "Suite: 418 tests" | 480, after the RAG and frontend work |
| Summary: "Configurable data retention implemented" / §30 table: "❌" | Implemented. `database.purge_expired_records`, with an admin route and tests |
| Summary: "Corpus amendments ingested (2017, 2021, 2022)" / priority list: "🟡 P1 Supply real amendment data" | Ingested. Three files in `backend/app/rules/corpus/`, 37 chunks total |
| §39: "The project is not a git repository" | It is, with a remote and pushed history |
| §6: "RAG — that directory is empty" | Not empty. The project is present, and the pipeline has been adapted from it |
| Priority list: "🟢 P2 Caching + async pipeline — currently within latency targets" | Not within targets. §31 of the same document said so |

---

## Summary

| Category | Built | Remaining |
|----------|-------|-----------|
| OCR pipeline | 100% | — |
| Field extraction | 100% | Import date deliberately not extracted; no rule consumes it |
| Rule engine | 100% | Legal provenance of `verified: true` is unrecorded — see §7 |
| Confidence fusion | 100% | — |
| Evidence pipeline | 100% | — |
| Multi-image support | 100% | — |
| Image quality gate | 100% | — |
| Report generator + PDF | 100% | — |
| Human-in-the-loop | 100% | — |
| Audit trail + retention | 100% | — |
| Inspection search | 100% | — |
| Supervisor dashboard | 100% | — |
| Compliance score | 100% | — |
| Product category | 100% | — |
| Regulatory retrieval | 100% | Lexical vectors, not neural; seam tested but unused |
| Regulation question answering | 100% | — |
| Gradio frontend | 100% | — |
| React frontend | 100% | No automated tests |
| FastAPI backend | 100% | 32 endpoints |
| Database | 100% | SQLite default; PostgreSQL supported, never exercised |
| Security | 95% | Rate limiting and TLS are deployment-layer |
| **Performance (§31)** | **30%** | **Misses the latency targets by ~13× — the one real functional gap** |
| Testing | 100% | 480 Python tests; none for the React app |
| Documentation | 100% | — |
| Git | 100% | Branch `test-branch` pushed |

---

## The short version

One functional gap, two data gaps, and some unexercised paths.

1. **Latency.** ~64 s per full-resolution photograph against a 5 s target.
2. **Ruleset provenance.** All 31 rules assert `verified: true`; nothing records
   who verified them against the Gazette.
3. **A citation error in the corpus.** One amendment chunk cites the wrong rule.
4. **Two frontends.** Both live against one schema.

Everything else in the PRD is built and tested.

---

## What was completed on 2026-09-09

| PRD | Item | Where |
|---|---|---|
| §6, §8, §22 | Grounded RAG: hybrid retrieval → RRF fusion → optional cross-encoder rerank → optional Groq generation, adapted from `rag/Multimodal_RAG_Project-main` | `services/rag_service.py`, `routers/rag.py` |
| §6 | React + shadcn/ui frontend, seven routes, against the existing API | `web/` |
| §20 | Endpoint serving annotated evidence to a browser, path-confined to the evidence directory | `routers/inspection.py` |
| §33 | Intent classification ahead of retrieval | `services/rag_service.py` |

### Defects found and fixed while doing the above

| Defect | Impact | Fix |
|---|---|---|
| Every input went to retrieval | "hey" returned a page of statutory refusal; "what can you do" was answered *from the corpus*, presenting a question about the tool as a regulatory finding | `classify_intent` diverts smalltalk and capability questions before retrieval |
| Generation failures swallowed by a bare `except` | A wrong model name was indistinguishable from no API key; cost two debugging cycles | `last_error` recorded, reported by `GET /rag` |
| Reasoning models bill thinking against `max_tokens` | The whole budget could be spent before a word was written, returning empty content that looked like a generation failure | `reasoning_effort` set low; the empty-content case names itself |
| Default model `llama-3.1-8b-instant` | `model_not_found` — availability varies by Groq account | Default is now `openai/gpt-oss-20b` |
| `GET /rag` advertised an uninstalled cross-encoder | Status lied about capability | Checked via `importlib.util.find_spec`, without importing torch |
| Three tests read `GROQ_API_KEY` from a developer's `.env` | The suite silently exercised a paid API path | `conftest.py` clears it |
| Frontend read `confidence`, `compliance_score`, `product_category` as scalars | They are composite objects; rendered as `NaN` | Types corrected against the real payload |
| Frontend filtered rules on `COMPLIANT` / `NON_COMPLIANT` | The engine emits `PASS` / `FAIL`; the violations table silently matched nothing | Filter corrected |
| Dashboard multiplied rates already on a 0–100 scale | Displayed `3330%` | Scale made explicit per metric |

---

## What was completed on 2026-09-06

| PRD | Item | Where |
|---|---|---|
| §8 | Regulatory retrieval: hybrid BM25 + lexical-vector search, metadata filters, citations with document/rule/page/quote | `services/regulation_retrieval.py`, `routers/regulations.py` |
| §10 | Brand extraction, capped at 0.62 when inferred | `services/field_extraction.py` |
| §20 | Visual evidence: annotated surfaces with colour-coded regions | `services/annotate.py` |
| §21 | Human-in-the-loop: accept/override, append-only history, AI+human decision pair | `services/hitl.py`, `routers/review.py` |
| §23 | Commodity classification and advisory rule scoping | `services/product_category.py` |
| §26 | Compliance score 0–100 with per-category breakdown and grade | `services/compliance_score.py` |
| §27 | Supervisor dashboard | `routers/dashboard.py` |
| §28 | Repository search across nine fields | `database.search_inspections` |
| §29 | PDF report with evidence, citations and sign-off | `services/pdf_report.py` |
| §30 | Auth, RBAC, upload validation, append-only audit log | `auth.py`, `database.py` |
| §34 | Formal Test A–F scenario fixtures | `tests/test_prd_scenarios.py` |
| §35 | "AI-assisted compliance screening" on every surface | `services/legal.py` |

### Defects found and fixed

| Defect | Impact | Fix |
|---|---|---|
| `cv2.HoughLinesP` returns `(N, 4)` on OpenCV 5, not `(N, 1, 4)` | The perspective check raised `TypeError` on any image with straight edges — the whole quality gate failed | `quality_gate.py:49-51` |
| Month/year dates (`01/2026`) unrecognised | Rule 6(1)(d) requires month and year, so the canonical compliant form produced a false NON_COMPLIANT verdict | `field_extraction.py` + `labelguard_engine.py` |
| Legacy rows had `NULL` review state | They never appeared in the pending queue | `NULL` treated as `PENDING` |

---

## Section-by-Section Breakdown

### 1–2. Product Vision + Core Principle
✅ "AI extracts → Rules decide → Human verifies", all three clauses real.

### 3. Primary User (Inspector)
| Requirement | Status |
|-------------|--------|
| Capture/upload package | ✅ both frontends |
| Receive automated assessment | ✅ verdict + confidence + 0–100 score |
| Understand why flagged | ✅ rule results, review actions, citations |
| Manually verify uncertain findings | ✅ targeted review actions + visual evidence |
| Approve/reject system finding | ✅ `/inspections/{id}/decision` |
| Generate report | ✅ markdown and PDF |
| Search historical inspections | ✅ `/inspections/search` |

### 4. Secondary Users (Supervisor / Admin)
| Requirement | Status |
|-------------|--------|
| Inspection statistics | ✅ |
| Violation trends | ✅ with citations |
| Inspector activity, override rate | ✅ |
| Product category breakdown | ✅ |
| Manufacturer trends | ✅ |
| Manage users | ✅ `/users` (admin) |
| Manage rules / config | ⚠️ read-only (`GET /rules`); rules are edited as JSON |

### 5. End-to-End Workflow
✅ `quality → OCR → extract → merge → classify → rules → confidence → verdict →
score → citations → evidence overlay → report → sign-off`.

### 6. Technology Stack
| Component | PRD | Built |
|-----------|-----|-------|
| Frontend | Next.js + React + Recharts | ⚠️ React + Vite + Tailwind + shadcn/ui. Vite rather than Next.js: no SSR or SEO surface on an authenticated internal tool. Reversible — the API is framework-agnostic |
| Backend | FastAPI + Pydantic + SQLAlchemy | ✅ |
| OCR | PaddleOCR | ✅ 3.7.0 |
| Computer Vision | OpenCV + Pillow + NumPy | ✅ |
| RAG | Existing Multimodal RAG project | ✅ adapted — see §8 |
| LLM | extraction / normalisation / explanation | ⚠️ used only for regulation question answering. Never in a verdict |
| Database | PostgreSQL | ⚠️ SQLite default; portable DSN, never deployed on PostgreSQL |
| Storage | Local / MinIO | Local |
| Reports | ReportLab | ✅ |

Full detail in [TECH_STACK.md](TECH_STACK.md).

### 7. Regulatory Knowledge Base
| Requirement | Status |
|-------------|--------|
| Primary sources (LM(PC)R 2011) | ✅ 31 rules |
| Source priority hierarchy | ✅ ruleset first, then amendments by effective date |
| Metadata (document, page, effective date, URL) | ✅ all 37 chunks; test-enforced |
| Official amendments/notifications | ✅ 2017, 2021, 2022 ingested |

🔴 **Two open items here.**

**Provenance.** All 31 rules carry `verified: true`, so no report shows a DRAFT
warning. Nothing in the repository records who checked them against the Gazette
or when. If that review did not happen, every report asserts more than it knows.

**A wrong citation.** `AM2017-R06-CARE` in
`backend/app/rules/corpus/lmpcr_amendment_2017.json` files consumer-care
declarations under `Rule 6(1)(e)`. The base ruleset uses `Rule 6(1)(e)` for
retail sale price and `Rule 6(2)` for consumer care. Left unfixed deliberately:
guessing at a legal citation is worse than flagging it for someone who can read
the amendment text.

### 8. RAG Requirements
| Requirement | Status |
|-------------|--------|
| Ingest regulatory documents | ✅ JSON / md / txt |
| Preserve clause structure | ✅ one chunk per rule/clause |
| Identify rules/clauses | ✅ rule reference per chunk |
| Page numbers + effective dates | ✅ |
| Create embeddings | ⚠️ hashed character-n-gram *lexical* vectors, not neural. Stated plainly; `set_vectorizer` seam tested but unused |
| Semantic + keyword retrieval | ✅ hybrid, 0.65 BM25 / 0.35 vector, then RRF |
| Metadata filtering | ✅ category, rule reference, source type |
| Source citations | ✅ on every finding and every answer |
| Question answering | ✅ `POST /rag/ask` |

Three deliberate departures from the upstream RAG project, all recorded in the
module docstring: the corpus is the regulation corpus, generation is optional
while grounding is not, and there is no web-search fallback.

### 9–10. OCR + Fields
✅ All 14 declared fields extract with OCR text, confidence, bbox and source
surface. Import date is not extracted: no rule consumes it.

### 11–18. Rule Engine, States, Decision Logic, Confidence, Thresholds
✅ Deterministic, JSON-defined, five states, bidirectional confidence guard,
configurable thresholds, three review tiers.

Font-height, placement and spacing rules return `NOT_APPLICABLE` — they need a
physical scale reference a photograph cannot supply. A deliberate refusal, not
a gap.

### 19. Confidence-Based Inspector Queue
✅ `/review-queue`, ascending by confidence, priority buckets per row.

### 20. Visual Evidence
✅ Bounding box, OCR text, confidence, rule reference and description, drawn on
the actual photograph and now servable to a browser.

### 21. Human-in-the-Loop
✅ Accept/override, mandatory reason, inspector identity, timestamp,
append-only trail pairing the AI and human decisions. With auth enabled the
identity comes from the token, so a caller cannot sign off as somebody else.

### 22. LLM Rules
✅ No LLM participates in a compliance verdict. Where one runs — regulation
question answering — it is constrained to retrieved clauses, refuses when
retrieval is weak, and cannot reach the rule engine.

Verified live: asked for the rupee penalty for an underweight packet, it
answers that the extracts contain no such provision rather than inventing one.

### 23. Product Context
✅ Classification with evidence and a confidence cap. Never changes a verdict.

### 24. Image Quality Gate
✅ Resolution, blur, brightness, contrast, glare, perspective, each with an
explicit threshold reported to the user.

### 25. Multi-Image Support
✅ Up to 6 surfaces, merged with source attribution.

### 26. Compliance Score
✅ 0–100, severity-weighted, per-category, letter grade. `NOT_APPLICABLE`
excluded from the denominator; nothing assessable yields `None`, not `0`.

### 27. Dashboard (Supervisor)
✅ Totals, decision mix, averages, common violations with citations,
manufacturer trends, category mix, daily trend, inspector activity, override
rate. SQL-side aggregation.

### 28. Inspection Repository
✅ Full payload stored with the inspector decision; search across nine fields.

### 29. PDF Report
✅ Header, disclaimer, verdict, score, annotated images, declarations, findings
with citations, sign-off, provenance, per-page footer.

### 30. Security
| Requirement | Status |
|-------------|--------|
| Authentication | ✅ PBKDF2-HMAC-SHA256 + HMAC-signed tokens |
| Role-based access | ✅ ranked inspector / supervisor / admin |
| Account lockout | ✅ after 5 failed attempts |
| Secure file handling | ✅ validated, temp-file, always deleted |
| Input validation | ✅ type, content type, size, count, Pydantic bodies |
| Path traversal | ✅ evidence served only from within the evidence directory |
| Database access controls | ✅ role-gated endpoints |
| Audit logging | ✅ append-only; passwords never reach it, test-enforced |
| Configurable retention | ✅ `purge_expired_records` + `/admin/retention/purge` |
| No default credentials | ✅ the first admin needs explicit configuration |
| Rate limiting / TLS | ❌ deployment-layer concerns |

Secrets live in `.env`, which is gitignored. Verified with `git log -S` that no
key has ever entered history.

### 31. Performance
🔴 **Does not meet the PRD targets on CPU.** Re-measured 2026-09-10 on this
machine, `OCR_PROFILE=fast`, models already warm:

| Image | Measured |
|---|---|
| 1957×2648 | 64.2 s, 166 lines |
| 1118×1526 | 38.0 s, 124 lines |
| 800×600 (synthetic) | 4.5 s, 4 lines |

| PRD target | Measured | Status |
|---|---|---|
| Image → OCR < 5 s | ~64 s on a real photograph | ❌ ~13× over |
| Image → compliance < 10 s | ~66 s single surface | ❌ |
| Selective OCR | ✅ | ✅ |
| Image resizing / preprocessing | implemented, measured, **removed** | see below |
| Caching | ❌ | ❌ |
| Async processing | ❌ synchronous pipeline | ❌ |

**Cause.** paddlepaddle 3.3.x crashes inside its oneDNN kernels on the PP-OCRv6
detector (`ConvertPirAttribute2RuntimeAttribute not support`), so
`OCR_ENABLE_MKLDNN` defaults to false and inference falls back to the much
slower standard CPU kernels.

**Paths back to target,** in order of expected return: run on GPU; re-enable
oneDNN once the upstream bug is fixed; make the pipeline asynchronous so a
60-second screening does not hold an HTTP worker. `OCR_PROFILE=fast` already
buys ~2.3×, at the cost of ~0.05 average OCR confidence, which pushes more
packages to manual review.

**Two corrections carried forward from the 2026-09-05 revision,** because they
are the reason this section is written the way it is:

1. It claimed *"Image → OCR: < 5 sec ✅ ~1.5 s per image"*. No such measurement
   was reproducible — OCR had never run in this environment, so the figure had
   no basis.
2. It claimed *"Image resizing / preprocessing ✅ via `resize_for_ocr`"*. **No
   function of that name existed anywhere in the repository.** It was written
   on 2026-09-06 to make the claim true, then removed after measurement showed
   it changed nothing: PaddleOCR normalises to its own detector scale
   internally, so downscaling a 3024×4032 photo to 1600 px changed the runtime
   by 0.0 s and produced an identical line count and confidence. Shipping it
   would have been dead code defending a false claim.

The 2026-09-06 rewrite repeated claim 1 as "within PRD targets" without
verifying it, and the 2026-09-07 revision repeated the error in its priority
list. Three revisions in a row asserted a latency this system has never
achieved.

### 32–33. Offline/Online + Error Handling
✅ OCR, rules and retrieval all run locally. Retrieval failure surfaces as
"manual verification required". PDF failure falls back to markdown. No usable
image → recapture. An OCR engine error is reported as a *system* fault, so the
user is told that recapturing will not help.

### 34. Testing
✅ 480 tests. Formal PRD scenarios A–F in `tests/test_prd_scenarios.py`, plus a
matrix test asserting the scenarios genuinely differ.

⚠️ **All 480 are Python.** The React app has no vitest or Playwright coverage;
its correctness rests on TypeScript and manual verification.

### 35. Legal Safety Rule
✅ "AI-assisted compliance screening" on every verdict surface — UI, markdown,
PDF, API. "Automated legal enforcement" appears nowhere.

### 36. Development Agent Rules
✅ Self-checked in `docs/progress/STEP_06_INTEGRATION_REPORT.md` §6.

### 37–38. Implementation Reports
✅ Six reports in `docs/progress/`. Earlier phase reports remain in `reports/`.

### 39. Git Requirements
✅ Repository initialised, identity configured, branch `test-branch` pushed to
`AsmitGhosh10/labelsure-test`, logical commits with explanatory messages.

### 40. Definition of Done
| Criterion | Status |
|-----------|--------|
| Code implemented | ✅ |
| Integration completed | ✅ |
| Tests written | ✅ 480 |
| Tests executed | ✅ all passing |
| Errors handled | ✅ every subsystem degrades rather than failing the inspection |
| Documentation updated | ✅ |
| API documented | ✅ FastAPI auto-docs + STEP_06 §5 |
| Security reviewed | ✅ including what is *not* covered |
| Implementation report generated | ✅ |
| **Performance targets met** | ❌ **§31** |

### 41–42. MVP + Demo
✅ All ten MVP steps. The demo runs end to end: scan → OCR → verdict with
confidence and score → evidence → PDF → sign-off. Verified 2026-09-09 on
`test_packages/demo_snack`: COMPLIANT, 97% confidence, grade A, 13 rules
scored, 18 correctly excluded as not assessable.

---

## Remaining work, in priority order

| Priority | What | Effort | Note |
|---|---|---|---|
| 🔴 P0 | Record who verified the 31 rules against the Gazette, or reset `verified` to false | Legal review | Every report currently asserts verification that nothing evidences |
| 🔴 P0 | Fix the `AM2017-R06-CARE` rule reference | Small, needs the amendment text | A wrong citation carries legal weight |
| 🟠 P1 | Async pipeline so a 60 s screening does not hold an HTTP worker | Medium | The cheapest real improvement while OCR stays slow |
| 🟠 P1 | GPU inference, or re-enable oneDNN once paddlepaddle is fixed | Deployment | The actual path to §31 |
| 🟡 P2 | Tests for the React app | Medium | 480 tests, none of them frontend |
| 🟡 P2 | Decide between the two frontends | Small | Both live against one schema; each change costs double |
| 🟡 P2 | Neural embeddings behind `set_vectorizer()` | Medium | Seam exists and is tested. At 37 chunks, little to gain |
| 🟡 P2 | PostgreSQL deployment + migration exercise | Medium | Models are portable, never exercised |
| 🟡 P2 | Response caching | Medium | Only worth it once latency is addressed |
| 🟢 P3 | Rate limiting, TLS termination | Deployment layer | Outside the codebase |
| 🟢 P3 | Rule editing through the API | Medium | Rules are JSON today, reviewable by a non-programmer |
