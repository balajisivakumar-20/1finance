# 1Finance — Architecture

> One App. Every Asset. Complete Financial Clarity.

## 1. System overview

```
┌─────────────────────────┐        HTTPS (cookie session + CSRF)        ┌──────────────────────────────┐
│ apps/web  (Next.js 15)  │ ─────────────────────────────────────────▶ │ apps/api  (FastAPI)          │
│ React 19 · Tailwind 4   │   /api/* proxied by Next rewrites          │  routes → services → repos    │
│ TanStack Query/Table    │                                            │  finance/ (Decimal engine)    │
│ Recharts · Motion       │ ◀── typed JSON (OpenAPI → TS types) ────── │  connectors/ (read-only)      │
└─────────────────────────┘                                            │  categorization/ · analytics/ │
                                                                       └──────┬─────────────┬──────────┘
                                                                              │             │
                                                                     PostgreSQL 16     Redis + Celery
                                                                     (NUMERIC money)   (sync jobs, FX)
```

**Modular monolith.** One deployable API with strict internal module boundaries; no microservices. The
requested monorepo folders `services/connectors`, `services/synchronization`, `services/analytics`,
`services/categorization`, `services/reporting` live as Python packages inside `apps/api/app/` so that
they share one process, one DB session and one transaction boundary. They import only from `app.finance`
(pure functions) and repository interfaces — never from the HTTP layer.

| Requested folder | Implemented at |
|---|---|
| `packages/financial-core` | `apps/api/app/finance/` (authoritative, Decimal) + `apps/web/src/lib/format.ts` (display only) |
| `services/connectors` | `apps/api/app/connectors/` |
| `services/synchronization` | `apps/api/app/sync/` |
| `services/analytics` | `apps/api/app/services/analytics.py` |
| `services/categorization` | `apps/api/app/categorization/` |
| `services/reporting` | `apps/api/app/services/reports.py` |
| `packages/shared-types` / `api-client` | `apps/web/src/lib/api/` (types mirror OpenAPI; regenerate with `npm run gen:api`) |
| `infrastructure/docker` | `infrastructure/docker/` + `docker-compose.yml` |

**Golden rule:** every money number shown in the UI is computed on the server with `Decimal`. The web app
formats; it never sums money.

## 2. Layering inside the API

```
api/routes/*.py        HTTP only: auth dependency, validation (Pydantic), status codes
services/*.py          use-cases: dashboard summary, transactions, accounts, imports, reports
finance/*.py           pure, side-effect-free calculations (100% unit tested)
categorization/        rule engine (user rules → merchant dictionary → learned corrections → optional AI)
connectors/            FinancialConnector adapters, capability discovery, mock vs production split
sync/                  sync orchestration, checkpoints, retries with exponential backoff
models/                SQLAlchemy 2.0 ORM (NUMERIC(20,8) money, UTC timestamps)
core/                  config, DB session, security (argon2, sessions, CSRF, credential encryption)
```

## 3. Data principles

1. **Raw vs normalized.** `transactions.raw_payload` (JSONB) and `raw_description` are written once by the
   importer and never updated. User edits go to `user_category_id`, `user_notes`, `tags`, `user_type`.
   The effective category is `COALESCE(user_category_id, category_id)`.
2. **Original currency is sacred.** Every amount is stored in its original currency. Converted values are
   computed at read time from a *stored* `exchange_rates` row, and the rate + timestamp are returned with
   the converted value.
3. **Snapshots for history.** Balances, holdings, asset valuations and liability balances are append-only
   snapshots. Net-worth history is computed per day from the latest snapshot on or before that day, using
   the FX rate effective on that day.
4. **Provenance.** Every record carries `source` (`api`, `import:csv`, `manual`, `mock`) and an
   `import_batch_id` / `sync_job_id` where applicable. Mock data is flagged `is_demo = true` and the UI shows a
   "Demo data" badge whenever any demo record contributes to a figure.
5. **No double counting.** Brokerage cash is taken from the broker's cash balance *or* the linked account,
   never both (`accounts.counts_toward_net_worth`). Credit cards count the outstanding balance, not the limit.
   Internal transfers (`transaction_type = transfer`) are excluded from income/expenses.

## 4. Financial definitions (implemented in `app/finance`)

| Metric | Definition |
|---|---|
| Net worth | Σ asset balances (converted) − Σ liability balances (converted), at one valuation instant |
| Income (period) | Σ inflows with type ∈ {income, interest, dividend*} excluding transfers and refunds (*dividends are investment income, shown separately) |
| Expenses (period) | Σ outflows with type = expense **minus** refunds matched to expense categories; excludes transfers, investment buys, fees on investment accounts are shown under Financial |
| Savings | Income − Eligible expenses |
| Savings rate | Savings ÷ Income × 100; `None` when income ≤ 0 (UI shows "—" with explanation) |
| Unrealized P/L | Market value − cost basis (per holding, in trading currency) |
| Simple return | Unrealized P/L ÷ cost basis |
| TWR | Chain-linked sub-period returns, breaking at each external cash flow (Modified Dietz not used) |
| MWR | XIRR of external flows + terminal value (Newton–Raphson with bisection fallback) |
| FX effect | (value in base at end rate) − (value in base at start rate) for unchanged local value |
| Budget utilization | spent ÷ budget; status `ok` < 80 %, `warning` 80–100 %, `over` > 100 % |

Rounding: never round intermediates. `quantize` only at presentation using ISO 4217 minor units
(EUR/USD/GBP/INR = 2, JPY = 0).

## 5. Security model

- **Sessions:** opaque 256-bit random token in `__Host-1f_session` cookie (`HttpOnly; Secure; SameSite=Lax`);
  only its SHA-256 is stored server-side. Idle timeout 30 min, absolute 12 h, revocable per device.
- **CSRF:** double-submit token (`1f_csrf` cookie + `X-CSRF-Token` header) on every unsafe method.
- **Passwords:** argon2id. **MFA:** TOTP (RFC 6238) required for sensitive settings when enabled.
- **Passkeys (WebAuthn):** the API surface (`/auth/passkeys/*`) and DB table (`webauthn_credentials`) are
  defined; activation needs `py_webauthn` and a configured RP ID/origin — see `docs/SETUP.md`.
- **Provider credentials:** AES-256-GCM with a key from `ONEFINANCE_CREDENTIAL_KEY` (swap for KMS/Vault in prod);
  never returned by any endpoint, never logged (log filter redacts `token|secret|password|authorization`).
- **Read-only by construction:** the connector interface has no write methods. The Groww and IBKR adapters
  only ever call portfolio/report endpoints; order endpoints are not referenced anywhere in the codebase.
- **Headers:** CSP, HSTS, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy set by middleware + Next config.
- **Rate limiting:** token bucket per session/IP on auth and sync endpoints.
- **Audit log:** login, failed login, connect/disconnect, credential rotation, import, export.

## 6. Cross-platform path

- **PWA:** manifest + service worker that caches only the app shell and static assets. API responses are
  `Cache-Control: no-store` and the SW never caches `/api/*`.
- **Desktop (Tauri):** the Next app can be exported as a static SPA (all pages are client-rendered against the
  API), wrapped by Tauri; secure storage via the Tauri stronghold plugin; biometrics via OS plugins.
- **Mobile (Expo):** formatting, Zod schemas and API types in `src/lib` are framework-free and can move into
  `packages/` unchanged when the Expo app is created.

## 7. Phase status

| Phase | Status |
|---|---|
| 1 Foundation | ✅ Monorepo, FastAPI, Postgres + Alembic, cookie sessions with CSRF, TOTP MFA, app shell, design system, light/dark/system themes, responsive nav. Passkeys: schema + UI placeholder only (see SETUP.md) |
| 2 Dashboard & mock data | ✅ Every overview widget is wired to real endpoints over clearly labelled demo data |
| 3 Core features | ✅ Calculation engine, multi-currency, categorization with learning, dedup, transfer detection, accounts, transactions, manual assets/liabilities |
| 4 Integrations | ◐ Connector framework with capability discovery, mock IBKR/Groww/Revolut, CSV/Revolut statement import, real IBKR Flex and Groww clients (tested against recorded responses; need your tokens for live use), Celery sync. Revolut live sync needs a licensed aggregator |
| 5 Planning | ✅ Budgets, goals (with overlap warning), analytics, deterministic insights, PDF/XLSX/CSV reports |
| 6 Security & quality | ◐ Security headers, CSP, audit log, rate limits, credential encryption, 66 backend tests, 15 Playwright E2E tests (desktop and mobile). ⏳ Redis-backed rate limiter, automated backups, full WCAG audit |
| 7 Cross-platform | ◐ PWA: manifest, icons, shell-only service worker, update prompt. ⏳ Tauri and Expo shells |
