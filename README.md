# LabelSure

AI-assisted screening of packaged-commodity labels against the Indian Legal
Metrology (Packaged Commodities) Rules, 2011.

Photograph a package. The pipeline gates image quality, reads the text, resolves
the declarations, applies 31 statutory rules deterministically, and hands an
inspector a verdict with its evidence, its confidence and the clause it cites.

**This is a decision-support aid, not a statutory inspection.** It carries no
legal finding of contravention, and every finding must be verified by an
authorised inspector before any action is taken.

## Running it

Two processes: the FastAPI backend and the React frontend.

```bash
.venv312/Scripts/python.exe -m uvicorn backend.app.main:app --port 8000
```

```bash
npm install --prefix web && npm run dev --prefix web
```

The app is then at <http://localhost:5174>. The frontend proxies `/api/*` to the
backend, so both run on one origin locally.

A Gradio frontend also exists at `frontend/app.py` and talks to the same API.

## What is where

| Path                            | What it holds                                              |
| ------------------------------- | ---------------------------------------------------------- |
| `backend/app/routers`           | HTTP surface: inspection, review, dashboard, regulations, RAG, auth |
| `backend/app/services`          | Quality gate, OCR, field extraction, rule engine, scoring, retrieval, RAG |
| `backend/app/rules`             | The machine-readable ruleset and the regulation corpus     |
| `web/`                          | React + shadcn/ui frontend (see `web/README.md`)            |
| `frontend/app.py`               | The original Gradio frontend                               |
| `tests/`                        | The test suite                                             |
| `rag/Multimodal_RAG_Project-main` | The upstream RAG project this system's RAG was adapted from |

## Regulation question answering

`POST /rag/ask` answers a plain-English question from the indexed regulation
corpus and returns the clauses behind the answer. The pipeline is hybrid
retrieval, then Reciprocal Rank Fusion over its keyword and vector views, then
an optional cross-encoder rerank, then generation.

Two things about it are deliberate:

- **Generation is optional; grounding is not.** With `GROQ_API_KEY` set, the
  answer is written by a Groq model constrained to the retrieved clauses.
  Without it, the service answers extractively by quoting those clauses
  verbatim. Either way, weak retrieval produces a refusal rather than an answer.
- **There is no web-search fallback.** The upstream project reached for a web
  search when internal confidence was low. Answering a statutory question from
  an arbitrary web page is the failure this system exists to avoid.

Configure it in `.env` (gitignored) or as plain environment variables:

```bash
GROQ_API_KEY=...                  # generated answers instead of verbatim extracts
GROQ_MODEL=openai/gpt-oss-20b     # the default
GROQ_REASONING_EFFORT=low         # reasoning models bill thinking against max_tokens
RAG_MIN_GROUNDING_SCORE=0.08      # retrieval score below which it refuses to answer
pip install sentence-transformers # enables cross-encoder reranking
```

Check what is actually live with `GET /rag`. It reports the generator, the
model and `generation_error`, which names the reason for any fallback to
extractive answers. A wrong model name is otherwise indistinguishable from no
key at all.

Model availability varies by Groq account. List what a key can reach with
`client.models.list()`; not every account has the Llama models.

## Configuration

| Variable                   | Effect                                               |
| -------------------------- | ---------------------------------------------------- |
| `AUTH_ENABLED`             | Turns on authentication and role gating              |
| `AUTH_SECRET_KEY`          | Token signing key; required when auth is enabled     |
| `AUTH_BOOTSTRAP_USER/PASSWORD` | Creates the first admin. No default account exists |
| `CORS_ORIGINS`             | Comma-separated allow-list; set this in production   |
| `MAX_UPLOAD_BYTES`         | Per-image upload cap, 20 MB by default               |
| `OCR_PROFILE`              | `fast` or `accurate` OCR models                      |
| `DATABASE_URL`             | Inspection repository, SQLite by default             |

## Database

SQLite by default, no configuration needed. For Postgres, including serverless
Postgres such as Neon, set a DSN and install the driver:

```bash
pip install "psycopg[binary]"
```

```bash
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

The schema is created on first start; there is no migration step. Use the
provider's *pooled* host when it offers one.

Serverless Postgres suspends an idle compute and drops its connections, so a
pooled connection handed out afterwards is dead and the first query on it
raises instead of reconnecting. The engine therefore sets `pool_pre_ping` and a
300-second `pool_recycle` for every non-SQLite DSN. Without those, the first
request after an idle period fails.

The test suite always redirects `DATABASE_URL` to a temporary SQLite file, so
running it never touches a configured Postgres database.

## Tests

```bash
.venv312/Scripts/python.exe -m pytest -q
```

## Documentation

| Document | What it covers |
| -------- | -------------- |
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | What the system does, how an inspection runs, what it refuses to do |
| [TECH_STACK.md](TECH_STACK.md) | What it is built from, and why each choice was made |
| [REMAINING.md](REMAINING.md) | Every requirement mapped to built or not-built, measured |
| [web/README.md](web/README.md) | The React frontend |
| [prd.md](prd.md) | The original requirements |
