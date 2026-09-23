.PHONY: install test-fast infra infra-down api worker web migrate seed test lint hatchet-token dev

install:          ## Backend (uv) + frontend (pnpm) dependencies
	cd backend && uv sync
	cd frontend && pnpm install

infra:            ## Postgres + Hatchet-lite
	docker compose up -d

infra-down:
	docker compose down

migrate:          ## Apply database migrations
	cd backend && uv run alembic upgrade head

seed:             ## Load 4 of the 5 lender policies + sample applications (onboard the 5th, Stearns, from its PDF)
	cd backend && uv run python -m app.seeds

api:              ## FastAPI on :8000
	cd backend && uv run uvicorn app.main:app --reload --port 8000

worker:           ## Hatchet worker
	cd backend && uv run python -m app.workflows.worker

web:              ## Vite dev server on :5173
	cd frontend && pnpm dev

test-fast:        ## Engine + golden tests only (no database, <1s)
	cd backend && uv run pytest -q -m "not integration"

test:
	cd backend && uv run pytest -q
	cd frontend && pnpm test --run

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd frontend && pnpm lint && pnpm exec tsc -b

hatchet-token:    ## Print an API token for the local Hatchet tenant
	@docker compose exec hatchet /hatchet-admin token create --config /config --tenant-id 707d0855-80ab-4e1f-a156-f1c4546cbf52
