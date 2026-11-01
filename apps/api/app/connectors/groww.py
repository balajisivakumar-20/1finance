"""Groww Trade API — portfolio endpoints only (read-only).

Docs: https://groww.in/trade-api/docs  ·  Headers: Authorization: Bearer <token>, X-API-VERSION: 1.0
Tokens expire daily at 06:00 IST. If an API key + TOTP secret are stored, a fresh token is minted automatically;
otherwise the connection moves to "reauth_required".
Not available via this API: mutual funds, FDs, historical transactions → use statement import.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pyotp

from .base import (
    AccountData,
    BalanceData,
    Capability,
    ConnectorError,
    ConnectorInfo,
    FinancialConnector,
    HoldingData,
    RateLimited,
    ReauthRequired,
    SecurityData,
)

BASE = "https://api.groww.in"
UNSUPPORTED_ASSETS = ("mutual_funds", "fixed_deposits", "transaction_history")


class GrowwConnector(FinancialConnector):
    info = ConnectorInfo(
        key="groww",
        institution_slug="groww",
        display_name="Groww — Trade API",
        auth_method="api_token",
        capabilities=frozenset({Capability.ACCOUNTS, Capability.BALANCES, Capability.HOLDINGS}),
        credential_fields=("access_token", "api_key", "totp_secret"),
        notes="Requires a Groww Trade API subscription. Mutual funds and FDs: manual import available.",
    )
    ACCT = "groww-demat"

    def __init__(self, credentials=None, client: httpx.Client | None = None):
        super().__init__(credentials)
        self.http = client or httpx.Client(base_url=BASE, timeout=20)

    def _token(self) -> str:
        if tok := self.credentials.get("access_token"):
            return tok
        key, secret = self.credentials.get("api_key"), self.credentials.get("totp_secret")
        if not key or not secret:
            raise ReauthRequired("Groww access token missing or expired")
        r = self.http.post("/v1/token/api/access", headers={"Authorization": f"Bearer {key}"},
                           json={"key_type": "totp", "totp": pyotp.TOTP(secret).now()})
        if r.status_code in (401, 403):
            raise ReauthRequired("Groww rejected the API key / TOTP")
        r.raise_for_status()
        tok = r.json().get("token")
        if not tok:
            raise ConnectorError("Groww did not return an access token")
        self.credentials["access_token"] = tok
        return tok

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self.http.get(path, params=params, headers={"Authorization": f"Bearer {self._token()}",
                                                        "Accept": "application/json", "X-API-VERSION": "1.0"})
        if r.status_code == 401:
            self.credentials.pop("access_token", None)
            raise ReauthRequired("Groww token expired (tokens reset daily at 06:00 IST)")
        if r.status_code == 403:
            raise ConnectorError("Groww API subscription required for this endpoint")
        if r.status_code == 429:
            raise RateLimited("Groww rate limit", 2)
        r.raise_for_status()
        body = r.json()
        if body.get("status") != "SUCCESS":
            raise ConnectorError(f"Groww error: {body.get('error', {}).get('message', 'unknown')}")
        return body.get("payload") or {}

    def validate_connection(self):
        self._get("/v1/holdings/user")

    def list_accounts(self):
        return [AccountData(self.ACCT, "Groww Stocks", "brokerage", "INR")]

    def fetch_holdings(self):
        payload = self._get("/v1/holdings/user")
        now = datetime.now(timezone.utc)
        rows = [h for h in payload.get("holdings", []) if Decimal(str(h.get("quantity", "0"))) != 0]
        symbols = [h.get("trading_symbol") or h.get("isin") for h in rows]
        prices = self._ltp_batch(symbols)
        out = []
        for h, symbol in zip(rows, symbols):
            ltp = prices.get(symbol)
            avg = Decimal(str(h.get("average_price", "0")))
            sec = SecurityData(symbol, symbol, "stock", "INR", h.get("isin"), "NSE", "IN")
            # Without the Live Data subscription there is no price: value at average price and label it "imported".
            out.append(HoldingData(self.ACCT, sec, Decimal(str(h["quantity"])), avg, ltp if ltp is not None else avg,
                                   "INR", now, "live" if ltp is not None else "imported"))
        return out

    def _ltp_batch(self, symbols: list[str]) -> dict[str, Decimal]:
        """GET /v1/live-data/ltp?segment=CASH&exchange_symbols=NSE_A,NSE_B (≤50 per call). Needs Live Data plan."""
        out: dict[str, Decimal] = {}
        for i in range(0, len(symbols), 50):
            chunk = symbols[i : i + 50]
            try:
                p = self._get("/v1/live-data/ltp", {"segment": "CASH", "exchange_symbols": ",".join(f"NSE_{s}" for s in chunk)})
            except ConnectorError:
                return out
            for s in chunk:
                if (v := p.get(f"NSE_{s}")) is not None:
                    out[s] = Decimal(str(v))
        return out

    def fetch_balances(self, since=None):
        p = self._get("/v1/margins/detail/user")
        cash = p.get("clear_cash")
        if cash is None:
            return []
        return [BalanceData(self.ACCT, Decimal(str(cash)), "INR", datetime.now(timezone.utc))]
