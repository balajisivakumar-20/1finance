# 1Finance

**One App. Every Asset. Complete Financial Clarity.**

A personal wealth-management app that consolidates bank accounts, brokerages (Interactive Brokers, Groww), statements
and manual assets into one calm, premium dashboard. It is read-only by design: there are no trading, transfer or payment features.

```
apps/
  api/        FastAPI · SQLAlchemy 2 · Alembic · Celery — modular monolith
    app/finance/          Decimal calculation engine (net worth, FX, cash flow, TWR/MWR, dedup, transfers)
    app/categorization/   rules → learned corrections → merchant dictionary → (opt-in) AI
    app/connectors/       read-only adapters: IBKR Flex, Groww, aggregator stub, CSV, manual + DEMO mocks
    app/sync/             sync engine (savepoints, checkpoints, backoff, re-auth)
    app/importers/        statement parsing with preview/validation
    app/services/         ledger read-model, analytics, insights, reports (PDF/XLSX/CSV)
    app/api/routes/       HTTP layer
  web/        Next.js 15 · React 19 · Tailwind 4 · Radix · TanStack Query/Table · Recharts · Motion · Zod
  desktop/    Tauri — planned          mobile/  Expo — planned
infrastructure/docker/   Dockerfiles      docs/   architecture, integrations, setup
```

Start here: [docs/SETUP.md](docs/SETUP.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)

### Key guarantees
- Money is `NUMERIC` in Postgres and `Decimal` in Python, and travels as exact strings. The browser formats it but never calculates it.
- Original currencies are preserved. Conversions use stored, dated exchange rates, and the rate used is shown.
- Raw provider data is immutable. User edits live in separate override columns.
- Duplicates are flagged, never silently deleted. Transfers between your own accounts are not counted as income or expenses.
- Connections only show as connected after a real authorization succeeds. Demo data is always labelled.
