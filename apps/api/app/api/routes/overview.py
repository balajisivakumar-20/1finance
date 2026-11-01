"""Aggregated dashboard endpoints (one round-trip per widget group; no full histories sent to the client)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import base_currency, current_user
from app.api.fmt import m, pct
from app.core.db import get_db
from app.finance.money import pct_change
from app.finance.networth import allocation_percentages
from app.models import Account, Category, Connection, ExchangeRate, Notification, Security, Transaction, User
from app.services import analytics
from app.services.ledger import Ledger
from app.services.serializers import account_out, txn_out

router = APIRouter(tags=["overview"])
RANGES = {"1M": relativedelta(months=1), "3M": relativedelta(months=3), "6M": relativedelta(months=6), "1Y": relativedelta(years=1)}
ALLOC_LABELS = {"bank": "Bank accounts", "cash": "Cash", "brokerage_cash": "Brokerage cash", "stocks": "Stocks", "etfs": "ETFs",
                "mutual_funds": "Mutual funds", "fixed_deposits": "Fixed deposits", "other_investments": "Other investments",
                "other_assets": "Other assets"}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _range_start(ledger: Ledger, rng: str) -> date:
    today = _today()
    if rng == "ALL":
        firsts = [s.times[0] for s in list(ledger.balances.values()) + list(ledger.holdings.values()) if s.times]
        return min(firsts).date() if firsts else today
    if rng not in RANGES:
        raise HTTPException(422, "range must be one of 1M, 3M, 6M, 1Y, ALL")
    return today - RANGES[rng]


def fx_meta(db: Session) -> dict:
    row = db.execute(select(ExchangeRate.provider, func.max(ExchangeRate.effective_timestamp)).group_by(ExchangeRate.provider)).first()
    return {"provider": row[0], "as_of": row[1]} if row else None


@router.get("/dashboard/summary")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    now = datetime.now(timezone.utc)
    today = now.date()
    ledger = Ledger(db, user.id)
    nw, meta = ledger.net_worth_at(now, base)
    prev, _ = ledger.net_worth_at(now - relativedelta(months=1), base)
    alloc_pct = allocation_percentages(nw.allocation)
    # current month cash flow vs same days of previous month
    ms = today.replace(day=1)
    cur = analytics.period_summary(db, user.id, ledger.fx, base, ms, today + timedelta(days=1))
    pms = ms - relativedelta(months=1)
    days = (today - ms).days + 1
    prv = analytics.period_summary(db, user.id, ledger.fx, base, pms, min(pms + timedelta(days=days), ms))
    prv_full = analytics.period_summary(db, user.id, ledger.fx, base, pms, ms)
    conns = {c.id: c for c in db.scalars(select(Connection).where(Connection.user_id == user.id))}
    last_sync = max((c.last_successful_sync for c in conns.values() if c.last_successful_sync), default=None)
    accounts = [account_out(a, ledger, conns.get(a.connection_id), base, now) for a in ledger.accounts.values()]
    return {
        "currency": base,
        "as_of": now,
        "net_worth": {
            "value": m(nw.net_worth, base),
            "previous": m(prev.net_worth, base),
            "change": m(nw.net_worth - prev.net_worth, base),
            "change_pct": pct(pct_change(nw.net_worth, prev.net_worth)),
            "comparison": "vs 1 month ago",
        },
        "assets": {"value": m(nw.total_assets, base), "change": m(nw.total_assets - prev.total_assets, base),
                   "change_pct": pct(pct_change(nw.total_assets, prev.total_assets))},
        "liabilities": {"value": m(nw.total_liabilities, base), "change": m(nw.total_liabilities - prev.total_liabilities, base),
                        "change_pct": pct(pct_change(nw.total_liabilities, prev.total_liabilities))},
        "income_month": {"value": m(cur.income, base), "previous_same_period": m(prv.income, base),
                         "change_pct": pct(pct_change(cur.income, prv.income)) if days >= 5 else None, "period": [ms, today],
                         "last_month_total": m(prv_full.income, base)},
        "expenses_month": {"value": m(cur.expenses, base), "previous_same_period": m(prv.expenses, base),
                           "change_pct": pct(pct_change(cur.expenses, prv.expenses)) if days >= 5 else None, "period": [ms, today],
                           "pending_excluded": cur.pending_excluded, "last_month_total": m(prv_full.expenses, base)},
        "allocation": [
            {"key": k, "label": ALLOC_LABELS.get(k, k.replace("_", " ").title()), "value": m(v, base), "share": pct(alloc_pct.get(k))}
            for k, v in sorted(nw.allocation.items(), key=lambda kv: -kv[1]) if v != 0
        ],
        "accounts": sorted(accounts, key=lambda a: -(float(a["balance_base"] or 0))),
        "last_sync": last_sync,
        "data_quality": {
            "includes_demo": nw.includes_demo,
            "includes_estimates": nw.includes_estimates,
            "missing_rates": nw.missing_rates,
            "stale_accounts": meta["stale_accounts"],
            "price_types": sorted(meta["price_types"]),
        },
        "fx": fx_meta(db),
    }


@router.get("/dashboard/history")
def history(range: str = Query("6M"), user: User = Depends(current_user), db: Session = Depends(get_db),
            base: str = Depends(base_currency)):
    ledger = Ledger(db, user.id)
    start = _range_start(ledger, range)
    span = (_today() - start).days
    step = 1 if span <= 120 else 3 if span <= 400 else 7
    pts = ledger.history(start, _today(), base, step)
    change = pts[-1]["net_worth"] - pts[0]["net_worth"] if len(pts) > 1 else None
    return {"currency": base, "range": range, "step_days": step,
            "change": m(change, base) if change is not None else None,
            "change_pct": pct(pct_change(pts[-1]["net_worth"], pts[0]["net_worth"])) if len(pts) > 1 else None,
            "points": [{"date": p["date"], "net_worth": m(p["net_worth"], base), "assets": m(p["assets"], base),
                        "liabilities": m(p["liabilities"], base)} for p in pts]}


@router.get("/dashboard/spending")
def spending(period: str = Query("this_month", pattern="^(this_month|last_month)$"), user: User = Depends(current_user),
             db: Session = Depends(get_db), base: str = Depends(base_currency)):
    from app.services.ledger import load_fx

    today = _today()
    fx = load_fx(db)
    if period == "this_month":
        start, end = today.replace(day=1), today + timedelta(days=1)
    else:
        end = today.replace(day=1)
        start = end - relativedelta(months=1)
    s = analytics.period_summary(db, user.id, fx, base, start, end)
    rows = analytics.group_by_parent(s.by_category, analytics.category_parent_map(db, user.id))
    return {"currency": base, "period": [start, end - timedelta(days=1)], "label": period, "total": m(s.expenses, base),
            "categories": [{**r, "amount": m(r["amount"], base), "share": pct(r["share"])} for r in rows]}


@router.get("/insights")
def get_insights(user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    from app.services.ledger import load_fx

    items = analytics.insights(db, user.id, load_fx(db), base, _today())
    for it in items:
        if "values" in it:
            it["unit"] = "percent" if it["id"] == "savings-rate" else "money"
            it["values"] = {k: (pct(v) if k.endswith("_pct") or it["unit"] == "percent" else m(v, base))
                            for k, v in it["values"].items()}
    return {"currency": base, "items": items}


@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(30))
    return [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "read": n.read_at is not None, "created_at": n.created_at}
            for n in rows]


@router.post("/notifications/read-all")
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))):
        n.read_at = now
    return {"ok": True}


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=80), user: User = Depends(current_user), db: Session = Depends(get_db)):
    like = f"%{q.lower()}%"
    accts = db.scalars(select(Account).where(Account.user_id == user.id,
                                             or_(func.lower(Account.account_name).like(like), func.lower(Account.nickname).like(like))).limit(5))
    txns = db.scalars(select(Transaction).join(Account).where(
        Account.user_id == user.id,
        or_(func.lower(Transaction.raw_description).like(like), func.lower(Transaction.merchant_name).like(like)))
        .order_by(Transaction.transaction_date.desc()).limit(8))
    cats = db.scalars(select(Category).where(or_(Category.user_id == user.id, Category.user_id.is_(None)),
                                             func.lower(Category.name).like(like)).limit(5))
    secs = db.scalars(select(Security).where(or_(func.lower(Security.ticker).like(like), func.lower(Security.name).like(like))).limit(5))
    reports = [r for r in ("Monthly summary", "Annual summary", "Transactions", "Investment holdings", "Net worth") if q.lower() in r.lower()]
    return {
        "accounts": [{"id": a.id, "label": a.nickname or a.account_name, "type": a.account_type} for a in accts],
        "transactions": [txn_out(t, mask=True) for t in txns],
        "categories": [{"id": c.id, "label": c.name, "slug": c.slug} for c in cats],
        "investments": [{"id": s.id, "label": s.name, "ticker": s.ticker} for s in secs],
        "reports": [{"label": r} for r in reports],
    }
