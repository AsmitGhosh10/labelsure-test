# LabelSure web frontend

React + Vite + TypeScript + Tailwind v4 + [shadcn/ui](https://ui.shadcn.com),
talking to the FastAPI compliance backend.

## Running it

The frontend needs the backend. Start the API first, from the repository root:

```bash
.venv312/Scripts/python.exe -m uvicorn backend.app.main:app --port 8000
```

Then, in `web/`:

```bash
npm install
npm run dev
```

The app serves on <http://localhost:5174>. Every request goes to `/api/*`, which
Vite proxies to `http://127.0.0.1:8000`. That keeps the browser on a single
origin, so no CORS configuration is needed locally and no cross-origin token
handling is involved. Point the proxy elsewhere with `VITE_API_TARGET`.

In production, serve `dist/` statically and route `/api` to the backend with the
same prefix-stripping rule the dev proxy uses.

## Pages

| Route               | What it is                                                        |
| ------------------- | ----------------------------------------------------------------- |
| `/`                 | Landing page: what the system does, and what it refuses to do      |
| `/inspect`          | Upload or photograph up to six surfaces and run a screening        |
| `/inspections/:id`  | A stored screening, with evidence and sign-off                     |
| `/ask`              | Regulation question answering (RAG) with citations                 |
| `/regulations`      | Keyword and lexical-vector search over the regulation corpus       |
| `/queue`            | The sign-off backlog, least confident first                        |
| `/dashboard`        | Repository statistics (supervisor role)                            |

## Camera capture

The inspect page can photograph a surface directly with `getUserMedia` and a
canvas, no dependency. Two details are load-bearing:

- **The stream stops on every exit path.** A camera left running keeps the
  hardware indicator lit, which reads as spyware.
- **Capture asks for the highest resolution the device offers.** The
  declarations being read are small print, and a 640x480 frame produces OCR
  failures that surface as compliance findings.

`getUserMedia` needs a secure context. It works on `localhost`; over plain HTTP
on any other hostname the API is absent and the dialog says so rather than
failing with a bare `TypeError`.

## Authentication

Sign-in appears in the header only when `GET /auth/status` reports auth enabled.
The token is held in `sessionStorage` and sent as a bearer token. When
authentication is on, the backend attributes a sign-off to the token's subject
and ignores any `inspector_id` in the request body, so a caller cannot sign off
as somebody else.

## Conventions

Components come from shadcn/ui and live in `src/components/ui`. Colours use
semantic tokens (`bg-background`, `text-muted-foreground`), never raw palette
values, so light and dark both work from one definition.

Two rules are load-bearing rather than cosmetic:

- **A missing measurement is never rendered as zero.** "Not assessed" and
  "assessed as zero" are different findings in a compliance report, so `null`
  renders as "not assessed" or "not found".
- **Verdict state is never carried by colour alone.** Each verdict and rule
  status also has its own icon and its own words.

Watch the units when adding a metric: the backend reports confidence as a 0-1
fraction, and compliance rate and compliance score already on a 0-100 scale.
