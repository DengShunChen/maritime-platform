# Security Baseline

Maritime Platform is currently suitable for local customer demos and controlled single-tenant deployments when this baseline is followed.

## Supported Deployment Model

- Single tenant per deployment.
- Backend API is reached through Nginx or a trusted reverse proxy.
- Browser clients never receive the backend `API_KEY`.
- WRF data files remain on the deployment host or controlled storage.

Multi-tenant accounts, role-based access control, billing, and per-customer data isolation are product roadmap items and should be added before broad public SaaS launch.

## Secrets

Store secrets in `.env` or the deployment platform secret manager. Never commit:

- `.env`
- `web-client/.env`
- MapTiler keys
- backend `API_KEY`
- customer WRF data

The release gate verifies that local secret and data paths are ignored.

## API Protection

Set `API_KEY` outside local development. Protected API requests may use:

- `X-API-Key: <key>`
- `Authorization: Bearer <key>`

Public endpoints:

- `/health`
- `/ready`
- `/version`

Private endpoints include model metadata, tiles, file selection, metrics, and ETL controls unless explicitly exempted in code.

## Network Controls

For customer or internet-reachable deployments:

- Put TLS termination in front of Nginx.
- Restrict `CORS_ORIGINS` to the deployed origin.
- Keep backend and TiTiler off the public internet when possible.
- Use VPN, IP allowlists, or an API gateway for administrative access.
- Set `RATE_LIMIT_PER_MINUTE` to a nonzero value for demos and trials.

## Data Access

Dataset selection is confined to `NETCDF_DATA_DIR`. Only WRF/NetCDF/GRIB candidate files under that directory should be selectable.

Customer forecast files may contain commercially sensitive operational information. Treat `data/` and `cog_data/` as confidential unless the customer explicitly approves sharing.

## Logging

Application logs should support operational debugging without exposing secrets:

- Do not log `API_KEY`.
- Do not log full `.env` content.
- Avoid publishing full customer file paths in public support tickets.
- Keep `/version` available for support traceability without exposing secrets.

## Dependency And Image Hygiene

Before commercial delivery:

```bash
make release-check
```

Maintain the release dependency notice:

```bash
make notices
python scripts/generate_third_party_notices.py --check
```

Review [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) before customer delivery. Items under "Manual Review Required" need human confirmation because their lockfile metadata is ambiguous, GPL-compatible, unknown, or unavailable from plain Python requirements.

Recommended additional checks when network access and registry credentials are available:

- npm dependency audit
- Python dependency audit
- container image vulnerability scan
- SBOM generation for backend and web-client images

## Incident Response

If a secret is exposed:

1. Revoke or rotate the secret immediately.
2. Redeploy with the new secret.
3. Confirm `/version` reports the expected build.
4. Run `make release-check`.
5. Review logs for unauthorized requests.

If customer data is exposed:

1. Preserve logs and deployment state.
2. Remove public access.
3. Identify affected files and time window.
4. Notify the customer owner.
5. Rotate API keys and redeploy.

## Commercial Launch Gaps

The current security baseline is not yet a complete public SaaS control plane. Before broad commercial launch, add:

- user accounts and organization model
- role-based access control
- tenant-scoped datasets
- audit logs
- passwordless or SSO login
- billing and entitlement checks
- persistent distributed rate limiting
- formal vulnerability scanning in CI
- signed releases and SBOM artifacts
