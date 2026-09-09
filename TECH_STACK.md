# Tech Stack

What LabelSure is built from, and why each piece was chosen. Versions are those
actually resolved in the working environment on 2026-09-10, not the range in the
manifest.

---

## Backend

| Layer | Technology | Version | Why |
|---|---|---|---|
| Language | Python | 3.12.13 | paddlepaddle has no wheel for 3.13+ |
| API | FastAPI | 0.141.1 | Typed request bodies, generated OpenAPI |
| Validation | Pydantic | 2.13.5 | Request validation is a trust boundary |
| ORM | SQLAlchemy | 2.0.52 | Portable DSN; SQLite locally, Neon Postgres in deployment |
| Postgres driver | psycopg | 3.3.5 | Optional; only when `DATABASE_URL` is Postgres |
| OCR | PaddleOCR | 3.7.0 | Strongest open CPU OCR for dense label text |
| Inference | paddlepaddle | 3.3.1 | PaddleOCR's runtime |
| Imaging | OpenCV | 4.10.0 | Quality-gate measurements |
| Imaging | Pillow | 12.3.0 | Evidence overlays |
| Arrays | NumPy | 2.5.3 | Transitive, and used for bounding-box maths |
| PDF | ReportLab | 5.0.1 | Inspection reports |
| LLM | groq | 1.7.0 | Optional answer generation |
| Config | python-dotenv | 1.x | Optional `.env` loading |

### Notable absences

**No LLM in the verdict path.** The rule engine is plain Python over a JSON
ruleset. This is a constraint from the requirements, not an implementation gap:
nothing in a compliance verdict may be generated.

**No vector database.** Regulation retrieval uses BM25 plus hashed character
n-gram cosine similarity, both in the standard library. These are *lexical*
vectors, not learned embeddings — nothing here understands meaning, it matches
surface form robustly enough to survive OCR noise and morphology. The seam for
a real embedding backend is `RegulationRetriever.set_vectorizer`, and it is
tested, but unused. At 37 chunks a vector database would be infrastructure for
nothing.

**No authentication library.** Passwords use PBKDF2-HMAC-SHA256 and tokens are
HMAC-SHA256 signed, both from `hashlib` and `hmac`. A JWT library would add a
dependency and a CVE feed for what fits in one module.

**No task queue.** The pipeline is synchronous. This is a real limitation at
current OCR latency, recorded in [REMAINING.md](REMAINING.md) rather than
papered over.

---

## Frontend

Two of them, sharing one API.

### React app — `web/`

| Layer | Technology | Version |
|---|---|---|
| Framework | React | 19.2.8 |
| Build | Vite | 8.2.2 |
| Language | TypeScript | 6.0.2 |
| Styling | Tailwind CSS | 4.3.3 |
| Components | shadcn/ui on Radix | radix-ui 1.6.7 |
| Routing | React Router | 7.18.3 |
| Icons | lucide-react | 1.43.0 |
| Toasts | sonner | 2.0.8 |
| Linting | oxlint | 1.79.0 |

**Why Vite rather than Next.js.** The requirements named Next.js. Nothing here
needs server rendering: the app is an authenticated internal tool behind a
login, with no SEO surface and no server-rendered content. Vite is a smaller
thing to own. The backend is framework-agnostic, so this is reversible.

**Why shadcn/ui.** Components are copied into the repository as source rather
than imported from a package, so they can be read and changed without fighting
a library's abstractions. Radix underneath supplies the accessibility
behaviour — focus management, keyboard navigation, ARIA wiring — that is
tedious to get right and dangerous to get wrong.

**No state management library.** React hooks and props. There is no shared
client state worth a store.

**No charting library.** The one chart is a bar strip of plain divs. A charting
dependency for a single series of one metric is not worth its weight; swap it
when a second series appears.

**No API client library.** One `fetch` wrapper, about 170 lines, in
`web/src/lib/api.ts`.

### Gradio app — `frontend/app.py`

Gradio 6.26.0. The original prototype, still functional against the same API.
Kept because it works and costs nothing to leave alone, but it is a second
surface to keep in step whenever the response schema moves.

---

## Data

| Concern | Choice |
|---|---|
| Inspection repository | SQLite by default; Neon serverless Postgres via `DATABASE_URL` |
| Ruleset | JSON, 31 rules, each with severity, category and source |
| Regulation corpus | JSON per document, 37 chunks, every one page-referenced |
| Audit log | Append-only table |
| Evidence images | Files under `reports/inspections/evidence` |

The ruleset being data rather than code is the point. A rule change is a JSON
edit reviewable by someone who knows the regulation but not Python.

---

## Retrieval and generation

```
query ──▶ BM25 ─────────┐
      └─▶ n-gram cosine ─┴─▶ RRF fusion ─▶ cross-encoder rerank ─▶ Groq
                                              (optional)          (optional)
```

Both optional stages degrade to the deterministic path when absent, so the
service works on a bare install. `GET /rag` reports which are actually live.

**Generation model.** `openai/gpt-oss-20b` on Groq by default. Model
availability varies by account — the Llama models are not on every key — so the
default is what this project's key can actually reach. Reasoning models bill
their thinking against `max_tokens`, so `reasoning_effort` is set low.

---

## Tooling

| Purpose | Tool |
|---|---|
| Python environment | `uv`, pinned to 3.12 in `.venv312` |
| Tests | pytest, 499 tests |
| Frontend package manager | npm |
| Version control | git |

---

## Dependency policy

Two rules, applied throughout:

1. **The standard library first.** Authentication, retrieval scoring and rank
   fusion are all stdlib. Each avoided dependency is one fewer thing to patch.
2. **Optional heavy things stay optional.** groq, sentence-transformers and
   python-dotenv are all guarded imports. A bare `pip install -r
   requirements.txt` produces a working system; the extras improve it.

The exception is OCR, where PaddleOCR and its runtime are load-bearing and
large. That is the cost of reading real photographs of real packages.
