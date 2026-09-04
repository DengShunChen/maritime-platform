# Operations Runbook

This runbook is the minimum operating procedure for delivering Maritime Platform as a customer-facing product on a MacBook Pro M2, Docker host, or small single-node server.

## Release Readiness

Run the local release gate before handing a build to a customer or publishing an image:

```bash
BUILD_VERSION=v1.2.0 \
BUILD_SHA=$(git rev-parse --short HEAD) \
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
make release-check
```

The gate must pass all checks:

- frontend lint, typecheck, tests, and production build
- backend Python compile and pytest contract tests
- Docker Compose config validation
- Nginx server-side API key injection validation
- ignored `.env`, frontend `.env`, and large WRF data files
- `.env.example` deployment key coverage
- real WRF `/ready`, `/version`, and `/metrics` smoke checks

Do not ship a release if any gate fails.

## Deployment

1. Copy `.env.example` to `.env`.
2. Set `VITE_MAPTILER_API_KEY`.
3. Set `API_KEY` for customer or demo environments.
4. Set `BUILD_VERSION`, `BUILD_SHA`, and `BUILD_DATE` for traceability.
5. Place WRF/NetCDF/GRIB files under `data/`.
6. Start services with `make up` or `docker compose up -d`.
7. Confirm readiness with `curl http://localhost:6000/ready`.
8. Confirm browser access at `http://localhost/`.

## Monitoring

Check liveness:

```bash
curl http://localhost:6000/health
```

Check data readiness:

```bash
curl http://localhost:6000/ready
```

Check release identity:

```bash
curl http://localhost:6000/version
```

Scrape metrics:

```bash
curl http://localhost:6000/metrics
```

Recommended customer-site alerts:

- `/ready` is not HTTP 200 for more than 3 minutes
- request 5xx rate exceeds 1 percent over 5 minutes
- rate limit rejects are sustained for more than 10 minutes
- tile cache hit rate drops unexpectedly after warmup
- disk usage for `data/` or `cog_data/` exceeds 80 percent

## Data Operations

Accepted forecast input files must stay inside `NETCDF_DATA_DIR`, normally `data/`.

After new WRF output arrives:

1. Copy the file into `data/`.
2. Use the UI dataset selector or API to select it.
3. If COG output is needed, run `make etl` or enable `ETL_AUTO=true`.
4. Confirm `curl http://localhost:6000/model_summary` shows the expected file.
5. Confirm the map shows the expected valid time and layer.

## Backup And Restore

Back up these paths before customer-site maintenance:

- `.env`
- `data/`
- `cog_data/`
- deployment notes or customer-specific config outside git

Restore order:

1. Restore `.env`.
2. Restore `data/`.
3. Restore `cog_data/` if available; otherwise rerun ETL.
4. Start services.
5. Run `curl http://localhost:6000/ready`.
6. Run `make qa` against the restored backend.

## Incident Response

If the map loads but no model data appears:

1. Check `/ready`.
2. Check `/model_summary`.
3. Verify the selected file is inside `NETCDF_DATA_DIR`.
4. Verify `.env` has the intended `NETCDF_PATH`.
5. Check backend logs with `make logs`.

If private API calls return 401:

1. Confirm backend and web-client share the same `API_KEY`.
2. Confirm Nginx template includes `proxy_set_header X-API-Key`.
3. Run `make release-check`.

If tiles are slow:

1. Check `/metrics` cache counters.
2. Increase `TILE_CACHE_SIZE` for repeated dynamic fallback tiles.
3. Prefer precomputed COG output for high-traffic layers.
4. Confirm Docker has enough memory on MacBook Pro M2.

## Customer Handoff

Every handoff should include:

- release version, git SHA, and build date
- expected WRF file name and valid time range
- `.env.example` with customer-specific values redacted
- `README.md`, `CHANGELOG.md`, `docs/OPERATIONS.md`, `docs/SECURITY.md`, and `docs/THIRD_PARTY_NOTICES.md`
- latest `make release-check` result
- known limits, especially single-process in-memory rate limiting
