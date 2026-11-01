# 1Finance — Setup & configuration

## Run with Docker (recommended)

```bash
docker compose up --build
# → http://localhost:3000   demo login: demo@1finance.app / demo-1finance
```

The stack: PostgreSQL 16, Redis, `api` (FastAPI, runs migrations + seed on start), `worker` (Celery worker + beat:
6-hourly sync and FX refresh), `web` (Next.js).

## Run locally (development)

Requirements: Python 3.12+, Node 20+, PostgreSQL 16, Redis 7.

```bash
# database
createuser -P onefinance            # password: onefinance
createdb -O onefinance onefinance
createdb -O onefinance onefinance_test

# API
cd apps/api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
python -m app.seed                  # reference data + DEMO data (when ONEFINANCE_DEMO_MODE=true)
uvicorn app.main:app --reload --port 8000
celery -A app.worker worker -B      # optional: scheduled sync + FX

# Web
cd apps/web
npm install
npm run dev                         # http://localhost:3000 (proxies /api → :8000)
```

## Tests

| Suite | Command | Notes |
|---|---|---|
| Financial engine + connectors + API (66 tests) | `cd apps/api && pytest` | uses the `onefinance_test` database |
| Type check / lint | `cd apps/web && npm run typecheck && npm run lint` | |
| End-to-end, desktop + mobile (15 tests) | `cd apps/web && npx playwright test` | needs API (demo mode) + web running |

## Connecting real accounts

All integrations are **read-only**. Credentials are validated with a live request, encrypted with AES-256-GCM and
never returned to the browser.

**Interactive Brokers (Flex Web Service)**
1. Client Portal → Performance & Reports → Flex Queries → *Create Activity Flex Query*.
   Sections: Account Information, Cash Report, Open Positions, Trades, Cash Transactions, Equity Summary. Format: **XML**. Period: e.g. Last 365 days.
2. Flex Web Service → generate a token (set an IP allowlist and lifespan).
3. In 1Finance: Accounts → Add account → Interactive Brokers → Official API → paste token + query ID.

**Groww (Trade API)** — requires a Groww Trade API plan.
1. groww.in/trade-api → API keys → generate an access token (expires daily 06:00 IST) **or** an API key + TOTP secret
   (lets 1Finance renew the token itself).
2. Stocks/ETFs sync automatically. Mutual funds and FDs are not in the Trade API → import a statement or add as manual assets.
   Without the Live Data plan, prices are shown at average cost and labelled "Imported price".

**Revolut** — Open Banking requires a regulated AISP. Use Revolut app → Statement → Excel/CSV, then
Accounts → Add account → Other/Revolut → Statement import (or "Import statement" on an existing account).
To enable live sync later, implement `AggregatorConnector` with a licensed provider (GoCardless Bank Account Data, TrueLayer, Tink).

## Production checklist

- `ONEFINANCE_ENV=production`, `ONEFINANCE_DEMO_MODE=false`, `ONEFINANCE_ALLOW_MOCK_CONNECTORS=false` (the API refuses to start otherwise)
- `ONEFINANCE_CREDENTIAL_KEY` from a secret manager (KMS / Vault / Docker secrets); rotate by re-encrypting `encrypted_credentials`
- HTTPS everywhere; `ONEFINANCE_COOKIE_SECURE=true` (enables `__Host-` cookies); TLS to Postgres; Postgres encryption at rest
- Restrict DB network access to the API/worker; run as the non-root users defined in the Dockerfiles
- Replace the in-process rate limiter with a Redis-backed one when running more than one API instance
- Enable MFA for your user (Settings → Security); exports and data deletion then require it
- Back up Postgres daily (`pg_dump` / managed snapshots) and test restores

## Passkeys

The data model (`webauthn_credentials`) and UI placeholders are in place. To activate: add `py_webauthn`, set
`ONEFINANCE_WEBAUTHN_RP_ID` / origin, implement `/auth/passkeys/{register,authenticate}/{options,verify}` and wire
`navigator.credentials` in the login page. This needs a real HTTPS origin, so it is not enabled in the dev build.

## Regenerating API types

```bash
cd apps/web && npm run gen:api     # writes src/lib/api-schema.d.ts from the live OpenAPI spec
```
