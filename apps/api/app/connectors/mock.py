"""DEMO connectors. Deterministic, clearly-labeled synthetic data for development.

Every record produced here is persisted with source="mock" and is_demo=True, and the UI shows a "Demo data"
badge. These connectors are never registered when ONEFINANCE_ALLOW_MOCK_CONNECTORS=false (production).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from .base import (
    AccountData,
    BalanceData,
    Capability,
    ConnectorInfo,
    FinancialConnector,
    HoldingData,
    InvestmentActivityData,
    SecurityData,
    TransactionData,
)

D = Decimal
HISTORY_DAYS = 400


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _c(x: float | Decimal) -> Decimal:
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def _days(end: datetime, n: int = HISTORY_DAYS):
    start = (end - timedelta(days=n)).replace(hour=9)
    for i in range(n + 1):
        d = start + timedelta(days=i)
        if d.date() == end.date():
            d = min(d, end - timedelta(minutes=5))  # never generate future-dated records
        yield d


# ---------------------------------------------------------------- Revolut (bank)
class MockRevolut(FinancialConnector):
    info = ConnectorInfo(
        key="mock_revolut",
        institution_slug="revolut",
        display_name="Revolut (demo)",
        auth_method="mock",
        capabilities=frozenset({Capability.ACCOUNTS, Capability.BALANCES, Capability.BALANCE_HISTORY,
                                Capability.TRANSACTIONS, Capability.HISTORICAL_BACKFILL}),
        is_mock=True,
        notes="Synthetic data. Real Revolut access requires a licensed AISP/aggregator or a statement import.",
    )
    CURRENT, VAULT = "DEMO-REV-EUR-7731", "DEMO-REV-VAULT-2205"

    def validate_connection(self) -> None:
        return None

    def list_accounts(self) -> list[AccountData]:
        return [
            AccountData(self.CURRENT, "Revolut Current", "checking", "EUR"),
            AccountData(self.VAULT, "Savings Vault", "savings", "EUR"),
        ]

    def _ledger(self) -> list[TransactionData]:
        rng = random.Random(1904)
        end = _now()
        out: list[TransactionData] = []
        n = 0

        def add(day, desc, amt, typ, merchant=None, acct=None, status="posted"):
            nonlocal n
            n += 1
            out.append(TransactionData(acct or self.CURRENT, f"rev-{n:06d}", day, desc, _c(amt), "EUR", typ,
                                       merchant, status, day + timedelta(hours=20), {"demo": True}))

        groceries = ["TESCO STORES 3321", "LIDL IRELAND GMBH", "ALDI STORES DUBLIN", "DUNNES STORES", "SUPERVALU RANELAGH"]
        dining = ["BUNSEN BURGERS", "PIZZA EMPIRE", "SUSHI KING DAME ST", "NANDOS DUNDRUM", "BISTRO ELLA"]
        for day in _days(end):
            d, wd = day.day, day.weekday()
            if d == 25:
                add(day, "ACME TECHNOLOGIES LTD SALARY", 4850, "income", "Acme Technologies")
            if d == 1:
                add(day, "RENT - RATHMINES LANDLORD", -1850, "expense", "Landlord")
                add(day, "To Savings Vault", -600, "transfer", acct=self.CURRENT)
                add(day, "From Revolut Current", 600, "transfer", acct=self.VAULT)
            if d == 26:
                add(day, "Transfer to Interactive Brokers", -800, "transfer", "Interactive Brokers")
            if d == 3:
                add(day, "SPOTIFY P3F1A2", -10.99, "expense", "Spotify")
                add(day, "NETFLIX.COM", -15.99, "expense", "Netflix")
            if d == 8:
                add(day, "GITHUB INC", -9.20, "expense", "GitHub")
                add(day, "APPLE.COM/BILL ICLOUD", -2.99, "expense", "Apple iCloud")
            if d == 12:
                add(day, "ELECTRIC IRELAND DD", -rng.uniform(70, 125), "expense", "Electric Ireland")
                add(day, "VIRGIN MEDIA IRELAND", -55, "expense", "Virgin Media")
            if d == 15:
                add(day, "VODAFONE IRELAND", -25, "expense", "Vodafone")
                add(day, "FLYEFIT MEMBERSHIP", -29.99, "expense", "Flyefit")
            if wd in (2, 6):
                add(day, rng.choice(groceries), -rng.uniform(28, 115), "expense")
            if wd in (4, 5) and rng.random() < 0.7:
                add(day, rng.choice(dining), -rng.uniform(18, 78), "expense")
            if wd < 5 and rng.random() < 0.45:
                add(day, rng.choice(["INSOMNIA COFFEE", "BUTLERS CHOCOLATE CAFE", "COSTA COFFEE"]), -rng.uniform(3.2, 5.8), "expense")
            if wd == 0:
                add(day, "LEAP CARD TOP UP", -20, "expense", "TFI Leap Card")
            if rng.random() < 0.06:
                add(day, rng.choice(["AMAZON EU SARL", "IKEA DUBLIN", "PENNEYS MARY ST", "ZARA GRAFTON ST"]), -rng.uniform(15, 140), "expense")
            if rng.random() < 0.04:
                add(day, "UBER *TRIP", -rng.uniform(9, 32), "expense", "Uber")
            if rng.random() < 0.02:
                add(day, "BOOTS PHARMACY", -rng.uniform(6, 40), "expense", "Boots")
            if rng.random() < 0.012:
                add(day, "ODEON CINEMAS", -rng.uniform(12, 28), "expense", "Odeon")
            if d == 18 and day.month in (3, 7, 10, 12):
                add(day, "RYANAIR DAC", -rng.uniform(80, 260), "expense", "Ryanair")
                add(day + timedelta(days=1), "BOOKING.COM HOTEL", -rng.uniform(180, 520), "expense", "Booking.com")
            if d == 20 and day.month in (4, 9):
                add(day, "AMAZON EU SARL REFUND", rng.uniform(20, 60), "refund", "Amazon")
            if d == 28:
                add(day, "Savings interest", 600 * 0.0225 / 12 * (1 + (day.month % 5) * 0.4), "interest", acct=self.VAULT)
        # last couple of days pending
        cutoff = end - timedelta(days=1)
        return [TransactionData(**{**t.__dict__, "status": "pending", "posted_at": None}) if t.occurred_at > cutoff
                and t.type_hint == "expense" else t for t in out]

    def fetch_transactions(self, since=None):
        txns = self._ledger()
        return [t for t in txns if since is None or t.occurred_at >= since]

    def fetch_balances(self, since=None):
        opening = {self.CURRENT: D("5200"), self.VAULT: D("8500")}
        bal = dict(opening)
        txns = sorted(self._ledger(), key=lambda t: t.occurred_at)
        out: list[BalanceData] = []
        end = _now()
        i = 0
        for day in _days(end):
            eod = day.replace(hour=23)
            while i < len(txns) and txns[i].occurred_at <= eod:
                if txns[i].status == "posted":
                    bal[txns[i].external_account_ref] += txns[i].amount
                i += 1
            if day.weekday() == 6 or day.date() == end.date():
                for ref, b in bal.items():
                    ts = end if day.date() == end.date() else eod
                    if since is None or ts >= since:
                        out.append(BalanceData(ref, b, "EUR", ts, b))
        return out


# ---------------------------------------------------------------- price paths
@dataclass(frozen=True)
class _Sec:
    data: SecurityData
    start_price: float
    drift: float
    vol: float


def _price_path(sec: _Sec, seed: int, end: datetime) -> dict[str, Decimal]:
    rng = random.Random(seed)
    p = sec.start_price
    out = {}
    for day in _days(end):
        out[day.date().isoformat()] = _c(p)
        p *= math.exp(sec.drift / 365 + sec.vol / math.sqrt(365) * rng.gauss(0, 1))
    return out


# ---------------------------------------------------------------- Interactive Brokers
IBKR_SECS = [
    _Sec(SecurityData("VWCE", "Vanguard FTSE All-World UCITS ETF (Acc)", "etf", "EUR", "IE00BK5BQT80", "XETRA", "IE", "Diversified"), 112.0, 0.10, 0.13),
    _Sec(SecurityData("CSPX", "iShares Core S&P 500 UCITS ETF (Acc)", "etf", "USD", "IE00B5BMR087", "LSE", "IE", "Diversified"), 560.0, 0.12, 0.15),
    _Sec(SecurityData("AAPL", "Apple Inc.", "stock", "USD", "US0378331005", "NASDAQ", "US", "Technology"), 210.0, 0.14, 0.26),
    _Sec(SecurityData("MSFT", "Microsoft Corp.", "stock", "USD", "US5949181045", "NASDAQ", "US", "Technology"), 420.0, 0.12, 0.22),
    _Sec(SecurityData("ASML", "ASML Holding N.V.", "stock", "EUR", "NL0010273215", "AEB", "NL", "Technology"), 690.0, 0.08, 0.32),
]


class MockIBKR(FinancialConnector):
    info = ConnectorInfo(
        key="mock_ibkr",
        institution_slug="interactive-brokers",
        display_name="Interactive Brokers (demo)",
        auth_method="mock",
        capabilities=frozenset({Capability.ACCOUNTS, Capability.BALANCES, Capability.BALANCE_HISTORY,
                                Capability.HOLDINGS, Capability.INVESTMENT_ACTIVITY, Capability.HISTORICAL_BACKFILL}),
        is_mock=True,
        notes="Synthetic data. Real sync uses the IBKR Flex Web Service (token + query id).",
    )
    ACCT = "DEMO-U4821"
    INITIAL = {"VWCE": D(120), "CSPX": D(14), "AAPL": D(25), "MSFT": D(12), "ASML": D(6)}
    COST = {"VWCE": D("98.40"), "CSPX": D("455.10"), "AAPL": D("162.30"), "MSFT": D("318.75"), "ASML": D("612.00")}

    def validate_connection(self):
        return None

    def list_accounts(self):
        return [AccountData(self.ACCT, "IBKR Individual", "brokerage", "EUR")]

    def _simulate(self):
        end = _now()
        prices = {s.data.ticker: _price_path(s, 77 + i, end) for i, s in enumerate(IBKR_SECS)}
        qty = dict(self.INITIAL)
        cost = {k: self.COST[k] * qty[k] for k in qty}
        cash = D("1250")
        acts: list[InvestmentActivityData] = []
        holdings_hist: list[HoldingData] = []
        cash_hist: list[BalanceData] = []
        by_t = {s.data.ticker: s.data for s in IBKR_SECS}
        n = 0
        for day in _days(end):
            key = day.date().isoformat()
            if day.day == 27:  # deposit lands the day after the Revolut transfer
                n += 1
                acts.append(InvestmentActivityData(self.ACCT, f"ib-{n}", "deposit", D(800), "EUR", day))
                cash += 800
                px = prices["VWCE"][key]
                q = (D(700) / px).quantize(D("0.0001"))
                n += 1
                acts.append(InvestmentActivityData(self.ACCT, f"ib-{n}", "buy", -(q * px + D("1.25")), "EUR", day + timedelta(hours=2),
                                                   by_t["VWCE"], q, px, D("1.25")))
                cash -= q * px + D("1.25")
                qty["VWCE"] += q
                cost["VWCE"] += q * px + D("1.25")
            if day.day == 14 and day.month in (2, 5, 8, 11):
                for t, per in (("AAPL", D("0.26")), ("MSFT", D("0.83"))):
                    n += 1
                    amt = qty[t] * per * D("0.85")  # after 15% withholding
                    acts.append(InvestmentActivityData(self.ACCT, f"ib-{n}", "dividend", _c(amt), "USD", day, by_t[t]))
                    cash += amt * D("0.92")  # credited in base after FX (demo simplification)
            if day.weekday() == 6 or day.date() == end.date():
                ts = end if day.date() == end.date() else day.replace(hour=23)
                for s in IBKR_SECS:
                    t = s.data.ticker
                    holdings_hist.append(HoldingData(self.ACCT, s.data, qty[t], cost[t] / qty[t], prices[t][key], s.data.currency, ts,
                                                     "delayed" if ts == end else "close"))
                cash_hist.append(BalanceData(self.ACCT, _c(cash), "EUR", ts, _c(cash)))
        return holdings_hist, cash_hist, acts

    def fetch_holdings(self):
        h, _, _ = self._simulate()
        last = max(x.as_of for x in h)
        return [x for x in h if x.as_of == last]

    def fetch_holdings_history(self, since=None):
        h, _, _ = self._simulate()
        return [x for x in h if since is None or x.as_of >= since]

    def fetch_balances(self, since=None):  # brokerage *cash* balance only — holdings are valued separately
        _, c, _ = self._simulate()
        return [x for x in c if since is None or x.as_of >= since]

    def fetch_investment_activity(self, since=None):
        _, _, a = self._simulate()
        return [x for x in a if since is None or x.executed_at >= since]


# ---------------------------------------------------------------- Groww
GROWW_SECS = [
    _Sec(SecurityData("RELIANCE", "Reliance Industries Ltd", "stock", "INR", "INE002A01018", "NSE", "IN", "Energy"), 2850.0, 0.10, 0.24),
    _Sec(SecurityData("INFY", "Infosys Ltd", "stock", "INR", "INE009A01021", "NSE", "IN", "Technology"), 1520.0, 0.09, 0.25),
    _Sec(SecurityData("HDFCBANK", "HDFC Bank Ltd", "stock", "INR", "INE040A01034", "NSE", "IN", "Financials"), 1610.0, 0.08, 0.2),
    _Sec(SecurityData("TCS", "Tata Consultancy Services Ltd", "stock", "INR", "INE467B01029", "NSE", "IN", "Technology"), 3900.0, 0.07, 0.22),
    _Sec(SecurityData("NIFTYBEES", "Nippon India ETF Nifty 50 BeES", "etf", "INR", "INF204KB14I2", "NSE", "IN", "Diversified"), 255.0, 0.11, 0.15),
]


class MockGroww(FinancialConnector):
    info = ConnectorInfo(
        key="mock_groww",
        institution_slug="groww",
        display_name="Groww (demo)",
        auth_method="mock",
        # Mirrors the real Trade API: holdings + cash only; no transaction history, no mutual funds.
        capabilities=frozenset({Capability.ACCOUNTS, Capability.BALANCES, Capability.HOLDINGS, Capability.BALANCE_HISTORY}),
        is_mock=True,
        notes="Synthetic data. Mutual funds & FDs: manual import available.",
    )
    ACCT = "DEMO-GRW-DEMAT"
    QTY = {"RELIANCE": D(40), "INFY": D(60), "HDFCBANK": D(55), "TCS": D(18), "NIFTYBEES": D(400)}
    AVG = {"RELIANCE": D("2410.50"), "INFY": D("1385.00"), "HDFCBANK": D("1502.20"), "TCS": D("3420.00"), "NIFTYBEES": D("221.40")}

    def validate_connection(self):
        return None

    def list_accounts(self):
        return [AccountData(self.ACCT, "Groww Stocks", "brokerage", "INR")]

    def _hist(self):
        end = _now()
        prices = {s.data.ticker: _price_path(s, 300 + i, end) for i, s in enumerate(GROWW_SECS)}
        out = []
        for day in _days(end):
            if day.weekday() == 6 or day.date() == end.date():
                ts = end if day.date() == end.date() else day.replace(hour=23)
                for s in GROWW_SECS:
                    t = s.data.ticker
                    out.append(HoldingData(self.ACCT, s.data, self.QTY[t], self.AVG[t], prices[t][day.date().isoformat()],
                                           "INR", ts, "delayed" if ts == end else "close"))
        return out

    def fetch_holdings(self):
        h = self._hist()
        last = max(x.as_of for x in h)
        return [x for x in h if x.as_of == last]

    def fetch_holdings_history(self, since=None):
        return [x for x in self._hist() if since is None or x.as_of >= since]

    def fetch_balances(self, since=None):
        end = _now()
        return [BalanceData(self.ACCT, D("18450.00"), "INR", end, D("18450.00"))]
