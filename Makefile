.PHONY: help up down logs build etl qa test test-backend test-frontend lint lint-frontend lint-backend clean

BACKEND_URL ?= http://localhost:6000

help:
	@echo "Maritime Platform — dev commands"
	@echo ""
	@echo "  make up              Start all services (docker compose)"
	@echo "  make down            Stop services"
	@echo "  make build           Rebuild images"
	@echo "  make etl             Run WRF/GRIB → COG ETL job"
	@echo "  make qa              Smoke-test API (requires running backend)"
	@echo "  make load-test       Concurrent /tiles load test"
	@echo "  make test            Run backend + frontend tests"
	@echo "  make test-backend    pytest unit tests"
	@echo "  make test-frontend   vitest unit tests"
	@echo "  make lint            Lint frontend + backend"
	@echo "  make lint-frontend   ESLint + tsc"
	@echo "  make lint-backend    ruff check (if installed)"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

etl:
	docker compose --profile etl run --rm etl-service

etl-file:
	@test -n "$(FILE)" || (echo "Usage: make etl-file FILE=wrfout_d01_..." && exit 1)
	docker compose --profile etl run --rm etl-service python3 convert_grib2_to_cog.py --file "/data/$(FILE)" --cog-root /cog

qa:
	BACKEND_URL=$(BACKEND_URL) python backend-service/qa_test.py

load-test:
	BACKEND_URL=$(BACKEND_URL) python backend-service/scripts/load_test_tiles.py --warmup 6 -c 20 -n 50

restart-backend:
	docker compose restart backend-service

test-e2e:
	cd web-client && npx playwright install chromium --with-deps 2>/dev/null || true
	cd web-client && PLAYWRIGHT_BASE_URL=$(BACKEND_URL) npm run test:e2e

test: test-backend test-frontend

test-backend:
	cd backend-service && pytest tests/ -v

test-frontend:
	cd web-client && npm run test:run

lint: lint-frontend lint-backend

lint-frontend:
	cd web-client && npm run lint && npm run typecheck

lint-backend:
	@command -v ruff >/dev/null 2>&1 && cd backend-service && ruff check . || echo "ruff not installed — skip"

clean:
	docker compose down -v
	rm -rf web-client/dist web-client/node_modules/.tmp
