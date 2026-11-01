# Financial integrations — what is actually possible

Researched November 2026. All access is **read-only**. 1Finance never references order, transfer or
payment endpoints.

## Capability matrix

| Capability | Interactive Brokers | Groww | Revolut | CSV import | Manual |
|---|---|---|---|---|---|
| Connection method | Flex Web Service (token + query id) | Trade API access token (or API key + TOTP) | Licensed aggregator / statement import | File upload | Form |
| Balances | ✅ Flex `EquitySummary`, `CashReport` | ◐ margin endpoint (cash available) | 🔒 needs AISP | ✅ derived | ✅ |
| Positions / holdings | ✅ `OpenPositions` | ✅ `GET /v1/holdings/user` (demat, ISIN) | — | — | ✅ |
| Cost basis / avg price | ✅ | ✅ average price | — | — | ✅ |
| Trades / investment activity | ✅ `Trades` | ◐ today's trade list only | — | ✅ | ✅ |
| Dividends, fees, deposits | ✅ `CashTransactions` | ❌ not exposed | — | ✅ | ✅ |
| Bank transactions | — | — | 🔒 needs AISP | ✅ Revolut CSV | ✅ |
| Mutual funds / FDs | — | ❌ not in Trade API → **Manual import available** | — | ✅ | ✅ |
| Historical backfill | ✅ up to 365 days per request (date range) | ❌ | 🔒 | ✅ | — |

### Interactive Brokers — Flex Web Service (implemented: `connectors/ibkr_flex.py`)
- Two-step flow: `SendRequest?t={token}&q={queryId}&v=3` returns a reference code; `GetStatement` with that
  code returns the XML report.
- Base URL `https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService`. Pacing: 1 request/second,
  max 10/minute per token. Error 1019 = statement still generating (poll), 1018 = rate limited (back off),
  1012 = token expired (→ "Reconnection required").
- **Your setup:** Client Portal → Performance & Reports → Flex Queries → create an *Activity Flex Query*
  with sections Account Information, Cash Report, Open Positions, Trades, Cash Transactions, Equity Summary;
  format XML. Then Flex Web Service → generate token (set IP allowlist + lifespan). Paste token + query id.
- The Client Portal Gateway / Web API requires a locally running gateway with interactive browser login and
  is not a good fit for unattended sync; it is intentionally not used.

### Groww — Trade API (implemented: `connectors/groww.py`)
- Base `https://api.groww.in`, headers `Authorization: Bearer …`, `X-API-VERSION: 1.0`.
- Portfolio endpoints: `GET /v1/holdings/user`, `GET /v1/positions/user`, margin. Non-trading rate limit
  ~10 req/s.
- Access tokens **expire daily at 06:00 IST** → connector reports `reauth_required` after expiry unless an
  API key + TOTP secret is stored (then it mints a token itself).
- API access is a paid subscription on Groww's side; check pricing on groww.in/trade-api.
- Mutual funds, FDs and historical transactions are **not** in the Trade API — use the Groww
  statement / CAS export via the CSV import connector. The UI shows "Manual import available".

### Revolut
- The Open Banking API is for regulated TPPs (AISP/PISP) and needs eIDAS (QWAC/QSeal) or OBIE certificates.
  An individual cannot register for production access.
- **Supported path today:** Revolut app → Statements → Excel/CSV → upload in 1Finance (parser
  `importers/revolut_csv.py`, with preview + validation before commit).
- **Future path:** a licensed aggregator (e.g. GoCardless Bank Account Data, TrueLayer, Tink, Salt Edge) with
  its own consent flow. The `AggregatorConnector` stub is in place; it reports `not_configured` until keys exist.

## Exchange rates
`fx/providers.py` defines `ExchangeRateProvider`. Production default: **ECB reference rates** (free, daily,
EUR base, includes INR/USD/GBP). Rates are stored with provider + effective timestamp; cross rates are derived
via EUR and labeled as such. Demo mode seeds rates flagged `provider = "demo"`.
