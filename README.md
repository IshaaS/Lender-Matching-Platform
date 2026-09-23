# Lender Matching Platform

Underwrites equipment-finance loan applications against multiple lenders' credit policies and
explains, criterion by criterion, who will fund the deal and why. Lender policies are **data,
not code**: every threshold, exclusion and tier is editable in the UI, and new lenders are
onboarded from their guideline PDF.

See [SETUP.md](SETUP.md) for a detailed install walk-
through and [DECISIONS.md](DECISIONS.md) for what was prioritised, simplified, and left for later.

---

## Quick start

Prerequisites: Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 22+ with pnpm, and a
PostgreSQL 14+ you can reach (local, Docker, or hosted — Neon and Supabase URLs paste in as-is).

```bash
make install                  # uv sync + pnpm install
cp .env.example .env          # set DATABASE_URL
make migrate                  # create the schema
make seed                     # load 4 of the 5 lenders' policies + 4 sample applications
make api                      # FastAPI on http://localhost:8000  (docs at /docs)
make web                      # Vite on   http://localhost:5173   (in a second terminal)
```

Open http://localhost:5173, create an application from a sample, submit it, run underwriting.
The 5th lender, **Stearns Bank, is deliberately not seeded** — add it yourself via
**Lenders → Onboard from PDF** on `docs/lender-pdfs/EF Credit Box 4.14.2025.pdf`, which exercises
the real extraction pipeline instead of trusting pre-loaded data.

**PDF ingestion needs a model key — `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` — this is mandatory,
there is no key-less mode.** Without one, "Onboard from PDF" fails with a clear "no model
connected" error rather than faking a result. Everything else (applications, underwriting, the
policy editor) works with no key at all.

**Hatchet is optional.** Set `HATCHET_CLIENT_TOKEN` and run `make worker` to get parallel
fan-out and retries on a real Hatchet queue. Without a token, the exact same underwriting and
ingestion code runs in-process on the API server instead — lenders are evaluated one after
another rather than in parallel, but the result is identical. The UI badge shows which mode ran
(`sync` / `hatchet`).

Tests: `make test-fast` (no database, < 2 s) and `make test` (adds API integration tests against
`DATABASE_URL`). `make lint` runs ruff, mypy `--strict`, tsc and oxlint.

---

## What it does

| Screen | What you can do |
|---|---|
| **Applications** | Create from scratch or from a sample; save drafts; submit; run underwriting; see ranked lenders inline. |
| **Results** | Every lender ranked, eligible by fit score. Open one to see every criterion — required vs. actual — and why it landed on that tier. |
| **Lenders** | View each policy by category. Edit → draft → publish; every rule's field/comparison/value/severity is catalog-driven. |
| **Onboard from PDF** | Upload a guideline PDF → the extractor drafts a policy → a review checklist lists every judgement call → you edit and publish. Nothing goes live unreviewed. |

---

## Architecture

```
frontend/  React + TypeScript + Vite + Tailwind, TanStack Query, react-hook-form + zod
backend/   FastAPI + SQLAlchemy 2 + Alembic on PostgreSQL; Hatchet workflows; Claude / OpenAI extraction
```

```
backend/app/
  engine/        the matching engine — pure Python, no DB/API/workflow imports (test-enforced)
    catalog.py     every fact a rule may test: key, type, unit, options, category
    operators.py   the comparison registry (gte, lte, between, in, not_in, is_true, ...)
    features.py    application -> flat feature set (equipment age, has_paynet, comparable %...)
    policy.py      Policy / Program / Rule documents, validated against the catalog
    evaluator.py   (features, policy) -> eligibility, matched program, criterion outcomes
    scoring.py     fit score 0-100: tier 40 + headroom 40 + preferences 20
  models/        SQLAlchemy tables (applications, versioned policies, runs, results, ingestion)
  services/      the pipelines as plain functions: underwriting, policies, ingestion, extraction
  workflows/     Hatchet wrappers around those functions (+ the worker)
  api/           FastAPI routers; one error shape everywhere
  seeds/         4 of the 5 provided PDFs modelled as data, plus sample applications
```

**Policy model:** `Lender → PolicyVersion (draft|published|archived) → Program[] (ranked) →
Rule[] (field + operator + value + severity: hard|soft)`. Rules can also sit directly on a
lender (checked before any program). Hard rules decline; soft rules only lower the fit score.
`applies_when` makes a rule or program conditional (e.g. Stearns' "No PayNet" table only when
`has_paynet` is false); `any_of` passes when any one alternative does.

**Underwriting:** `validate completeness → derive features → evaluate each lender → rank →
persist`. One set of plain functions (`services/underwriting.py`) is called by both the
in-process runner and the Hatchet workflow, so the two never diverge.

**PDF onboarding:** `upload → extract text → extract policy (model) → validate → draft → human
review → publish`. Two providers (Anthropic, OpenAI) implement the same extractor interface
against one prompt and one schema; every extracted rule is re-validated by the engine's own
`Rule` model, and anything it can't express is dropped to a review checklist instead of guessed.

**Extending it:**

| To add… | Change |
|---|---|
| A new threshold/exclusion for a lender | Nothing in code — **Lenders → Edit → Add rule**, publish. |
| A new lender | **Onboard from PDF**, review, publish — or add manually. |
| A new fact rules can test | One `FieldDef` in `engine/catalog.py` + one line in `engine/features.py`. The rule editor and extractor pick it up automatically. |
| A new kind of comparison | One `register(Operator(...))` in `engine/operators.py`. |

---

## API

Interactive documentation: http://localhost:8000/docs (OpenAPI). Every error has the shape
`{"detail": {"message": "...", "errors": [...]}}`.

| Area | Endpoints |
|---|---|
| Applications | `GET/POST /api/applications`, `GET/PUT/DELETE /api/applications/{id}`, `POST …/submit`, `POST …/duplicate`, `GET …/features`, `GET /api/samples` |
| Underwriting | `POST /api/applications/{id}/runs` (202), `GET /api/applications/{id}/runs`, `GET /api/runs/{id}`, `GET /api/results/{id}` |
| Lender policies | `GET/POST /api/lenders`, `GET/PATCH/DELETE /api/lenders/{id}`, `GET …/versions`, `POST …/draft`, `GET/DELETE /api/policy-versions/{id}`, `POST …/publish`, `POST …/programs`, `POST …/rules`, `PATCH/DELETE /api/programs/{id}`, `PUT/DELETE /api/rules/{id}`, `GET /api/catalog` |
| Onboarding | `POST /api/ingestion` (multipart, 202), `GET /api/ingestion`, `GET /api/ingestion/{id}`, `POST …/retry` |

---

## Configuration

| Variable | Required? | Purpose |
|---|---|---|
| `DATABASE_URL` | **yes** | PostgreSQL. Plain `postgresql://` URLs are accepted. |
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | **yes, for PDF ingestion only** | At least one is required to onboard lenders from a PDF. `EXTRACTION_PROVIDER` picks between them when both are set (`auto` prefers Anthropic). |
| `HATCHET_CLIENT_TOKEN` | no | Enables Hatchet workflows (`make worker`). Without it, underwriting and ingestion run in-process, sequentially. |
| `UNDERWRITING_MODE` | no | `auto` (default) · `hatchet` · `sync` |
| `OPENAI_BASE_URL` | no | Optional OpenAI-compatible endpoint, e.g. Azure. |
| `UPLOADS_DIR` | no | Where uploaded PDFs are stored (default `uploads/`). |

`docker-compose.yml` provides Postgres + hatchet-lite for anyone who prefers containers; see
[SETUP.md](SETUP.md) for the full variable reference and troubleshooting.
