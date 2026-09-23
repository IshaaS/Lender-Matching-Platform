# Setup guide

Everything needed to run the Lender Matching Platform on a fresh machine. The [README](README.md)
explains what the system does and how it is built; this file is only about getting it running.

Time to first underwriting run: about 10 minutes, most of it dependency installs.

---

## 1. Prerequisites

| Tool | Version | Check | Install |
|---|---|---|---|
| Python | 3.12+ | `python3.12 --version` | https://www.python.org/downloads/ or `brew install python@3.12` |
| uv | any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node | 22+ | `node --version` | https://nodejs.org/ or `brew install node` |
| pnpm | 10+ | `pnpm --version` | `npm install -g pnpm` |
| PostgreSQL | 14+ | see §3 | local install, Docker, or a hosted database (Neon / Supabase) |

Docker is **not** required. `docker-compose.yml` is provided only as a convenience for Postgres
and Hatchet-lite.

---

## 2. Install dependencies

From the repository root:

```bash
make install
```

which runs `uv sync` in `backend/` (creates `backend/.venv`) and `pnpm install` in `frontend/`
(creates `frontend/node_modules`). Both folders are excluded from the shared copy of the repo,
so this step is required after unpacking it.

---

## 3. Database

You need a Postgres connection string. Any of these work:

**Hosted (fastest to start).** Create a free project on https://neon.tech, copy the connection
string (pooled or direct — both work), and use it as-is. Plain `postgresql://` URLs are
accepted; the app adds the driver prefix itself.

**Local.** With a local Postgres running:
```bash
createdb lender_matching
# DATABASE_URL=postgresql://<user>:<password>@localhost:5432/lender_matching
```

**Docker.**
```bash
docker compose up -d db
# DATABASE_URL=postgresql+psycopg://lender_matching:lender_matching@localhost:5433/lender_matching
```

Note on hosted databases: every query is a network round trip (about 230 ms from Europe to
`us-east-2`). The app is fine with that, but the API integration tests take 3–5 minutes instead
of seconds. Use `make test-fast` for day-to-day work.

---

## 4. Configuration

```bash
cp .env.example .env
```

Then edit `.env`. The variables, in order of importance:

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | **yes** | From §3. |
| `UNDERWRITING_MODE` | no | `auto` (default): Hatchet if a token is set, otherwise in-process. `sync` forces in-process. |
| `EXTRACTION_PROVIDER` | for PDF onboarding | `auto` picks Anthropic if its key is set, else OpenAI. Or `anthropic` / `openai`. |
| `OPENAI_API_KEY` | one provider key | For OpenAI or any OpenAI-compatible endpoint. |
| `OPENAI_BASE_URL` | for Azure / proxies | Azure: `https://<resource>.openai.azure.com/openai/v1`. Leave empty for api.openai.com. |
| `OPENAI_EXTRACTION_MODEL` | with Azure | On Azure this is the **deployment name** (e.g. `gpt-5.5`), not the model id. Default `gpt-4.1`. |
| `ANTHROPIC_API_KEY` | one provider key | Direct Anthropic API. Model via `EXTRACTION_MODEL` (default `claude-opus-5`). |
| `HATCHET_CLIENT_TOKEN` | no | Enables the Hatchet workflows (see §7). |
| `UPLOADS_DIR` | no | Where uploaded PDFs are stored. Default `uploads/`. |

There is no key-less PDF ingestion mode. Everything else in the app (applications,
underwriting, the policy editor) works without a model key; only "Onboard from PDF" needs one
— without it, that flow fails with a clear "no model connected" error rather than silently
substituting canned data.

Minimum viable `.env`:

```
DATABASE_URL=postgresql://...
```

---

## 5. Create the schema and load the data

```bash
make migrate   # applies the Alembic migrations (12 application tables + ingestion jobs)
make seed      # loads 4 of the 5 lenders' policies (15 programs, 105 rules) + 4 sample applications
```

Both are idempotent: running them again changes nothing.

The 5th lender, Stearns Bank, is deliberately not seeded — step 4 below onboards it live from
its PDF instead, so the first time it enters the system is via the real extraction pipeline,
not pre-loaded data. See DECISIONS.md ("PDF parsing → lender policies") for why.

---

## 6. Run it

Two terminals:

```bash
make api       # FastAPI on http://localhost:8000 — interactive docs at /docs
make web       # Vite dev server on http://localhost:5173 (proxies /api to :8000)
```

Open http://localhost:5173. The header badge shows API health and which underwriting mode
is active (`sync` or `hatchet`).

Suggested first walk-through:

1. **Applications → New application → "Strong — established contractor"** → *Save & submit*.
2. On the application page, **Run underwriting**. Within a few seconds four lenders are ranked
   (the seeded set — Stearns joins after step 4).
3. **View full results and reasoning** — open Citizens Bank and click the *Tier 1* chip to see
   why it fell to Tier 3 (the $120,000 request exceeds the $75,000 app-only limit).
4. **Lenders → Onboard from PDF**, upload `docs/lender-pdfs/EF Credit Box 4.14.2025.pdf` as a
   new lender named "Stearns Bank". (Needs `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env` —
   see §4.) Review the checklist on the resulting draft — it flags a corp-only table the
   extractor didn't model and a rule it couldn't map to the catalog — then publish it.
5. Back on the application, **Run underwriting** again: five lenders now, Stearns included.
6. **Lenders → Stearns Bank → Edit policy**, change Tier 1's *Minimum FICO*, **Publish**, then
   re-run the application and watch the match change.

---

## 7. Optional: Hatchet

Without a token the underwriting and ingestion pipelines run in-process (same code, same
results). To run them as Hatchet workflows with parallel fan-out and retries:

**Hatchet Cloud.** Create a tenant at https://cloud.onhatchet.run, generate an API token, set
`HATCHET_CLIENT_TOKEN` in `.env`.

**Hatchet-lite in Docker.**
```bash
docker compose up -d          # Postgres + hatchet-lite (dashboard on http://localhost:8888)
make hatchet-token            # prints a token; paste it into .env
```

Then, in a third terminal:

```bash
make worker
```

Restart `make api` after changing `.env`. New runs now show `hatchet` as their mode and appear
in the Hatchet dashboard as a parent run with one child run per lender.

---

## 8. Tests and checks

```bash
make test-fast   # engine, golden lender cases, workflow definitions, extractor tests — ~2 s, no DB
make test        # everything above + API integration tests against DATABASE_URL + frontend tests
make lint        # ruff, mypy --strict, tsc, oxlint
```

The integration tests create and delete their own rows; they never touch seeded data.

---

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `make api` fails with a connection error | `DATABASE_URL` wrong or the database is unreachable. `psql "$DATABASE_URL"` should connect. |
| Header badge says **API unreachable** | The API is not running on :8000, or it crashed on startup — check its terminal. |
| `alembic upgrade` complains about existing tables | The database already has the schema; run `make migrate` once only, or use a fresh database. |
| Onboard from PDF fails with *No model is connected for PDF parsing* | Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, then restart `make api`. There is no key-less mode — see §4. |
| Azure returns `DeploymentNotFound` | `OPENAI_EXTRACTION_MODEL` must be a deployment that exists on the resource. List them: `curl "https://<resource>.openai.azure.com/openai/deployments?api-version=2023-03-15-preview" -H "api-key: $OPENAI_API_KEY"`. |
| Azure returns 401 | The key is for a different resource, or `OPENAI_BASE_URL` is missing so the call went to api.openai.com. |
| Changing `.env` has no effect | Settings are read once at startup; restart `make api` (and `make worker`). |
| Integration tests are slow | Expected against a remote database. Use `make test-fast` unless you changed the API. |
| Underwriting runs show `sync` although Hatchet is configured | The API could not reach Hatchet when the run started and fell back to in-process; check the API log and that `make worker` is running. |

---

## 10. Where things live

```
README.md          what it is, architecture, API, extension points
DECISIONS.md       requirements prioritised, assumptions per lender, simplifications, next steps
SETUP.md           this file
docs/              the 5 provided lender guideline PDFs
backend/           FastAPI app  (app/engine is the matching engine; app/seeds the modelled PDFs)
frontend/          React app
docker-compose.yml optional Postgres + Hatchet-lite
Makefile           every command used above
```
