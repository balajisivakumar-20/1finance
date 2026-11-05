"""Interactive Brokers — Flex Web Service (read-only reports).

Flow: SendRequest(token, queryId) → ReferenceCode → GetStatement(token, ReferenceCode) → XML.
Pacing: 1 req/s, max 10 req/min per token. Codes: 1019 still generating, 1018 throttled, 1012/1015 token issues.
Configure an *Activity* Flex Query (XML) including: AccountInformation, CashReport, OpenPositions, Trades,
CashTransactions, EquitySummaryInBase.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from .base import (
    AccountData,
    BalanceData,
    Capability,
    ConnectorError,
    ConnectorInfo,
    FinancialConnector,
    HoldingData,
    InvestmentActivityData,
    RateLimited,
    ReauthRequired,
    SecurityData,
)

BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
AUTH_ERRORS = {"1012", "1015", "1014"}  # expired / invalid token, invalid query
ASSET_CLASS = {"STK": "stock", "ETF": "etf", "FUND": "mutual_fund", "BOND": "bond", "OPT": "other", "FUT": "other", "CASH": "cash"}


def _d(v: str | None) -> Decimal | None:
    if v in (None, "", "--"):
        return None
    try:
        return Decimal(v.replace(",", ""))
    except InvalidOperation:
        return None


def _dt(v: str | None, day_first: bool = False) -> datetime | None:
    """Parse any Flex date setting: yyyyMMdd, yyyy-MM-dd, MM/dd/yyyy, dd/MM/yyyy, dd-MMM-yy …, optionally with a time."""
    if not v:
        return None
    day, _, clock = v.replace(";", " ").strip().partition(" ")
    slash = ["%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y"]
    for fmt in ("%Y%m%d", "%Y-%m-%d", *(slash if day_first else slash[2:] + slash[:2]), "%d-%b-%y", "%d-%b-%Y"):
        try:
            d = datetime.strptime(day, fmt)
            break
        except ValueError:
            continue
    else:
        return None
    for fmt in ("%H%M%S", "%H:%M:%S", "%H:%M"):
        try:
            d = datetime.combine(d.date(), datetime.strptime(clock.strip(), fmt).time())
            break
        except ValueError:
            continue
    return d.replace(tzinfo=timezone.utc)


class FlexStatementParser:
    """Pure XML → DTO parser (unit-tested with fixtures; no network)."""

    def __init__(self, xml: str) -> None:
        self.root = ET.fromstring(xml)
        self.statements = self.root.findall(".//FlexStatement")
        if not self.statements:
            raise ConnectorError("Flex response contained no statements — check the query configuration")
        self.now = datetime.now(timezone.utc)
        self.day_first = self._detect_day_first()

    def _detect_day_first(self) -> bool:
        """04/11/2026 is ambiguous; the reading that puts the generation time closest to now is the query's format."""
        for st in self.statements:
            stamp = st.get("whenGenerated") or st.get("toDate")
            a, b = _dt(stamp, True), _dt(stamp, False)
            if a and b and a != b:
                return abs(a - self.now) < abs(b - self.now)
        return False

    def _dt(self, v: str | None) -> datetime | None:
        return _dt(v, self.day_first)

    def _book(self, st: ET.Element) -> tuple[dict, dict]:
        """Average-cost book rebuilt from the statement's trades, for accounts where IBKR reports cost/realized P&L as 0.

        Returns ({(symbol, currency): (quantity, total cost)} for positions whose full history is in the statement,
        {trade id: realized P&L} for sells of those positions)."""
        trades = [t for t in st.findall("Trades/Trade")
                  if t.get("assetCategory") != "CASH" and t.get("levelOfDetail", "EXECUTION") == "EXECUTION"]
        trades.sort(key=lambda t: self._dt(t.get("dateTime") or t.get("tradeDate")) or self.now)
        held: dict[tuple, list] = {}
        realized: dict[str, Decimal] = {}
        broken: set[tuple] = set()  # sold more than the statement shows being bought: history starts earlier
        for t in trades:
            key, qty = (t.get("symbol"), t.get("currency")), _d(t.get("quantity"))
            net = _d(t.get("netCash"))
            if qty is None or net is None or key in broken:
                continue
            q, cost = held.setdefault(key, [Decimal(0), Decimal(0)])
            if qty > 0:
                held[key] = [q + qty, cost - net]  # netCash is negative for a buy and includes commission
            elif -qty > q:
                broken.add(key)
            else:
                part = cost * (-qty) / q
                realized[t.get("tradeID") or t.get("transactionID") or ""] = net - part
                held[key] = [q + qty, cost - part]
        return {k: (q, c) for k, (q, c) in held.items() if k not in broken}, realized

    def _as_of(self, st: ET.Element) -> datetime:
        # one timestamp per statement, so all of its balances and positions form a single snapshot
        return self._dt(st.get("toDate")) or self._dt(st.get("whenGenerated")) or self.now

    def accounts(self) -> list[AccountData]:
        out = []
        for st in self.statements:
            info = st.find("AccountInformation")
            acct = st.get("accountId", "")
            cur = (info.get("currency") if info is not None else None) or "USD"
            name = (info.get("acctAlias") if info is not None else None) or "IBKR account"
            out.append(AccountData(acct, name, "brokerage", cur))
        return out

    def cash_balances(self) -> list[BalanceData]:
        out = []
        for st in self.statements:
            acct, as_of = st.get("accountId", ""), self._as_of(st)
            for row in st.findall("CashReport/CashReportCurrency"):
                cur = row.get("currency")
                if not cur or cur == "BASE_SUMMARY":
                    continue
                bal = _d(row.get("endingCash"))
                if bal is not None:
                    out.append(BalanceData(acct, bal, cur, as_of, _d(row.get("endingSettledCash"))))
        return out

    def holdings(self) -> list[HoldingData]:
        out = []
        for st in self.statements:
            acct, as_of = st.get("accountId", ""), self._as_of(st)
            book, _ = self._book(st)
            for p in st.findall("OpenPositions/OpenPosition"):
                if p.get("levelOfDetail", "SUMMARY") not in ("SUMMARY", ""):
                    continue
                qty, mark = _d(p.get("position")), _d(p.get("markPrice"))
                if qty is None or mark is None:
                    continue
                cost_basis = _d(p.get("costBasisMoney"))
                avg = _d(p.get("costBasisPrice")) or ((cost_basis / qty) if cost_basis and qty else Decimal(0))
                cur = p.get("currency", "USD")
                bq, bc = book.get((p.get("symbol"), cur), (None, None))
                if not avg and bq and abs(bq - qty) < Decimal("0.0001"):
                    avg = bc / bq
                sec = SecurityData(
                    ticker=p.get("symbol", "?"), name=p.get("description") or p.get("symbol", "?"),
                    asset_class=ASSET_CLASS.get(p.get("assetCategory", ""), "other"), currency=cur,
                    isin=p.get("isin") or None, exchange=p.get("listingExchange") or None,
                )
                out.append(HoldingData(acct, sec, qty, avg, mark, cur, as_of, "close"))
        return out

    def activity(self) -> list[InvestmentActivityData]:
        out = []
        for st in self.statements:
            acct = st.get("accountId", "")
            _, realized = self._book(st)
            for t in st.findall("Trades/Trade"):
                qty, price = _d(t.get("quantity")), _d(t.get("tradePrice"))
                if qty is None or t.get("assetCategory") == "CASH":  # currency conversions, not investments
                    continue
                tid = t.get("tradeID") or t.get("transactionID")
                pnl = _d(t.get("fifoPnlRealized")) or (realized.get(tid) if qty < 0 else None)
                cur = t.get("currency", "USD")
                sec = SecurityData(t.get("symbol", "?"), t.get("description") or t.get("symbol", "?"),
                                   ASSET_CLASS.get(t.get("assetCategory", ""), "other"), cur, t.get("isin") or None,
                                   t.get("listingExchange") or None)
                out.append(InvestmentActivityData(
                    acct, tid, "buy" if qty > 0 else "sell",
                    _d(t.get("netCash")) or Decimal(0), cur, self._dt(t.get("dateTime") or t.get("tradeDate")) or self.now,
                    sec, abs(qty), price, abs(_d(t.get("ibCommission")) or Decimal(0)), pnl,
                ))
            kinds = {"Dividends": "dividend", "Payment In Lieu Of Dividends": "dividend", "Withholding Tax": "fee",
                     "Deposits/Withdrawals": "deposit", "Broker Interest Received": "interest",
                     "Broker Interest Paid": "fee", "Other Fees": "fee", "Commission Adjustments": "fee"}
            for c in st.findall("CashTransactions/CashTransaction"):
                amt = _d(c.get("amount"))
                if amt is None:
                    continue
                kind = kinds.get(c.get("type", ""), "fee" if amt < 0 else "interest")
                if kind == "deposit" and amt < 0:
                    kind = "withdrawal"
                out.append(InvestmentActivityData(acct, c.get("transactionID"), kind, amt, c.get("currency", "USD"),
                                                  self._dt(c.get("dateTime") or c.get("settleDate")) or self.now))
        return out


class IBKRFlexConnector(FinancialConnector):
    info = ConnectorInfo(
        key="ibkr_flex",
        institution_slug="interactive-brokers",
        display_name="Interactive Brokers — Flex Web Service",
        auth_method="api_token",
        capabilities=frozenset({Capability.ACCOUNTS, Capability.BALANCES, Capability.HOLDINGS,
                                Capability.INVESTMENT_ACTIVITY, Capability.HISTORICAL_BACKFILL}),
        credential_fields=("flex_token", "query_id"),
        notes="Create an Activity Flex Query (XML) and a Flex Web Service token in IBKR Client Portal.",
    )

    def __init__(self, credentials=None, client: httpx.Client | None = None, sleep=time.sleep):
        super().__init__(credentials)
        self.http = client or httpx.Client(timeout=30, headers={"User-Agent": "1Finance/0.1"})
        self.sleep = sleep
        self._cache: FlexStatementParser | None = None

    def _get(self, path: str, params: dict) -> ET.Element:
        r = self.http.get(f"{BASE}/{path}", params={**params, "v": "3"})
        if r.status_code == 429:
            raise RateLimited("IBKR rate limit", 60)
        r.raise_for_status()
        return ET.fromstring(r.text)

    def _statement(self) -> FlexStatementParser:
        if self._cache:
            return self._cache
        tok, qid = self.credentials.get("flex_token"), self.credentials.get("query_id")
        if not tok or not qid:
            raise ReauthRequired("Flex token and query id are required")
        resp = self._get("SendRequest", {"t": tok, "q": qid})
        if resp.findtext("Status") != "Success":
            code = resp.findtext("ErrorCode") or ""
            if code in AUTH_ERRORS:
                raise ReauthRequired("IBKR Flex token expired or invalid")
            if code == "1018":
                raise RateLimited("IBKR throttled the request", 60)
            raise ConnectorError(f"IBKR Flex error {code}: {resp.findtext('ErrorMessage') or 'unknown'}")
        ref = resp.findtext("ReferenceCode")
        delay = 2.0
        for _ in range(10):
            self.sleep(delay)
            r = self.http.get(f"{BASE}/GetStatement", params={"t": tok, "q": ref, "v": "3"})
            r.raise_for_status()
            if "<FlexQueryResponse" in r.text:
                self._cache = FlexStatementParser(r.text)
                return self._cache
            el = ET.fromstring(r.text)
            code = el.findtext("ErrorCode") or ""
            if code == "1019":  # still generating
                delay = min(delay * 1.6, 20)
                continue
            if code in AUTH_ERRORS:
                raise ReauthRequired("IBKR Flex token expired or invalid")
            raise ConnectorError(f"IBKR Flex error {code}")
        raise ConnectorError("IBKR statement was not ready in time — try again shortly")

    def validate_connection(self):
        self._statement()

    def list_accounts(self):
        return self._statement().accounts()

    def fetch_balances(self, since=None):
        return self._statement().cash_balances()

    def fetch_holdings(self):
        return self._statement().holdings()

    def fetch_investment_activity(self, since=None):
        acts = self._statement().activity()
        return [a for a in acts if since is None or a.executed_at >= since]
