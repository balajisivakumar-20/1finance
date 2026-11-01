from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import base_currency, current_user
from app.api.fmt import m, pct, qty
from app.api.routes.overview import RANGES
from app.core.db import get_db
from app.finance.money import ZERO
from app.finance.returns import HoldingPL, ValuationPoint, decompose_change, money_weighted_return, time_weighted_return
from app.models import Account, Connection, HoldingSnapshot, InvestmentTransaction, Security, User
from app.services.ledger import Ledger, end_of_day, to_base

router = APIRouter(prefix="/investments", tags=["investments"])
INVEST_TYPES = ("brokerage", "investment")


def _scope_accounts(db: Session, user: User, scope: str) -> list[int]:
    q = select(Account).where(Account.user_id == user.id, Account.account_type.in_(INVEST_TYPES), Account.status == "active")
    accts = list(db.scalars(q))
    if scope == "all":
        return [a.id for a in accts]
    if scope.startswith("account:"):
        aid = int(scope.split(":")[1])
        if aid not in {a.id for a in accts}:
            raise HTTPException(404, "Account not found")
        return [aid]
    if scope.startswith("institution:"):
        slug = scope.split(":", 1)[1]
        return [a.id for a in accts if a.connection and a.connection.institution.slug == slug]
    raise HTTPException(422, "scope must be all | institution:<slug> | account:<id>")


def _value_at(ledger: Ledger, ids: list[int], at: datetime, base: str) -> tuple[Decimal, Decimal, list[str]]:
    """(holdings value, brokerage cash) in base."""
    hv = cash = ZERO
    missing = []
    for aid in ids:
        for h in ledger.holdings_at(aid, at):
            v = to_base(ledger.fx, h.market_value, h.currency, base, at)
            if v is None:
                missing.append(h.currency)
            else:
                hv += v
        import bisect
        s = ledger.balances.get(aid)
        if s:
            i = bisect.bisect_right(s.times, at) - 1
            if i >= 0:
                b = s.values[i]
                v = to_base(ledger.fx, b.balance, b.currency, base, at)
                cash += v or ZERO
    return hv, cash, missing


@router.get("/summary")
def summary(scope: str = "all", user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    now = datetime.now(timezone.utc)
    ids = _scope_accounts(db, user, scope)
    ledger = Ledger(db, user.id, ids or [-1])
    mv = cb = ZERO
    price_types, stale = set(), False
    for aid in ids:
        for h in ledger.latest_holdings(aid):
            v, c = to_base(ledger.fx, h.market_value, h.currency, base, now), to_base(ledger.fx, h.cost_basis, h.currency, base, now)
            if v is None or c is None:
                continue
            mv, cb = mv + v, cb + c
            price_types.add(h.price_type)
            stale |= now - h.valuation_timestamp > timedelta(days=3)
    _, cash, _ = _value_at(ledger, ids, now, base)
    acts = list(db.scalars(select(InvestmentTransaction).where(InvestmentTransaction.account_id.in_(ids or [-1]))))
    realized = sum((to_base(ledger.fx, a.realized_pl, a.currency, base, a.execution_timestamp) or ZERO for a in acts if a.realized_pl), ZERO)
    dividends = sum((to_base(ledger.fx, a.amount, a.currency, base, a.execution_timestamp) or ZERO for a in acts if a.activity_type == "dividend"), ZERO)
    pl = HoldingPL(mv, cb)
    by_inst: dict[str, Decimal] = defaultdict(Decimal)
    for aid in ids:
        a = ledger.accounts[aid]
        name = a.connection.institution.name if a.connection else "Manual"
        for h in ledger.latest_holdings(aid):
            by_inst[name] += to_base(ledger.fx, h.market_value, h.currency, base, now) or ZERO
    return {
        "currency": base, "scope": scope, "as_of": now,
        "total_value": m(mv + cash, base), "holdings_value": m(mv, base), "cash": m(cash, base),
        "invested_capital": m(cb, base), "unrealized": m(pl.unrealized, base), "unrealized_pct": pct(pl.unrealized_pct),
        "realized": m(realized, base), "dividends": m(dividends, base),
        "cost_basis_note": "Cost basis converted at today's FX rate; unrealized P/L therefore includes currency effects.",
        "price_types": sorted(price_types), "stale": stale,
        "by_institution": [{"name": k, "value": m(v, base)} for k, v in by_inst.items()],
        "scopes": [{"value": "all", "label": "All investments"}]
        + [{"value": f"institution:{s}", "label": n} for s, n in sorted({(a.connection.institution.slug, a.connection.institution.name)
                                                                          for a in db.scalars(select(Account).where(Account.user_id == user.id, Account.account_type.in_(INVEST_TYPES), Account.status == "active")) if a.connection})]
        + [{"value": f"account:{a.id}", "label": a.nickname or a.account_name} for a in db.scalars(
            select(Account).where(Account.user_id == user.id, Account.account_type.in_(INVEST_TYPES), Account.status == "active"))],
    }


@router.get("/holdings")
def holdings(scope: str = "all", user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    now = datetime.now(timezone.utc)
    ids = _scope_accounts(db, user, scope)
    ledger = Ledger(db, user.id, ids or [-1])
    rows, total = [], ZERO
    for aid in ids:
        a = ledger.accounts[aid]
        for h in ledger.latest_holdings(aid):
            v = to_base(ledger.fx, h.market_value, h.currency, base, now)
            total += v or ZERO
            pl = HoldingPL(h.market_value, h.cost_basis)
            s: Security = h.security
            rows.append({"security_id": s.id, "account_id": aid, "name": s.name, "ticker": s.ticker, "isin": s.isin,
                         "asset_class": s.asset_class, "exchange": s.exchange, "country": s.country, "sector": s.sector,
                         "brokerage": a.connection.institution.name if a.connection else "Manual",
                         "quantity": qty(h.quantity), "average_price": m(h.average_price, h.currency),
                         "current_price": m(h.market_price, h.currency), "market_value": m(h.market_value, h.currency),
                         "cost_basis": m(h.cost_basis, h.currency), "unrealized": m(pl.unrealized, h.currency),
                         "unrealized_pct": pct(pl.unrealized_pct), "currency": h.currency,
                         "market_value_base": m(v, base), "_v": v or ZERO, "price_type": h.price_type,
                         "valuation_timestamp": h.valuation_timestamp,
                         "is_stale": now - h.valuation_timestamp > timedelta(days=3), "is_demo": a.is_demo})
    for r in rows:
        r["allocation_pct"] = pct(r.pop("_v") / total * 100) if total else None

    def group(key):
        agg: dict[str, Decimal] = defaultdict(Decimal)
        for r in rows:
            agg[r.get(key) or "Unknown"] += Decimal(r["market_value_base"] or 0)
        return [{"label": k, "value": v, "share": pct(v / total * 100) if total else None} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]

    return {"currency": base, "total": m(total, base), "items": sorted(rows, key=lambda r: -Decimal(r["market_value_base"] or 0)),
            "allocation": {"brokerage": group("brokerage"), "asset_class": group("asset_class"), "country": group("country"),
                           "currency": group("currency"), "sector": group("sector")}}


@router.get("/history")
def history(scope: str = "all", range: str = Query("1Y"), user: User = Depends(current_user), db: Session = Depends(get_db),
            base: str = Depends(base_currency)):
    now = datetime.now(timezone.utc)
    ids = _scope_accounts(db, user, scope)
    ledger = Ledger(db, user.id, ids or [-1])
    firsts = [s.times[0] for aid in ids for s in [ledger.holdings.get(aid)] if s and s.times]
    if not firsts:
        return {"currency": base, "points": [], "twr": None, "mwr": None, "decomposition": None}
    start = max(firsts[0].date() if range == "ALL" else (now - RANGES.get(range, RANGES["1Y"])).date(), min(firsts).date())
    flows_by_day: dict = defaultdict(Decimal)
    for a in db.scalars(select(InvestmentTransaction).where(InvestmentTransaction.account_id.in_(ids or [-1]),
                                                           InvestmentTransaction.activity_type.in_(("deposit", "withdrawal")))):
        v = to_base(ledger.fx, a.amount, a.currency, base, a.execution_timestamp)
        if v is not None:
            flows_by_day[a.execution_timestamp.date()] += v
    pts, vpoints = [], []
    d = start
    step = 1 if (now.date() - start).days <= 120 else 3
    pending_flow = ZERO
    while d <= now.date():
        at = end_of_day(d) if d < now.date() else now
        hv, cash, _ = _value_at(ledger, ids, at, base)
        flow = sum((v for k, v in flows_by_day.items() if (d - timedelta(days=step)) < k <= d), ZERO) if pts else ZERO
        pending_flow = flow
        pts.append({"date": d.isoformat(), "value": m(hv + cash, base), "holdings": m(hv, base), "cash": m(cash, base),
                    "net_flow": m(flow, base)})
        vpoints.append(ValuationPoint(d, hv + cash, pending_flow))
        d += timedelta(days=step)
    net_contrib = sum((v for k, v in flows_by_day.items() if start < k <= now.date()), ZERO)
    # approximate FX effect: start-of-period local values revalued at end-period rates
    fx_effect = ZERO
    s_at = end_of_day(start)
    for aid in ids:
        for h in ledger.holdings_at(aid, s_at):
            a0 = to_base(ledger.fx, h.market_value, h.currency, base, s_at)
            a1 = to_base(ledger.fx, h.market_value, h.currency, base, now)
            if a0 is not None and a1 is not None:
                fx_effect += a1 - a0
    dec = decompose_change(vpoints[0].value, vpoints[-1].value, net_contrib, fx_effect)
    return {"currency": base, "range": range, "points": pts,
            "twr": pct(time_weighted_return(vpoints)), "mwr": pct(money_weighted_return(vpoints)),
            "methods": {"twr": "Time-weighted (chain-linked between external cash flows)",
                        "mwr": "Money-weighted (annualized XIRR of deposits/withdrawals and ending value)"},
            "decomposition": {k: m(v, base) for k, v in dec.items()},
            "decomposition_note": "FX effect is approximated from start-of-period holdings revalued at current rates."}


@router.get("/holdings/{security_id}")
def holding_detail(security_id: int, account_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
                   base: str = Depends(base_currency)):
    a = db.get(Account, account_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Not found")
    sec = db.get(Security, security_id)
    if not sec:
        raise HTTPException(404, "Not found")
    snaps = list(db.scalars(select(HoldingSnapshot).where(HoldingSnapshot.account_id == account_id, HoldingSnapshot.security_id == security_id)
                            .order_by(HoldingSnapshot.valuation_timestamp)))
    if not snaps:
        raise HTTPException(404, "No holding")
    last = snaps[-1]
    acts = list(db.scalars(select(InvestmentTransaction).where(InvestmentTransaction.account_id == account_id,
                                                              InvestmentTransaction.security_id == security_id)
                           .order_by(InvestmentTransaction.execution_timestamp.desc()).limit(50)))
    pl = HoldingPL(last.market_value, last.cost_basis)
    return {
        "security": {"id": sec.id, "name": sec.name, "ticker": sec.ticker, "isin": sec.isin, "asset_class": sec.asset_class,
                     "exchange": sec.exchange, "currency": sec.trading_currency, "sector": sec.sector, "country": sec.country},
        "quantity": qty(last.quantity), "average_price": m(last.average_price, last.currency),
        "current_price": m(last.market_price, last.currency), "price_type": last.price_type,
        "valuation_timestamp": last.valuation_timestamp, "market_value": m(last.market_value, last.currency),
        "total_invested": m(last.cost_basis, last.currency), "unrealized": m(pl.unrealized, last.currency),
        "unrealized_pct": pct(pl.unrealized_pct), "currency": last.currency,
        "price_history": [{"date": s.valuation_timestamp.date().isoformat(), "price": m(s.market_price, s.currency)} for s in snaps],
        "activity": [{"date": x.execution_timestamp, "type": x.activity_type, "quantity": qty(x.quantity), "price": m(x.price, x.currency),
                      "amount": m(x.amount, x.currency), "fees": m(x.fees, x.currency), "currency": x.currency} for x in acts],
        "dividends_total": m(sum((x.amount for x in acts if x.activity_type == "dividend"), ZERO), last.currency),
    }
