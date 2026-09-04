# Changelog

All notable product, operational, and deployment changes are tracked here.

## Unreleased

### Added
- Windy-class operational map shell with WRF status, variable groups, WebGL wind particles, time controls, coordinate probing, and forecast status telemetry.
- Commercial release gate via `make release-check`, covering frontend build, backend contract tests, compose validation, secret/data ignore checks, and real WRF readiness smoke.
- Backend operational endpoints: `/health`, `/ready`, `/version`, `/metrics`, `/model_summary`, and `/time_series`.
- Optional API key protection, server-side Nginx API key injection, basic rate limiting, response security headers, CORS configuration, and release identity metadata.
- WRF/NetCDF data directory fallback and confined dataset selection under `NETCDF_DATA_DIR`.
- Operations and security runbooks for deployment, monitoring, incident response, backup, restore, and customer handoff.
- Third-party dependency notice generation and release-gated notice freshness checks.
- Automated concurrent dynamic tile contract test plus verified 50-request load test for Matplotlib render-lock hardening.

### Changed
- README now reflects the COG/TiTiler-first architecture with dynamic tile fallback.
- Docker images carry OCI labels and build identity for customer-site support.

### Security
- `.env`, `web-client/.env`, generated artifacts, and large WRF data files are excluded from source control.
- Private API paths can be protected with `API_KEY`; public health endpoints stay open for liveness/readiness automation.

## v1.1.0 - 2026-01-16

### Added
- Variable selector and time slider for WRF model output.

### Fixed
- Improved raster rendering behavior.

### Changed
- Default map focus moved toward Taiwan and East Asia.
