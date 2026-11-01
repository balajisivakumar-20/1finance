from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import base_currency, current_user
from app.categorization.engine import merchant_key
from app.core.db import get_db
from app.finance.money import Money
from app.finance.reconcile import TransferLeg, find_transfer_pairs
from app.models import Account, CategorizationRule, Category, Connection, Transaction, User
from app.services.ledger import load_fx, to_base
from app.services.serializers import txn_out

router = APIRouter(tags=["transactions"])
TYPES = {"income", "expense", "refund", "transfer", "investment_buy", "investment_sell", "dividend", "interest", "fee",
         "withdrawal", "deposit"}
SORTS = {"date": Transaction.transaction_date, "amount": Transaction.amount, "description": Transaction.raw_description}


def _cats(db: Session, user_id: int) -> dict[int, Category]:
    return {c.id: c for c in db.scalars(select(Category).where(or_(Category.user_id == user_id, Category.user_id.is_(None))))}


def _own_txn(db: Session, user: User, tid: int) -> Transaction:
    t = db.get(Transaction, tid, options=[joinedload(Transaction.account)])
    if not t or t.account.user_id != user.id:
        raise HTTPException(404, "Transaction not found")
    return t


@router.get("/transactions")
def list_transactions(
    user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency),
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    q: str | None = Query(None, max_length=80), account_id: list[int] = Query(default=[]),
    institution: str | None = None, category: list[str] = Query(default=[]), type: list[str] = Query(default=[]),
    currency: str | None = None, status: str | None = None, date_from: date | None = None, date_to: date | None = None,
    min_amount: Decimal | None = None, max_amount: Decimal | None = None, review: bool = False,
    sort: str = "date", order: str = "desc",
):
    cats = _cats(db, user.id)
    eff_cat = func.coalesce(Transaction.user_category_id, Transaction.category_id)
    eff_type = func.coalesce(Transaction.user_type, Transaction.transaction_type)
    qy = select(Transaction).join(Account).where(Account.user_id == user.id)
    if q:
        like = f"%{q.lower()}%"
        qy = qy.where(or_(func.lower(Transaction.raw_description).like(like), func.lower(Transaction.merchant_name).like(like),
                          func.lower(Transaction.user_notes).like(like)))
    if account_id:
        qy = qy.where(Transaction.account_id.in_(account_id))
    if institution:
        qy = qy.join(Connection, Connection.id == Account.connection_id).where(Connection.connector.contains(institution))
    if category:
        slugs = set(category)
        ids = [c.id for c in cats.values() if c.slug in slugs or (c.parent_category_id in cats and cats[c.parent_category_id].slug in slugs)]
        qy = qy.where(eff_cat.in_(ids))
    if type:
        qy = qy.where(eff_type.in_([t for t in type if t in TYPES]))
    if currency:
        qy = qy.where(Transaction.currency == currency.upper())
    if status:
        qy = qy.where(Transaction.transaction_status == status)
    if date_from:
        qy = qy.where(Transaction.transaction_date >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        qy = qy.where(Transaction.transaction_date <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if min_amount is not None:
        qy = qy.where(func.abs(Transaction.amount) >= min_amount)
    if max_amount is not None:
        qy = qy.where(func.abs(Transaction.amount) <= max_amount)
    if review:
        qy = qy.where(or_(Transaction.duplicate_status == "possible_duplicate", Transaction.transfer_group.like("suggested:%")))
    total = db.scalar(select(func.count()).select_from(qy.subquery()))
    col = SORTS.get(sort, Transaction.transaction_date)
    qy = qy.order_by(col.asc() if order == "asc" else col.desc(), Transaction.id.desc())
    rows = db.scalars(qy.options(joinedload(Transaction.account).joinedload(Account.connection).joinedload(Connection.institution))
                      .offset((page - 1) * page_size).limit(page_size)).all()
    fx = load_fx(db)
    return {"total": total, "page": page, "page_size": page_size, "currency": base,
            "items": [txn_out(t, cats, base, fx) for t in rows]}


@router.get("/transactions/{tid}")
def get_txn(tid: int, user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    t = _own_txn(db, user, tid)
    out = txn_out(t, _cats(db, user.id), base, load_fx(db))
    fx = load_fx(db)
    try:
        conv = fx.convert(Money(t.amount, t.currency), base, t.transaction_date)
        out["fx"] = {"rate": conv.rate, "provider": conv.provider, "effective_at": conv.effective_at, "derived": conv.derived}
    except Exception:
        out["fx"] = None
    out["merchant_key"] = merchant_key(t.raw_description, t.merchant_name)
    return out


class TxnPatch(BaseModel):
    category_id: int | None = None
    type: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = None
    apply_to_future: bool = False
    apply_to_existing: bool = False


@router.patch("/transactions/{tid}")
def patch_txn(tid: int, body: TxnPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Edits go to user_* override columns; raw provider data is never modified."""
    t = _own_txn(db, user, tid)
    cats = _cats(db, user.id)
    applied = 0
    if body.category_id is not None:
        if body.category_id not in cats:
            raise HTTPException(422, "Unknown category")
        t.user_category_id = body.category_id
        if body.apply_to_future:
            key = merchant_key(t.raw_description, t.merchant_name)
            rule = db.scalar(select(CategorizationRule).where(CategorizationRule.user_id == user.id,
                                                              CategorizationRule.rule_kind == "learned",
                                                              CategorizationRule.matching_rule == key))
            if rule:
                rule.category_id = body.category_id
            else:
                db.add(CategorizationRule(user_id=user.id, matching_rule=key, rule_kind="learned", category_id=body.category_id, priority=50))
            if body.apply_to_existing:
                for other in db.scalars(select(Transaction).join(Account).where(
                        Account.user_id == user.id, Transaction.id != t.id, Transaction.user_category_id.is_(None))):
                    if merchant_key(other.raw_description, other.merchant_name) == key:
                        other.user_category_id = body.category_id
                        applied += 1
    if body.type is not None:
        if body.type not in TYPES:
            raise HTTPException(422, "Unknown type")
        t.user_type = body.type
    if body.notes is not None:
        t.user_notes = body.notes.strip() or None
    if body.tags is not None:
        t.tags = sorted({x.strip()[:32] for x in body.tags if x.strip()})[:20]
    return {"ok": True, "also_updated": applied}


@router.post("/transactions/{tid}/review")
def review(tid: int, decision: str = Query(pattern="^(not_duplicate|duplicate|confirm_transfer|reject_transfer)$"),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own_txn(db, user, tid)
    if decision == "not_duplicate":
        t.duplicate_status = "confirmed_unique"
    elif decision == "duplicate":
        t.duplicate_status = "confirmed_duplicate"  # excluded from analytics; raw row retained for audit
    elif decision in ("confirm_transfer", "reject_transfer") and t.transfer_group:
        group = t.transfer_group.split(":", 1)[-1]
        for leg in db.scalars(select(Transaction).join(Account).where(Account.user_id == user.id,
                                                                      Transaction.transfer_group.like(f"%:{group}"))):
            if decision == "confirm_transfer":
                leg.user_type, leg.transfer_group = "transfer", f"confirmed:{group}"
            else:
                leg.transfer_group = None
    return {"ok": True}


@router.post("/transactions/detect-transfers")
def detect_transfers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Suggest transfer pairs between the user's own accounts (requires confirmation; nothing is reclassified)."""
    fx = load_fx(db)
    rows = db.scalars(select(Transaction).join(Account).where(
        Account.user_id == user.id, Transaction.transfer_group.is_(None),
        func.coalesce(Transaction.user_type, Transaction.transaction_type).in_(("income", "expense", "deposit", "withdrawal")))).all()
    legs = []
    for r in rows:
        v = to_base(fx, r.amount, r.currency, "EUR", r.transaction_date)
        if v is not None:
            legs.append(TransferLeg(str(r.id), str(r.account_id), r.transaction_date, v, r.transaction_type))
    by_id = {str(r.id): r for r in rows}
    pairs = find_transfer_pairs(legs)
    for o, i in pairs:
        g = f"suggested:{uuid.uuid4().hex[:12]}"
        by_id[o].transfer_group = by_id[i].transfer_group = g
    return {"suggested_pairs": len(pairs)}


# ------------------------------------------------------------------ categories & rules
@router.get("/categories")
def categories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cats = _cats(db, user.id)
    tree = []
    for c in sorted(cats.values(), key=lambda c: c.name):
        if c.parent_category_id is None:
            tree.append({"id": c.id, "slug": c.slug, "name": c.name, "type": c.category_type, "icon": c.icon, "color": c.color,
                         "custom": c.user_id is not None,
                         "children": [{"id": k.id, "slug": k.slug, "name": k.name, "custom": k.user_id is not None}
                                      for k in sorted(cats.values(), key=lambda k: k.name) if k.parent_category_id == c.id]})
    return tree


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: int | None = None
    category_type: str = "expense"
    color: str | None = Field(default=None, max_length=16)


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cats = _cats(db, user.id)
    parent = cats.get(body.parent_id) if body.parent_id else None
    if body.parent_id and not parent:
        raise HTTPException(422, "Unknown parent")
    slug = "u_" + "".join(ch if ch.isalnum() else "_" for ch in body.name.lower())[:40]
    if any(c.slug == slug and c.user_id == user.id for c in cats.values()):
        raise HTTPException(409, "Category already exists")
    c = Category(user_id=user.id, slug=slug, name=body.name.strip(), parent_category_id=parent.id if parent else None,
                 category_type=parent.category_type if parent else body.category_type,
                 color=body.color or (parent.color if parent else "#64748B"), icon=parent.icon if parent else "tag")
    db.add(c)
    db.flush()
    return {"id": c.id, "slug": c.slug}


@router.delete("/categories/{cid}")
def delete_category(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Category, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(403, "Only your custom categories can be deleted")
    db.delete(c)  # FK ON DELETE SET NULL keeps transactions, which fall back to the system category
    return {"ok": True}


@router.get("/categorization-rules")
def rules(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cats = _cats(db, user.id)
    rows = db.scalars(select(CategorizationRule).where(CategorizationRule.user_id == user.id).order_by(CategorizationRule.priority.desc()))
    return [{"id": r.id, "pattern": r.matching_rule, "field": r.match_field, "kind": r.rule_kind, "priority": r.priority,
             "category": {"id": r.category_id, "name": cats[r.category_id].name if r.category_id in cats else "?"},
             "created_at": r.created_at} for r in rows]


class RuleIn(BaseModel):
    pattern: str = Field(min_length=2, max_length=255)
    category_id: int
    field: str = Field(default="description", pattern="^(description|merchant)$")
    priority: int = Field(default=100, ge=0, le=1000)


@router.post("/categorization-rules", status_code=201)
def add_rule(body: RuleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.category_id not in _cats(db, user.id):
        raise HTTPException(422, "Unknown category")
    r = CategorizationRule(user_id=user.id, matching_rule=body.pattern, match_field=body.field, category_id=body.category_id,
                           priority=body.priority, rule_kind="rule")
    db.add(r)
    db.flush()
    return {"id": r.id}


@router.delete("/categorization-rules/{rid}")
def delete_rule(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(CategorizationRule, rid)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Rule not found")
    db.delete(r)
    return {"ok": True}
