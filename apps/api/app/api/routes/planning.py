"""Budgets, goals, manual assets/liabilities, analytics."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import base_currency, current_user
from app.api.fmt import m, pct
from app.core.db import get_db
from app.finance.cashflow import budget_status
from app.finance.money import ZERO, Money
from app.models import (
    Account,
    Asset,
    AssetValuation,
    Budget,
    Category,
    Goal,
    GoalContribution,
    Liability,
    LiabilitySnapshot,
    User,
)
from app.services import analytics
from app.services.ledger import Ledger, load_fx, to_base

router = APIRouter(tags=["planning"])


def _today() -> date:
    return datetime.now(timezone.utc).date()


# ------------------------------------------------------------------ budgets
@router.get("/budgets")
def budgets(month: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db),
            base: str = Depends(base_currency)):
    today = _today()
    ms = datetime.strptime(month, "%Y-%m").date() if month else today.replace(day=1)
    me = ms + relativedelta(months=1)
    fx = load_fx(db)
    s = analytics.period_summary(db, user.id, fx, base, ms, me)
    cmap = analytics.category_parent_map(db, user.id)
    cats = {c.id: c for c in db.scalars(select(Category))}
    items = []
    for b in db.scalars(select(Budget).where(Budget.user_id == user.id)):
        c = cats[b.category_id]
        spent = sum((v for slug, v in s.by_category.items() if slug == c.slug or cmap.get(slug, {}).get("parent") == c.slug), ZERO)
        budget_base = to_base(fx, b.amount, b.currency, base, datetime.now(timezone.utc)) or b.amount
        p, status = budget_status(spent, budget_base)
        items.append({"id": b.id, "category": {"id": c.id, "slug": c.slug, "name": c.name, "color": c.color, "icon": c.icon},
                      "amount": m(budget_base, base), "spent": m(spent, base), "remaining": m(budget_base - spent, base),
                      "percent": pct(p), "status": status})
    elapsed = ((min(today, me - timedelta(days=1)) - ms).days + 1) / ((me - ms).days)
    tb = sum((Decimal(i["amount"]) for i in items), ZERO)
    ts = sum((Decimal(i["spent"]) for i in items), ZERO)
    return {"currency": base, "month": ms.strftime("%Y-%m"), "month_elapsed_pct": pct(Decimal(str(elapsed * 100))),
            "totals": {"budget": m(tb, base), "spent": m(ts, base)},
            "items": sorted(items, key=lambda i: -(i["percent"] or 0))}


class BudgetIn(BaseModel):
    category_id: int
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)


@router.post("/budgets", status_code=201)
def create_budget(body: BudgetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category_id == body.category_id)):
        raise HTTPException(409, "A budget for this category already exists")
    b = Budget(user_id=user.id, category_id=body.category_id, amount=body.amount, currency=body.currency.upper())
    db.add(b)
    db.flush()
    return {"id": b.id}


class BudgetPatch(BaseModel):
    amount: Decimal = Field(gt=0)


@router.patch("/budgets/{bid}")
def update_budget(bid: int, body: BudgetPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Budget, bid)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "Budget not found")
    b.amount = body.amount
    return {"ok": True}


@router.delete("/budgets/{bid}")
def delete_budget(bid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Budget, bid)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "Budget not found")
    db.delete(b)
    return {"ok": True}


# ------------------------------------------------------------------ goals
@router.get("/goals")
def goals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = _today()
    fx = load_fx(db)
    out = []
    linked: dict[int, list[str]] = {}
    for g in db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at)):
        contribs = list(db.scalars(select(GoalContribution).where(GoalContribution.goal_id == g.id).order_by(GoalContribution.contribution_date)))
        cur = ZERO
        series, entries = [], []
        for c in contribs:
            cur += to_base(fx, c.amount, c.currency, g.target_currency, datetime.now(timezone.utc)) or ZERO
            series.append({"date": c.contribution_date, "amount": m(cur, g.target_currency)})
            entries.append({"id": c.id, "date": c.contribution_date, "amount": m(c.amount, c.currency), "currency": c.currency, "note": c.note})
        if g.linked_account_id:
            linked.setdefault(g.linked_account_id, []).append(g.goal_name)
        remaining = max(g.target_amount - cur, ZERO)
        eta = None
        if remaining == 0:
            eta = today
        elif g.monthly_contribution_plan and g.monthly_contribution_plan > 0:
            months = int((remaining / g.monthly_contribution_plan).to_integral_value(rounding="ROUND_CEILING"))
            eta = today + relativedelta(months=months)
        out.append({"id": g.id, "name": g.goal_name, "type": g.goal_type, "target": m(g.target_amount, g.target_currency),
                    "currency": g.target_currency, "target_date": g.target_date, "current": m(cur, g.target_currency),
                    "remaining": m(remaining, g.target_currency), "progress_pct": pct(min(cur / g.target_amount * 100, Decimal(100))),
                    "monthly_plan": m(g.monthly_contribution_plan, g.target_currency), "estimated_completion": eta,
                    "on_track": None if not (eta and g.target_date) else eta <= g.target_date,
                    "linked_account_id": g.linked_account_id, "history": series, "contributions": entries[::-1]})
    overlaps = [{"account_id": k, "goals": v} for k, v in linked.items() if len(v) > 1]
    return {"items": out, "overlaps": overlaps}


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal_type: str = "general"
    target_amount: Decimal = Field(gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    target_date: date | None = None
    monthly_plan: Decimal | None = Field(default=None, ge=0)
    linked_account_id: int | None = None


def _check_account(db: Session, user: User, account_id: int | None) -> None:
    if account_id:
        a = db.get(Account, account_id)
        if not a or a.user_id != user.id:
            raise HTTPException(422, "Unknown account")


def _own_goal(db: Session, user: User, gid: int) -> Goal:
    g = db.get(Goal, gid)
    if not g or g.user_id != user.id:
        raise HTTPException(404, "Goal not found")
    return g


def _own_contribution(db: Session, user: User, gid: int, cid: int) -> GoalContribution:
    _own_goal(db, user, gid)
    c = db.get(GoalContribution, cid)
    if not c or c.goal_id != gid:
        raise HTTPException(404, "Contribution not found")
    return c


@router.post("/goals", status_code=201)
def create_goal(body: GoalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _check_account(db, user, body.linked_account_id)
    g = Goal(user_id=user.id, goal_name=body.name, goal_type=body.goal_type, target_amount=body.target_amount,
             target_currency=body.currency.upper(), target_date=body.target_date, monthly_contribution_plan=body.monthly_plan,
             linked_account_id=body.linked_account_id)
    db.add(g)
    db.flush()
    return {"id": g.id}


class GoalPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    goal_type: str | None = None
    target_amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    target_date: date | None = None
    monthly_plan: Decimal | None = Field(default=None, ge=0)
    linked_account_id: int | None = None


@router.patch("/goals/{gid}")
def update_goal(gid: int, body: GoalPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _own_goal(db, user, gid)
    sent = body.model_fields_set
    if "name" in sent and body.name:
        g.goal_name = body.name
    if "goal_type" in sent and body.goal_type:
        g.goal_type = body.goal_type
    if "target_amount" in sent and body.target_amount:
        g.target_amount = body.target_amount
    if "currency" in sent and body.currency and body.currency.upper() != g.target_currency:
        # Amounts are logged by hand in the goal's currency, so a currency change relabels them rather than converting.
        g.target_currency = body.currency.upper()
        for c in db.scalars(select(GoalContribution).where(GoalContribution.goal_id == g.id)):
            c.currency = g.target_currency
    if "target_date" in sent:
        g.target_date = body.target_date
    if "monthly_plan" in sent:
        g.monthly_contribution_plan = body.monthly_plan
    if "linked_account_id" in sent:
        _check_account(db, user, body.linked_account_id)
        g.linked_account_id = body.linked_account_id
    return {"ok": True}


class ContributionIn(BaseModel):
    amount: Decimal
    on: date | None = None
    note: str | None = Field(default=None, max_length=200)


@router.post("/goals/{gid}/contributions", status_code=201)
def contribute(gid: int, body: ContributionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _own_goal(db, user, gid)
    if body.amount == 0:
        raise HTTPException(422, "Amount cannot be zero")
    c = GoalContribution(goal_id=g.id, amount=body.amount, currency=g.target_currency, contribution_date=body.on or _today(),
                         note=body.note or None)
    db.add(c)
    db.flush()
    return {"id": c.id}


class ContributionPatch(BaseModel):
    amount: Decimal | None = None
    on: date | None = None
    note: str | None = Field(default=None, max_length=200)


@router.patch("/goals/{gid}/contributions/{cid}")
def update_contribution(gid: int, cid: int, body: ContributionPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _own_contribution(db, user, gid, cid)
    sent = body.model_fields_set
    if "amount" in sent and body.amount is not None:
        if body.amount == 0:
            raise HTTPException(422, "Amount cannot be zero")
        c.amount = body.amount
    if "on" in sent and body.on:
        c.contribution_date = body.on
    if "note" in sent:
        c.note = body.note or None
    return {"ok": True}


@router.delete("/goals/{gid}/contributions/{cid}")
def delete_contribution(gid: int, cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_contribution(db, user, gid, cid))
    return {"ok": True}


@router.delete("/goals/{gid}")
def delete_goal(gid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_goal(db, user, gid))
    return {"ok": True}


# ------------------------------------------------------------------ manual assets & liabilities
@router.get("/assets-liabilities")
def assets_liabilities(user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    now = datetime.now(timezone.utc)
    fx = load_fx(db)
    assets, liabs = [], []
    for a in db.scalars(select(Asset).where(Asset.user_id == user.id)):
        v = db.scalar(select(AssetValuation).where(AssetValuation.asset_id == a.id).order_by(AssetValuation.valuation_date.desc()).limit(1))
        assets.append({"id": a.id, "name": a.asset_name, "type": a.asset_type, "currency": a.currency,
                       "value": m(v.valuation_amount, a.currency) if v else None,
                       "value_base": m(to_base(fx, v.valuation_amount, a.currency, base, now), base) if v else None,
                       "valuation_date": v.valuation_date if v else None, "valuation_source": v.valuation_source if v else None,
                       "method": a.valuation_method, "is_estimate": a.valuation_method == "manual_estimate", "notes": a.notes, "is_demo": a.is_demo})
    for l in db.scalars(select(Liability).where(Liability.user_id == user.id)):
        s = db.scalar(select(LiabilitySnapshot).where(LiabilitySnapshot.liability_id == l.id).order_by(LiabilitySnapshot.snapshot_date.desc()).limit(1))
        liabs.append({"id": l.id, "name": l.liability_name, "type": l.liability_type, "currency": l.currency,
                      "outstanding": m(s.outstanding_amount, l.currency) if s else None,
                      "outstanding_base": m(to_base(fx, s.outstanding_amount, l.currency, base, now), base) if s else None,
                      "as_of": s.snapshot_date if s else None, "interest_rate": l.interest_rate,
                      "payment_amount": m(l.payment_amount, l.currency), "payment_frequency": l.payment_frequency,
                      "next_payment_date": l.next_payment_date, "is_demo": l.is_demo})
    return {"currency": base, "assets": assets, "liabilities": liabs}


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    asset_type: str = Field(pattern="^(property|fixed_deposit|cash|vehicle|other)$")
    currency: str = Field(min_length=3, max_length=3)
    value: Decimal = Field(ge=0)
    valuation_date: date | None = None
    valuation_source: str = Field(default="manual estimate", max_length=64)
    notes: str | None = Field(default=None, max_length=1000)


@router.post("/assets", status_code=201)
def create_asset(body: AssetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = Asset(user_id=user.id, asset_name=body.name, asset_type=body.asset_type, currency=body.currency.upper(), notes=body.notes)
    db.add(a)
    db.flush()
    db.add(AssetValuation(asset_id=a.id, valuation_amount=body.value, valuation_date=body.valuation_date or _today(),
                          valuation_source=body.valuation_source))
    return {"id": a.id}


class LiabilityIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    liability_type: str = Field(pattern="^(personal_loan|education_loan|home_loan|credit_card|other)$")
    currency: str = Field(min_length=3, max_length=3)
    outstanding: Decimal = Field(ge=0)
    interest_rate: Decimal | None = Field(default=None, ge=0, le=100)
    payment_amount: Decimal | None = Field(default=None, ge=0)
    payment_frequency: str | None = None
    next_payment_date: date | None = None


@router.post("/liabilities", status_code=201)
def create_liability(body: LiabilityIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    l = Liability(user_id=user.id, liability_name=body.name, liability_type=body.liability_type, currency=body.currency.upper(),
                  interest_rate=body.interest_rate, payment_amount=body.payment_amount, payment_frequency=body.payment_frequency,
                  next_payment_date=body.next_payment_date)
    db.add(l)
    db.flush()
    db.add(LiabilitySnapshot(liability_id=l.id, outstanding_amount=body.outstanding, snapshot_date=_today()))
    return {"id": l.id}


class ValueUpdate(BaseModel):
    value: Decimal = Field(ge=0)


@router.post("/assets/{aid}/valuations")
def revalue_asset(aid: int, body: ValueUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Asset, aid)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Asset not found")
    db.add(AssetValuation(asset_id=a.id, valuation_amount=body.value, valuation_date=_today(), valuation_source="manual estimate"))
    return {"ok": True}


@router.post("/liabilities/{lid}/balance")
def update_liability(lid: int, body: ValueUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    l = db.get(Liability, lid)
    if not l or l.user_id != user.id:
        raise HTTPException(404, "Liability not found")
    db.add(LiabilitySnapshot(liability_id=l.id, outstanding_amount=body.value, snapshot_date=_today()))
    return {"ok": True}


# ------------------------------------------------------------------ analytics
@router.get("/analytics/cashflow")
def cashflow(months: int = Query(12, ge=1, le=60), user: User = Depends(current_user), db: Session = Depends(get_db),
             base: str = Depends(base_currency)):
    fx = load_fx(db)
    series = analytics.monthly_series(db, user.id, fx, base, months, _today())
    cmap = analytics.category_parent_map(db, user.id)
    out = []
    for s in series:
        groups = analytics.group_by_parent(s["by_category"], cmap)
        out.append({"month": s["month"], "income": m(s["income"], base), "expenses": m(s["expenses"], base), "net": m(s["net"], base),
                    "savings_rate": pct(s["savings_rate"]), "transfers_out": m(s["transfers_out"], base), "partial": s["partial"],
                    "categories": {g["slug"]: m(g["amount"], base) for g in groups}})
    full = [s for s in series if not s["partial"]]
    inc = sum((s["income"] for s in full), ZERO)
    exp = sum((s["expenses"] for s in full), ZERO)
    return {"currency": base, "months": out,
            "totals": {"income": m(inc, base), "expenses": m(exp, base), "savings": m(inc - exp, base),
                       "savings_rate": pct((inc - exp) / inc * 100) if inc > 0 else None, "full_months": len(full)},
            "definitions": {
                "income": "Salary, interest and other inflows. Excludes transfers between your accounts, refunds and dividends.",
                "expenses": "Spending and fees, net of refunds. Excludes transfers, investment purchases and pending items.",
                "savings": "Income − Expenses", "savings_rate": "Savings ÷ Income × 100 (undefined when income is zero)"}}


@router.get("/analytics/categories")
def categories(date_from: date | None = None, date_to: date | None = None, user: User = Depends(current_user),
               db: Session = Depends(get_db), base: str = Depends(base_currency)):
    today = _today()
    start = date_from or today.replace(day=1)
    end = (date_to or today) + timedelta(days=1)
    fx = load_fx(db)
    s = analytics.period_summary(db, user.id, fx, base, start, end)
    cmap = analytics.category_parent_map(db, user.id)
    groups = analytics.group_by_parent(s.by_category, cmap)
    detail = sorted(({"slug": k, "name": cmap.get(k, {}).get("name", k), "parent": cmap.get(k, {}).get("parent_name"),
                      "amount": m(v, base)} for k, v in s.by_category.items()), key=lambda r: -Decimal(r["amount"]))
    return {"currency": base, "period": [start, end - timedelta(days=1)], "total": m(s.expenses, base),
            "groups": [{**g, "amount": m(g["amount"], base), "share": pct(g["share"])} for g in groups], "detail": detail}


@router.get("/analytics/net-worth")
def net_worth_compare(period: str = Query("monthly", pattern="^(monthly|quarterly|annual)$"), user: User = Depends(current_user),
                      db: Session = Depends(get_db), base: str = Depends(base_currency)):
    ledger = Ledger(db, user.id)
    today = _today()
    step = {"monthly": relativedelta(months=1), "quarterly": relativedelta(months=3), "annual": relativedelta(years=1)}[period]
    n = {"monthly": 12, "quarterly": 5, "annual": 3}[period]
    out, prev = [], None
    for i in range(n - 1, -1, -1):
        d = today - step * i
        r, _ = ledger.net_worth_at(datetime.combine(d, datetime.max.time(), tzinfo=timezone.utc), base)
        out.append({"date": d, "net_worth": m(r.net_worth, base),
                    "change": m(r.net_worth - prev, base) if prev is not None else None})
        prev = r.net_worth
    return {"currency": base, "period": period, "points": out}


@router.get("/analytics/yearly")
def yearly(year: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    today = _today()
    y = year or today.year
    start, end = date(y, 1, 1), min(date(y + 1, 1, 1), today + timedelta(days=1))
    fx = load_fx(db)
    s = analytics.period_summary(db, user.id, fx, base, start, end)
    ledger = Ledger(db, user.id)
    nw0, _ = ledger.net_worth_at(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc), base)
    nw1, _ = ledger.net_worth_at(datetime.now(timezone.utc) if end > today else datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc), base)
    from app.models import InvestmentTransaction
    acct_ids = [a.id for a in db.scalars(select(Account).where(Account.user_id == user.id))]
    divs = sum((to_base(fx, x.amount, x.currency, base, x.execution_timestamp) or ZERO for x in db.scalars(
        select(InvestmentTransaction).where(InvestmentTransaction.account_id.in_(acct_ids or [-1]), InvestmentTransaction.activity_type == "dividend",
                                            InvestmentTransaction.execution_timestamp >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)))), ZERO)
    return {"currency": base, "year": y, "period": [start, end - timedelta(days=1)], "income": m(s.income, base),
            "expenses": m(s.expenses, base), "net_savings": m(s.savings, base), "savings_rate": pct(s.savings_rate),
            "investment_income": m(s.investment_income + divs, base), "net_worth_start": m(nw0.net_worth, base),
            "net_worth_end": m(nw1.net_worth, base), "net_worth_change": m(nw1.net_worth - nw0.net_worth, base),
            "coverage_note": "Net worth at the start of the year uses the earliest snapshots available if history begins later."}


__all__ = ["router", "Money"]
