# Project Overview

**LabelSure** screens photographs of packaged commodities against the Indian
Legal Metrology (Packaged Commodities) Rules, 2011, and hands a human inspector
a verdict with its evidence, its confidence and the clause it cites.

**Last updated:** 2026-09-10 · **Suite:** 499 tests passing ·
**Response schema:** `labelguard-inspection/1.1`

---

## What problem it solves

A Legal Metrology officer inspecting packaged goods must check each package for
a set of mandatory declarations: retail sale price, net quantity, manufacturer
identity, month and year of manufacture, consumer care details, country of
origin. Doing this by eye, at shelf scale, is slow and inconsistent.

LabelSure narrows the field. It reads the declarations off photographs, applies
the rules deterministically, and produces a prioritised queue so an inspector's
attention lands on the packages the system was least sure about.

## What it deliberately does not do

The constraints are the product. A screening tool that overstates its authority
is worse than no tool, because a wrong verdict carries statutory weight.

- **No model decides compliance.** Rules are data evaluated by a deterministic
  engine. The same package and the same photographs always produce the same
  finding.
- **No generated regulation text.** Citations are retrieved verbatim from an
  indexed corpus, with document, rule reference and page number. Nothing is
  paraphrased.
- **No silent guessing.** A stage that cannot do its job says so. No usable
  image, no readable text, no matching clause — each surfaces as "manual
  verification required" rather than a confident-looking default.
- **No autonomous finding.** Every verdict waits for an inspector to accept,
  override or escalate it, and that decision is written to an audit log.

Every surface that shows a verdict carries the same wording: this is
AI-assisted compliance screening, not a statutory inspection.

---

## How an inspection runs

```
photographs ──▶ quality gate ──▶ OCR ──▶ field extraction ──▶ rule engine
                                                                   │
        inspector sign-off ◀── confidence fusion ◀── citation ◀─────┘
```

**1. Quality gate.** Each surface is scored on blur, brightness, contrast,
glare and perspective against explicit thresholds. A frame that fails is
rejected before it can produce a false verdict, and the reason names the
measurement so the officer knows how to recapture.

**2. OCR.** PaddleOCR lifts every text line with its confidence and its
bounding polygon. A surface whose OCR engine errors is reported as a *system*
fault, distinct from a bad photograph, because recapturing will not help.

**3. Field extraction.** Regex and heuristic extractors resolve the declaration
values, each carrying the raw text it came from, a confidence and a position.
Up to six surfaces are merged into one view of the package.

**4. Rule engine.** 31 rules evaluate to `PASS`, `FAIL`, `MANUAL_REVIEW`,
`NOT_APPLICABLE` or `UNVERIFIED`. Rules that cannot be judged from photographs —
standard pack sizes, sticker tampering, component structure — return
`NOT_APPLICABLE` with the reason, and are excluded from the score rather than
counted as passes.

**5. Confidence fusion.** Image quality, OCR confidence, extraction confidence
and rule applicability combine into one figure. The engine will downgrade its
own verdict when the evidence does not support the stronger one.

**6. Citation.** Each finding is paired with the clause it rests on: document,
rule reference, page, verbatim quote.

**7. Sign-off.** The inspector accepts or overrides, with a mandatory reason. An
override must name the decision that replaces the automated one.

---

## Regulation question answering

Beyond screening, the system answers plain-English questions about the rules at
`POST /rag/ask`: hybrid retrieval, Reciprocal Rank Fusion over the keyword and
vector views, an optional cross-encoder rerank, then generation.

Adapted from the RAG project in `rag/Multimodal_RAG_Project-main`, with three
changes:

| Upstream | Here | Why |
|---|---|---|
| Postgres + FAISS ingestion of arbitrary uploads | The existing regulation corpus | No second index, no ingestion step |
| Groq generation required | Generation optional, extraction always available | Works with no key; quotes clauses verbatim instead |
| Tavily web-search fallback on low confidence | Refusal | Answering a statutory question from an arbitrary web page is the failure this project exists to prevent |

An intent classifier sits ahead of retrieval, so a greeting gets guidance
rather than a page of statutory refusal, and a question about the tool is not
answered with whatever clauses happened to rank highest. It is conservative:
only input that is *entirely* smalltalk is diverted, so "hey what is the rule
for net quantity" still reaches the corpus.

---

## Interfaces

Two frontends, one API.

| | React app (`web/`) | Gradio app (`frontend/app.py`) |
|---|---|---|
| Stack | Vite, TypeScript, Tailwind, shadcn/ui | Python, Gradio |
| Port | 5174 | 7860 |
| Purpose | The product surface | The original prototype |

Both call the same FastAPI backend, so the response schema is the contract
between them.

**Routes in the React app:** landing, inspect, inspection detail, ask,
regulations, review queue, dashboard.

---

## Roles

| Role | Can do |
|---|---|
| Inspector | Run screenings, sign off on findings |
| Supervisor | Everything above, plus repository statistics |
| Admin | Everything above, plus user management and retention purges |

Roles are ranked, so a higher role inherits the lower permissions. With
authentication enabled, a sign-off is attributed to the token's subject and any
`inspector_id` in the request body is ignored — a caller cannot sign off as
somebody else. No default account exists to guess; the first admin is created
from explicit environment configuration.

---

## Scale of the codebase

| Part | Lines |
|---|---|
| Backend (`backend/`) | ~9,900 |
| React app, excluding generated components | ~3,200 |
| Gradio app | ~1,000 |
| Tests | ~5,400 |

19 service modules, 32 HTTP endpoints, 37 indexed regulation chunks across 4
documents, all carrying page references.

---

## Where things stand

Everything the PRD asks for is built except the latency targets. Screening a
full-resolution photograph takes roughly 60 seconds against a 5-second target,
because a bug in paddlepaddle's oneDNN kernels forces inference onto the slower
standard path. See [REMAINING.md](REMAINING.md) for the full accounting.

## Further reading

- [README.md](README.md) — how to run it
- [TECH_STACK.md](TECH_STACK.md) — what it is built from and why
- [REMAINING.md](REMAINING.md) — what is built, what is not, measured
- [web/README.md](web/README.md) — the React frontend
- [prd.md](prd.md) — the original requirements
