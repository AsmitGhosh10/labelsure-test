# STEP 06 — Integration, Security & Testing Report

**Date:** 2026-09-06
**PRD sections:** §5 (workflow), §6 (stack), §30 (security), §34 (testing), §36 (agent rules), §40 (definition of done), §41 (MVP)
**Status:** Complete
**Modules:** `main.py`, `auth.py` (319), `routers/*`, `pipeline.py` (552), `tests/*`

---

## 1. End-to-end workflow (PRD §5, §41)

```
capture -> quality gate -> OCR -> field extraction -> evidence merge
        -> commodity classification -> rule evaluation -> confidence fusion
        -> verdict -> compliance score -> regulation citation
        -> visual evidence overlay -> report (markdown + PDF) -> human sign-off
```

All ten MVP steps in §41 are implemented. Steps 5 (retrieve regulations),
9 (visual evidence) and 10 (PDF report) were the outstanding ones and are
covered in STEP_03 and STEP_05.

---

## 2. Response schema: 1.0 → 1.1

The `/inspect` contract was frozen at `labelguard-inspection/1.0` and pinned by
`tests/test_schema_freeze.py`. This work bumped it to **1.1**, deliberately and
additively:

| Added key | PRD |
|---|---|
| `compliance_score` | §26 |
| `product_category` | §23 |
| `regulation_citations` | §8 |
| `annotated_images` | §20 |
| `disclaimer` | §35 |

**No 1.0 key was removed, renamed or retyped**, so every 1.0 consumer keeps
working. Two new tests guard that: `test_v1_0_keys_still_present` and
`test_additions_are_the_only_difference`. The version history is documented in
the freeze test's own docstring, which is where the next person will look.

---

## 3. Security (PRD §30)

| Requirement | Implementation |
|---|---|
| Authentication | PBKDF2-HMAC-SHA256 (240k iterations, per-user salt); HMAC-SHA256 signed bearer tokens |
| Role-based access | `inspector` < `supervisor` < `admin`, ranked so higher roles inherit |
| Secure file handling | Uploads validated by extension + content type + size, written to temp files, deleted in a `finally` |
| Input validation | Image types only; 20 MB cap (configurable); at most 6 surfaces; Pydantic models on every JSON body |
| Database access controls | Supervisor+ for stats and the audit log; admin for user management |
| Audit logging | Append-only `audit_log`: inspections, decisions, logins, failed logins, access denials |
| No sensitive info in logs | Passwords never logged; failed-login audit records the reason, not the attempt |

Deliberate choices worth stating:

- **Zero new dependencies.** Everything uses `hashlib`, `hmac`, `secrets` and
  `base64` from the standard library, used the standard way. No home-grown
  cryptography and no new supply-chain surface.
- **No default credentials, ever.** `bootstrap_admin()` creates the first admin
  only when `AUTH_BOOTSTRAP_USER` *and* `AUTH_BOOTSTRAP_PASSWORD` are both set
  and no user exists. Absent those, no account exists to guess.
- **No hardcoded fallback signing key.** If `AUTH_SECRET_KEY` is unset a random
  key is generated per process — tokens then die at restart, which is
  inconvenient but not forgeable. A constant default would have been a
  token-forgery hole.
- **Identical login failure message** for unknown user and wrong password, so
  the endpoint is not a username oracle.
- **`AUTH_ENABLED=false` by default.** With enforcement off nothing is gated and
  the demo runs unchanged; with it on, protected routes require a valid token
  and decisions are attributed to the token subject, not to the ID in the
  request body (`test_decision_is_attributed_to_the_token_not_the_body`).

CORS is configurable via `CORS_ORIGINS`; `*` remains the dev default so the
local Gradio app works, and credentials are disabled whenever the origin is `*`.

### Not implemented

Rate limiting, account lockout, password rotation policy, TLS termination and
configurable data retention (§30's last line) are not implemented. For a
deployment beyond a demo these belong in front of the app (reverse proxy) or in
a follow-up.

---

## 4. Testing (PRD §34)

`tests/test_prd_scenarios.py` implements Tests A–F as formal fixtures driving
the **real** pipeline with OCR and quality stubbed:

| Test | Scenario | Assertion |
|---|---|---|
| A | Fully compliant package | no FAIL; every mandatory field read; score ≥ 75; verdict never NON_COMPLIANT |
| B | Missing mandatory declaration (MRP) | MRP not extracted; an MRP rule is unresolved; verdict not COMPLIANT; score below A's |
| C | Invalid quantity unit (`7 oz`) | quantity rules do not all pass; verdict not COMPLIANT |
| D | Poor OCR (0.35 confidence) | MANUAL_REVIEW; confidence < 0.70; downgrade explained |
| E | Multiple violations | at least 3 unresolved findings; **every** finding traced to document + rule + page; score < 60 |
| F | Glare / blur, unusable | MANUAL_REVIEW; **zero rules evaluated**; `compliance_score is None`; schema still complete |
| G | OCR engine unavailable | MANUAL_REVIEW, but the reason names a **system fault** and says recapturing will not help — a broken engine must not masquerade as a bad photograph |

`TestScenarioMatrix` asserts the scenarios actually *differ* —
a pipeline that returned the same verdict for every input would otherwise pass
each test in isolation.

Test A and Test F each caught a real production defect on their first run (the
month/year date gap and the OpenCV 5 Hough shape change — see STEP_02 and
STEP_01).

### Suite

**393 tests, all passing, about 10 seconds** (verified on Python 3.12 with the
real OCR stack installed, and on 3.14 without it — every test stubs OCR).

| File | Tests | File | Tests |
|---|---|---|---|
| `test_api.py` | 39 | `test_labelguard_engine.py` | 23 |
| `test_prd_scenarios.py` | 33 | `test_rule_engine.py` | 22 |
| `test_field_extraction.py` | 32 | `test_bottle_regression.py` | 19 |
| `test_frontend.py` | 37 | `test_visual_evidence.py` | 19 |
| `test_hitl.py` | 26 | `test_confidence.py` | 16 |
| `test_auth.py` | 25 | `test_product_category.py` | 16 |
| `test_regulation_retrieval.py` | 25 | `test_multi_image.py` | 14 |
| `test_can_regression.py` | 23 | `test_compliance_score.py` | 12 |
| | | `test_schema_freeze.py` | 8 |

### Real OCR verification (2026-09-06)

Until this date the OCR path had never actually executed: the only interpreter
present was Python 3.14, for which paddlepaddle publishes no wheel. A Python
3.12 environment was created (`.venv312`) and the full stack installed, which
exposed three problems that stubbed tests could not:

1. `requirements.txt` pinned `paddleocr>=2.9,<3` while `ocr_service.py` used
   the **3.x** API. The pin installed 2.10, which has no `predict()`.
2. paddlepaddle 3.3.1 crashes in its oneDNN kernels on the PP-OCRv6 detector.
   Worked around with `enable_mkldnn=False`; paddlepaddle 3.0.0 was tried as an
   alternative and is wholly incompatible with paddleocr 3.7.
3. Real throughput is ~140 s/image, not the ~1.5 s an earlier document claimed
   (see §7.5).

A real end-to-end inspection of `test_images/image2.jpg` now runs: 170 OCR
lines at 0.917 average confidence, verdict NON_COMPLIANT at 85% confidence,
score 62.5/100, with an annotated evidence overlay written.

`tests/conftest.py` redirects `DATABASE_URL` to a temporary SQLite file before
`backend.app.database` is imported, so the suite never writes to the
development database.

---

## 5. API surface

| Method | Path | Role |
|---|---|---|
| POST | `/inspect` | inspector |
| GET | `/inspections`, `/inspections/search`, `/inspections/{id}` | open |
| GET | `/inspections/{id}/report`, `/inspections/{id}/report.pdf` | open |
| POST | `/inspections/{id}/decision` | inspector |
| GET | `/inspections/{id}/decision`, `/inspections/{id}/audit` | inspector |
| GET | `/review-queue` | inspector |
| GET | `/audit-log`, `/stats`, `/stats/violations` | supervisor |
| GET/POST | `/regulations`, `/regulations/search`, `/regulations/{rule_id}` | open |
| POST | `/auth/login`; GET `/auth/status`, `/auth/me` | open |
| GET/POST | `/users` | admin |
| POST | `/assess-quality`, `/ocr`, `/extract-fields`, `/evaluate-rules`; GET `/rules` | open |

Roles apply only when `AUTH_ENABLED=true`.

---

## 6. PRD §36 agent rules — self-check

| Rule | Held? |
|---|---|
| Read existing architecture before modifying | Yes — the schema freeze, evidence pipeline and rule engine were read before any change |
| Never rewrite working modules | Yes — extraction, evidence, rule engine and confidence logic were extended, not replaced |
| Backward compatibility | Yes — 1.1 is additive and guarded by test |
| Modular architecture | Yes — each new capability is its own service module |
| No hardcoded regulations in the frontend | Yes — the frontend reads rule results and citations, never rule text |
| Separate regulatory data from logic | Yes — the ruleset stays JSON |
| Env vars for secrets; never commit keys | Yes — `.env.example` documents them; `.env` is gitignored |
| Never fabricate test results | Yes — every count in these reports is from an actual run |
| Never claim accuracy without testing | Yes — no accuracy claim is made anywhere |
| Never claim a regulation without a source | Yes — every citation carries document, rule and page |
| Reproducible results | Yes — deterministic retrieval, deterministic rules, versioned schema and ruleset |

---

## 7. Remaining gaps (honest list)

1. **Ruleset verification.** `status: DRAFT`, `verified: false`. Every report
   says so. This needs legal review, not code.
2. **Frontend auth.** The API enforces RBAC; the Gradio UI has no login screen,
   so the sign-off form asks the inspector to type their ID.
3. **Neural embeddings.** Retrieval is lexical; the swap seam exists and is
   tested, the model does not.
4. **PostgreSQL.** SQLAlchemy models are portable and `DATABASE_URL` is
   honoured, but the deployment tested here is SQLite.
5. **Performance (§31) — misses the PRD targets on CPU.** Corrected
   2026-09-06 after running real OCR for the first time: ~140 s per image
   against a < 5 s target. The cause is paddlepaddle 3.3.x crashing in its
   oneDNN kernels on the PP-OCRv6 detector, forcing a fallback to the much
   slower standard CPU kernels. `OCR_PROFILE=fast` gives 2.3x for ~0.05 less
   average OCR confidence. Caching and async are still unimplemented on top of
   that. An earlier revision of REMAINING.md claimed ~1.5 s/image; that figure
   was never reproducible and has been retracted.
6. **Operational hardening.** Rate limiting, lockout and retention policy, per
   section 3 above.
7. **Next.js frontend (§6).** The stack table names Next.js + React + Recharts;
   the implementation is Gradio. This was the pre-existing choice and was not
   revisited — the API is framework-agnostic, so a React frontend is additive
   work, not a rewrite.
