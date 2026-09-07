# STEP 03 — Regulatory Retrieval (RAG) Report

**Date:** 2026-09-06
**PRD sections:** §7 (regulatory knowledge base), §8 (RAG requirements), §33 (error handling), §42 (demo)
**Status:** Implemented as a self-contained retrieval subsystem
**Module:** `backend/app/services/regulation_retrieval.py` (488 lines), `backend/app/routers/regulations.py`

---

## 1. Scope decision — read this first

PRD §8 asks to *"integrate the existing Multimodal RAG project"*. That project is
not present in this repository: `rag/Multimodal_RAG_Project/` exists but is
**empty**. There was nothing to adapt.

Rather than report the section as blocked, this step implements the *capability*
§8 actually specifies — ingest regulation documents, preserve clause structure
and page numbers, retrieve semantically and by keyword, filter by metadata,
return source citations — as a self-contained subsystem over the corpus the
project already owns, with an explicit seam for a richer backend.

**What is honestly true about it:**

- Retrieval is **hybrid BM25 + hashed character-n-gram cosine similarity**.
- The n-gram vectors are **lexical**, not learned neural embeddings. They
  tolerate OCR noise and morphology; they do not understand meaning. The
  docstring and `stats()["vectorizer"]` say so.
- `RegulationRetriever.set_vectorizer()` is the swap point: hand it a sentence-
  embedding function and the same hybrid scoring runs over real embeddings, no
  caller changes. `tests/test_regulation_retrieval.py::TestVectorizerSeam`
  exercises that seam.
- It is not multimodal. It retrieves text clauses.

---

## 2. Corpus (PRD §7)

Primary source: `backend/app/rules/labelguard_rules_draft.json` — 31 rules
extracted from the Gazette scan of the Legal Metrology (Packaged Commodities)
Rules, 2011. Each rule already carries what a citation needs:

| Field | Coverage |
|---|---|
| `source.document` | 31/31 |
| `source.rule_reference` | 31/31 |
| `source.source_pdf_page` | 31/31 |
| `source.evidence_text` (verbatim quote) | 31/31 |
| `publication_date` (effective date) | 2011-03-07 |

`tests/test_regulation_retrieval.py::test_every_chunk_carries_a_citable_source`
enforces this — a rule that cannot be cited cannot enter the corpus.

Supplementary documents (amendments, notifications) are ingested from
`backend/app/rules/corpus/`:

- `.json` — a `{document, effective_date, url, clauses: [...]}` envelope; each
  clause keeps its own rule reference, page and effective date.
- `.md` / `.txt` — split on blank lines into clauses, with `[p. N]` markers
  preserved as page numbers and leading `Rule N` captured as the reference.

The directory is optional. Its absence is not an error; a missing ruleset file
degrades retrieval to empty results rather than crashing.

---

## 3. Retrieval

```
score = 0.65 × BM25(normalised) + 0.35 × cosine(n-gram vectors)
```

Keyword dominates deliberately: statutory wording ("retail sale price
inclusive of all taxes") must retrieve exactly, and a fuzzy vector must not
outvote a literal clause match.

Determinism matters for reproducibility (PRD §36), so the vectors hash with
`blake2b`, never Python's randomised `hash()`. Two independent retriever
instances rank identically — asserted by
`test_retrieval_is_deterministic`.

Metadata filters: `category`, `rule_reference`, `source_type`.

### Citations attached to findings

`cite_findings()` runs after rule evaluation and attaches sources to **FAIL and
MANUAL_REVIEW findings only** — those are the ones an inspector must justify.
Exact rule-id lookup is preferred (`retrieval: "exact_rule_id"`); hybrid search
is the fallback for findings whose rule is not in the corpus.

The result reaches the API response as `regulation_citations`, the markdown
report as "Regulatory Sources", the PDF as a quoted clause under each finding,
and the UI as the "Regulatory Sources" tab.

---

## 4. Failure handling (PRD §33)

A retrieval miss returns `retrieval: "no_match"` with
`note: "No regulation text retrieved - manual verification required"`. This is
the point of the whole section: an empty retrieval must never be presented as
"no rule applies". Asserted by `test_no_match_says_manual_verification_required`.

Retrieval failure inside the pipeline is caught and converted into exactly that
message; an inspection never fails because retrieval did.

---

## 5. API

| Endpoint | Purpose |
|---|---|
| `GET /regulations` | corpus stats: chunk count, documents, page coverage, load errors |
| `GET /regulations/search?q=…&top_k=&category=&rule_reference=` | ranked citations |
| `POST /regulations/search` | same, JSON body |
| `GET /regulations/{rule_id}` | exact citation lookup |

---

## 6. Tests

`tests/test_regulation_retrieval.py` — 25 tests: corpus completeness, citation
metadata, ranking order, metadata filters, determinism, OCR-noise tolerance,
amendment/text ingestion, missing-corpus degradation, the vectorizer seam, and
the manual-verification fallback.

---

## 7. Known limitations

- Lexical retrieval only (see §1). A query using entirely different vocabulary
  from the statute will under-retrieve.
- The corpus is one document plus whatever is dropped into `corpus/`. No PDF
  parsing is built in: converting a new Gazette PDF to clauses is a manual or
  scripted step producing the JSON envelope.
- The ruleset is marked `verified: false` / `status: DRAFT` upstream, and every
  report says so. Retrieval faithfully propagates that status; it does not
  launder a draft into an authority.
