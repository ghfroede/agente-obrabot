.PHONY: dev dev-api dev-worker build start-api start-worker test lint typecheck db-migrate install sync smoke-s3 smoke-api smoke-openclaw smoke-prod smoke-prod-railway

PROD_API_URL ?= https://api-production-8bfb.up.railway.app

UV ?= uv

install sync:
	$(UV) sync

dev-api:
	$(UV) run uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload

dev-worker:
	$(UV) run python -m src.worker.index

dev:
	@echo "Execute 'make dev-api' e 'make dev-worker' em terminais separados"

build:
	$(UV) sync --frozen --no-dev

start-api:
	$(UV) run uvicorn src.api.server:app --host 0.0.0.0 --port $${PORT:-8000}

start-worker:
	$(UV) run python -m src.worker.index

test:
	$(UV) run pytest -q

lint:
	$(UV) run ruff check src tests

typecheck:
	$(UV) run mypy src

db-migrate:
	$(UV) run alembic upgrade head

smoke-s3:
	PYTHONPATH=. $(UV) run python scripts/smoke_s3.py

smoke-api:
	$(UV) run python scripts/smoke_api.py $(BASE_URL)

smoke-openclaw:
	$(UV) run python scripts/smoke_openclaw.py $(or $(BASE_URL),$(PROD_API_URL))

smoke-prod:
	$(UV) run python scripts/smoke_prod.py

smoke-prod-railway:
	railway run --service api $(UV) run python scripts/smoke_prod.py
