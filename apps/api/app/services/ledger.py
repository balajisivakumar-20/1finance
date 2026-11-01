"""In-memory read model of a user's snapshots for point-in-time valuation.

Loaded once per request; point lookups use bisect, so a 1-year daily history is O(days × accounts × log n).
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.fx import FxConverter, Rate
from app.finance.money import Money
from app.finance.networth import ASSET, LIABILITY, NetWorthResult, Position, compute_net_worth
from app.models import (
    Account,
    AccountBalanceSnapshot,
    Asset,
    AssetValuation,
    ExchangeRate,
    HoldingSnapshot,
    Liability,
    LiabilitySnapshot,
)

LIABILITY_ACCOUNT_TYPES = {"credit_card", "loan"}
ACCOUNT_BUCKET = {"checking": "bank", "savings": "bank", "cash": "cash", "fixed_deposit": "fixed_deposits",
                  "brokerage": "brokerage_cash", "investment": "brokerage_cash", "other": "other_assets"}
HOLDING_BUCKET = {"stock": "stocks", "etf": "etfs", "mutual_fund": "mutual_funds", "bond": "other_investments",
                  "other": "other_investments"}
ASSET_BUCKET = {"property": "other_assets", "fixed_deposit": "fixed_deposits", "cash": "cash", "vehicle": "other_assets",
                "other": "other_assets"}
STALE_AFTER = timedelta(days=3)


def load_fx(db: Session) -> FxConverter:
    rows = db.scalars(select(ExchangeRate)).all()
    return FxConverter([Rate(r.base_currency, r.quote_currency, r.rate, r.provider, r.effective_timestamp) for r in rows])


def end_of_day(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


@dataclass
class _Series:
    times: list[datetime]
    values: list


def _series(pairs: list[tuple[datetime, object]]) -> _Series:
    pairs.sort(key=lambda p: p[0])
    return _Series([p[0] for p in pairs], [p[1] for p in pairs])


def _at(s: _Series | None, at: datetime):
    if not s:
        return None
    i = bisect.bisect_right(s.times, at) - 1
    return (s.times[i], s.values[i]) if i >= 0 else None


class Ledger:
    def __init__(self, db: Session, user_id: int, account_ids: list[int] | None = None) -> None:
        self.db = db
        q = select(Account).where(Account.user_id == user_id, Account.status == "active")
        if account_ids:
            q = q.where(Account.id.in_(account_ids))
        self.accounts = {a.id: a for a in db.scalars(q)}
        ids = list(self.accounts)
        self.fx = load_fx(db)
        bal: dict[int, list] = defaultdict(list)
        for s in db.scalars(select(AccountBalanceSnapshot).where(AccountBalanceSnapshot.account_id.in_(ids))):
            bal[s.account_id].append((s.valuation_timestamp, s))
        self.balances = {k: _series(v) for k, v in bal.items()}
        hold: dict[int, dict[datetime, list]] = defaultdict(lambda: defaultdict(list))
        for h in db.scalars(select(HoldingSnapshot).where(HoldingSnapshot.account_id.in_(ids))):
            hold[h.account_id][h.valuation_timestamp].append(h)
        self.holdings = {k: _series(list(v.items())) for k, v in hold.items()}
        self.include_manual = account_ids is None
        self.assets, self.asset_vals = [], {}
        self.liabs, self.liab_vals = [], {}
        if self.include_manual:
            self.assets = list(db.scalars(select(Asset).where(Asset.user_id == user_id)))
            av: dict[int, list] = defaultdict(list)
            for v in db.scalars(select(AssetValuation).where(AssetValuation.asset_id.in_([a.id for a in self.assets]))):
                av[v.asset_id].append((end_of_day(v.valuation_date), v))
            self.asset_vals = {k: _series(v) for k, v in av.items()}
            self.liabs = list(db.scalars(select(Liability).where(Liability.user_id == user_id)))
            lv: dict[int, list] = defaultdict(list)
            for v in db.scalars(select(LiabilitySnapshot).where(LiabilitySnapshot.liability_id.in_([l.id for l in self.liabs]))):
                lv[v.liability_id].append((end_of_day(v.snapshot_date), v))
            self.liab_vals = {k: _series(v) for k, v in lv.items()}

    # ------------------------------------------------------------------
    def positions_at(self, at: datetime) -> tuple[list[Position], dict]:
        pos: list[Position] = []
        meta = {"stale_accounts": [], "price_types": set()}
        for a in self.accounts.values():
            if not a.counts_toward_net_worth:
                continue
            b = _at(self.balances.get(a.id), at)
            if b:
                ts, snap = b
                if at - ts > STALE_AFTER:
                    meta["stale_accounts"].append(a.id)
                if a.account_type in LIABILITY_ACCOUNT_TYPES:
                    pos.append(Position(f"acct:{a.id}", LIABILITY, a.account_type, Money(-snap.balance, snap.currency), a.is_demo))
                else:
                    pos.append(Position(f"acct:{a.id}", ASSET, ACCOUNT_BUCKET.get(a.account_type, "other_assets"),
                                        Money(snap.balance, snap.currency), a.is_demo))
            h = _at(self.holdings.get(a.id), at)
            if h:
                _, rows = h
                for r in rows:
                    meta["price_types"].add(r.price_type)
                    pos.append(Position(f"hold:{a.id}:{r.security_id}", ASSET,
                                        HOLDING_BUCKET.get(r.security.asset_class, "other_investments"),
                                        Money(r.market_value, r.currency), a.is_demo))
        for asset in self.assets:
            v = _at(self.asset_vals.get(asset.id), at)
            if v:
                pos.append(Position(f"asset:{asset.id}", ASSET, ASSET_BUCKET.get(asset.asset_type, "other_assets"),
                                    Money(v[1].valuation_amount, asset.currency), asset.is_demo, True))
        for l in self.liabs:
            v = _at(self.liab_vals.get(l.id), at)
            if v:
                pos.append(Position(f"liab:{l.id}", LIABILITY, l.liability_type, Money(v[1].outstanding_amount, l.currency), l.is_demo))
        return pos, meta

    def net_worth_at(self, at: datetime, base: str) -> tuple[NetWorthResult, dict]:
        pos, meta = self.positions_at(at)
        return compute_net_worth(pos, self.fx, base, at), meta

    def history(self, start: date, end: date, base: str, step_days: int = 1) -> list[dict]:
        out = []
        d = start
        while d <= end:
            at = end_of_day(d) if d < end else datetime.now(timezone.utc)
            r, _ = self.net_worth_at(at, base)
            out.append({"date": d.isoformat(), "assets": r.total_assets, "liabilities": r.total_liabilities, "net_worth": r.net_worth})
            d += timedelta(days=step_days)
        if out and out[-1]["date"] != end.isoformat():
            r, _ = self.net_worth_at(datetime.now(timezone.utc), base)
            out.append({"date": end.isoformat(), "assets": r.total_assets, "liabilities": r.total_liabilities, "net_worth": r.net_worth})
        return out

    def latest_balance(self, account_id: int):
        s = self.balances.get(account_id)
        return s.values[-1] if s and s.values else None

    def latest_holdings(self, account_id: int) -> list[HoldingSnapshot]:
        s = self.holdings.get(account_id)
        return s.values[-1] if s and s.values else []

    def holdings_at(self, account_id: int, at: datetime) -> list[HoldingSnapshot]:
        r = _at(self.holdings.get(account_id), at)
        return r[1] if r else []


def to_base(fx: FxConverter, amount: Decimal, currency: str, base: str, at: datetime) -> Decimal | None:
    from app.finance.fx import MissingRateError

    try:
        return fx.convert(Money(amount, currency), base, at).converted.amount
    except MissingRateError:
        return None
