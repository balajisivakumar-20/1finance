"""Cash-flow analytics and deterministic insights, built on app.finance."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finance.cashflow import CashflowSummary, Txn, summarize
from app.finance.fx import FxConverter
from app.finance.money import Money, pct_change
from app.models import Account, Category, Transaction

SUBSCRIPTION_SLUGS = {"streaming", "software", "memberships", "fitness"}


def month_start(d: date) -> date:
    return d.replace(day=1)


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def load_txns(db: Session, user_id: int, start: date, end: date) -> list[Txn]:
    """[start, end) — uses effective (user-overridden) type and category."""
    parent = {}
    cats = {c.id: c for c in db.scalars(select(Category).where((Category.user_id == user_id) | (Category.user_id.is_(None))))}
    for c in cats.values():
        parent[c.id] = cats[c.parent_category_id].slug if c.parent_category_id in cats else c.slug
    q = (select(Transaction.id, Transaction.transaction_date, Transaction.amount, Transaction.currency,
                func.coalesce(Transaction.user_type, Transaction.transaction_type),
                func.coalesce(Transaction.user_category_id, Transaction.category_id), Transaction.transaction_status)
         .join(Account, Account.id == Transaction.account_id)
         .where(Account.user_id == user_id, Transaction.transaction_date >= _dt(start), Transaction.transaction_date < _dt(end),
                Transaction.duplicate_status != "confirmed_duplicate"))
    out = []
    for tid, when, amt, cur, typ, cat_id, status in db.execute(q):
        out.append(Txn(str(tid), when, Money(amt, cur), typ, cats[cat_id].slug if cat_id in cats else None, status))
    return out


def category_parent_map(db: Session, user_id: int) -> dict[str, dict]:
    cats = {c.id: c for c in db.scalars(select(Category).where((Category.user_id == user_id) | (Category.user_id.is_(None))))}
    out = {}
    for c in cats.values():
        p = cats.get(c.parent_category_id)
        out[c.slug] = {"name": c.name, "parent": p.slug if p else c.slug, "parent_name": p.name if p else c.name,
                       "color": (p or c).color, "icon": (p or c).icon}
    return out


def period_summary(db: Session, user_id: int, fx: FxConverter, base: str, start: date, end: date) -> CashflowSummary:
    return summarize(load_txns(db, user_id, start, end), fx, base)


def group_by_parent(by_category: dict[str, Decimal], cmap: dict[str, dict]) -> list[dict]:
    agg: dict[str, Decimal] = defaultdict(Decimal)
    for slug, v in by_category.items():
        agg[cmap.get(slug, {}).get("parent", slug)] += v
    total = sum((v for v in agg.values() if v > 0), Decimal(0))
    rows = []
    for slug, v in sorted(agg.items(), key=lambda kv: -kv[1]):
        info = cmap.get(slug, {})
        rows.append({"slug": slug, "name": info.get("parent_name", slug.title()), "amount": v, "color": info.get("color"),
                     "icon": info.get("icon"), "share": (v / total * 100) if total and v > 0 else Decimal(0)})
    return rows


def monthly_series(db: Session, user_id: int, fx: FxConverter, base: str, months: int, today: date) -> list[dict]:
    start = month_start(today) - relativedelta(months=months - 1)
    txns = load_txns(db, user_id, start, month_start(today) + relativedelta(months=1))
    buckets: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        buckets[t.occurred_at.strftime("%Y-%m")].append(t)
    out = []
    for i in range(months):
        m = start + relativedelta(months=i)
        key = m.strftime("%Y-%m")
        s = summarize(buckets.get(key, []), fx, base)
        transfers = sum((abs(t.amount.amount) for t in buckets.get(key, []) if t.type == "transfer" and t.amount.amount < 0), Decimal(0))
        out.append({"month": key, "income": s.income, "expenses": s.expenses, "net": s.savings, "savings_rate": s.savings_rate,
                    "by_category": s.by_category, "transfers_out": transfers, "partial": m == month_start(today)})
    return out


def insights(db: Session, user_id: int, fx: FxConverter, base: str, today: date) -> list[dict]:
    """Deterministic, verifiable insights. Each carries its calculation period and the numbers used."""
    out: list[dict] = []
    cmap = category_parent_map(db, user_id)
    cur_start, prev_start = month_start(today), month_start(today) - relativedelta(months=1)
    # compare month-to-date with the same number of days last month (fair comparison)
    days = (today - cur_start).days + 1
    prev_end = min(prev_start + timedelta(days=days), cur_start)
    cur = period_summary(db, user_id, fx, base, cur_start, today + timedelta(days=1))
    prev = period_summary(db, user_id, fx, base, prev_start, prev_end)
    period = {"current": [cur_start.isoformat(), today.isoformat()],
              "previous": [prev_start.isoformat(), (prev_end - timedelta(days=1)).isoformat()]}
    if not load_txns(db, user_id, prev_start, cur_start):
        return [{"id": "coverage", "kind": "info", "title": "Not enough history yet",
                 "body": "Insights need at least one full previous month of transactions.", "period": period}]
    cg, pg = {r["slug"]: r for r in group_by_parent(cur.by_category, cmap)}, {r["slug"]: r for r in group_by_parent(prev.by_category, cmap)}
    for slug in ("food", "shopping", "transport", "entertainment"):
        c, p = cg.get(slug), pg.get(slug)
        if c and p and p["amount"] >= 20:
            ch = pct_change(c["amount"], p["amount"])
            if ch is not None and abs(ch) >= 10:
                out.append({"id": f"cat-{slug}", "kind": "positive" if ch < 0 else "attention",
                            "title": f"{c['name']} spending {'down' if ch < 0 else 'up'} {abs(ch):.0f}%",
                            "body": f"{c['name']} month-to-date vs the same {days} days last month.",
                            "values": {"current": c["amount"], "previous": p["amount"], "change_pct": ch}, "period": period})
    # subscriptions (last full month)
    last_full = period_summary(db, user_id, fx, base, prev_start, cur_start)
    subs = sum((v for k, v in last_full.by_category.items() if k in SUBSCRIPTION_SLUGS), Decimal(0))
    if subs > 0:
        out.append({"id": "subscriptions", "kind": "info", "title": "Recurring subscriptions",
                    "body": f"Streaming, software, memberships and fitness in {prev_start.strftime('%B')}.",
                    "values": {"current": subs}, "period": {"current": [prev_start.isoformat(), (cur_start - timedelta(days=1)).isoformat()]}})
    # savings rate: last full month vs month before
    m2 = period_summary(db, user_id, fx, base, prev_start - relativedelta(months=1), prev_start)
    if last_full.savings_rate is not None and m2.savings_rate is not None:
        diff = last_full.savings_rate - m2.savings_rate
        if abs(diff) >= 1:
            out.append({"id": "savings-rate", "kind": "positive" if diff > 0 else "attention",
                        "title": f"Savings rate {'improved' if diff > 0 else 'dropped'} to {last_full.savings_rate:.0f}%",
                        "body": f"{prev_start.strftime('%B')} vs {(prev_start - relativedelta(months=1)).strftime('%B')} "
                                f"({m2.savings_rate:.0f}%). Transfers and investments are excluded.",
                        "values": {"current": last_full.savings_rate, "previous": m2.savings_rate}, "period": period})
    # largest category this month
    if cg:
        top = max(cg.values(), key=lambda r: r["amount"])
        out.append({"id": "top-category", "kind": "info", "title": f"Largest spend: {top['name']}",
                    "body": f"{top['share']:.0f}% of this month's expenses so far.", "values": {"current": top["amount"]}, "period": period})
    if cur.missing_rates or cur.pending_excluded:
        out.append({"id": "coverage-warning", "kind": "info", "title": "Some data excluded",
                    "body": f"{cur.pending_excluded} pending transaction(s) not yet counted"
                            + (f"; missing FX rates for {', '.join(cur.missing_rates)}" if cur.missing_rates else "") + ".",
                    "period": period})
    return out
