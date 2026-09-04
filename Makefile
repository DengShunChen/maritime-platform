.PHONY: help up down logs build etl qa release-check notices test test-backend test-frontend lint lint-frontend lint-backend ci-local ci-frontend ci-backend ci-compose clean

BACKEND_URL ?= http://localhost:6000
CI_PYTHON ?= .venv311/bin/python

help:
	@echo "Maritime Platform — dev commands"
	@echo ""
	@echo "  make up              Start all services (docker compose)"
	@echo "  make down            Stop services"
	@echo "  make build           Rebuild images"
	@echo "  make etl             Run WRF/GRIB → COG ETL job"
	@echo "  make qa              Smoke-test API (requires running backend)"
	@echo "  make release-check   Run local release gate before delivery"
	@echo "  make notices         Regenerate third-party notices"
	@echo "  make load-test       Concurrent /tiles load test"
	@echo "  make test            Run backend + frontend tests"
	@echo "  make test-backend    pytest unit tests"
	@echo "  make test-frontend   vitest unit tests"
	@echo "  make lint            Lint frontend + backend"
	@echo "  make lint-frontend   ESLint + tsc"
	@echo "  make lint-backend    ruff check (if installed)"
	@echo "  make ci-local        Run local CI checks without Docker"

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

release-check:
	CI_PYTHON=$(CI_PYTHON) python scripts/release_check.py

notices:
	python scripts/generate_third_party_notices.py

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

ci-local: ci-frontend ci-backend ci-compose

ci-frontend:
	cd web-client && npm run lint && npm run typecheck && npm run test:run && npm run build

ci-backend:
	@test -x "$(CI_PYTHON)" || (echo "Missing $(CI_PYTHON). Create it with: python3.11 -m venv .venv311 && $(CI_PYTHON) -m pip install -r backend-service/requirements.txt -r backend-service/requirements-dev.txt" && exit 1)
	$(CI_PYTHON) -m py_compile backend-service/app_v2.py backend-service/etl_bridge.py backend-service/tile_cache.py backend-service/wind_texture.py backend-service/qa_test.py etl/convert_grib2_to_cog.py scripts/release_check.py scripts/generate_third_party_notices.py
	$(CI_PYTHON) -m pytest backend-service/tests -v

ci-compose:
	docker compose config --quiet
	test -f web-client/nginx.conf.template
	grep -q 'proxy_set_header X-API-Key "$${API_KEY}"' web-client/nginx.conf.template
	grep -q 'org.opencontainers.image.revision' backend-service/Dockerfile
	grep -q 'org.opencontainers.image.revision' web-client/Dockerfile
	grep -q '@app.route("/version")' backend-service/app_v2.py

clean:
	docker compose down -v
	rm -rf web-client/dist web-client/node_modules/.tmp
