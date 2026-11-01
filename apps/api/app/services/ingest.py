"""Persisting normalized data from connectors and imports, with de-duplication and categorization."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorization.engine import Categorizer, Rule
from app.connectors.base import TransactionData
from app.finance.reconcile import Candidate, classify_duplicate
from app.models import Account, CategorizationRule, Category, Transaction, UserPreferences

# category slug → transaction type override when the connector gave no strong hint
INCOME_CATEGORIES = {"salary", "interest_income", "other_income"}


def category_map(db: Session, user_id: int) -> dict[str, int]:
    rows = db.scalars(select(Category).where((Category.user_id == user_id) | (Category.user_id.is_(None)))).all()
    # user categories override system ones with the same slug
    out: dict[str, int] = {}
    for c in sorted(rows, key=lambda c: c.user_id is not None):
        out[c.slug] = c.id
    return out


def build_categorizer(db: Session, user_id: int) -> Categorizer:
    rules, learned = [], {}
    id_to_slug = {v: k for k, v in category_map(db, user_id).items()}
    for r in db.scalars(select(CategorizationRule).where(CategorizationRule.user_id == user_id)):
        slug = id_to_slug.get(r.category_id)
        if not slug:
            continue
        if r.rule_kind == "learned":
            learned[r.matching_rule] = slug
        else:
            rules.append(Rule(str(r.id), r.matching_rule, slug, r.priority, r.match_field))
    prefs = db.get(UserPreferences, user_id)
    return Categorizer(rules, learned, ai=None, ai_consent=bool(prefs and prefs.ai_categorization_consent))


def ingest_transactions(
    db: Session,
    user_id: int,
    accounts_by_ref: dict[str, Account],
    txns: list[TransactionData],
    source: str,
    import_batch_id: int | None = None,
    is_demo: bool = False,
    dry_run: bool = False,
) -> dict:
    stats = {"new": 0, "duplicate": 0, "possible_duplicate": 0, "updated_status": 0, "skipped_unknown_account": 0}
    if not txns:
        return stats
    cats = category_map(db, user_id)
    categorizer = build_categorizer(db, user_id)
    by_account: dict[int, list[TransactionData]] = defaultdict(list)
    for t in txns:
        acct = accounts_by_ref.get(t.external_account_ref)
        if not acct:
            stats["skipped_unknown_account"] += 1
            continue
        by_account[acct.id].append(t)

    for account_id, items in by_account.items():
        lo = min(t.occurred_at for t in items) - timedelta(days=3)
        hi = max(t.occurred_at for t in items) + timedelta(days=3)
        existing = db.scalars(select(Transaction).where(
            Transaction.account_id == account_id, Transaction.transaction_date.between(lo, hi))).all()
        by_ext = {e.external_transaction_id: e for e in existing if e.external_transaction_id}
        cands = [Candidate(str(e.account_id), e.external_transaction_id, e.transaction_date, e.amount, e.currency, e.raw_description)
                 for e in existing]
        for t in items:
            # exact id match: duplicate, but propagate status changes (pending → posted) without touching raw data
            if t.external_id and t.external_id in by_ext:
                e = by_ext[t.external_id]
                if e.transaction_status != t.status:
                    if not dry_run:
                        e.transaction_status = t.status
                        e.posting_date = t.posted_at
                    stats["updated_status"] += 1
                else:
                    stats["duplicate"] += 1
                continue
            cand = Candidate(str(account_id), t.external_id, t.occurred_at, Decimal(t.amount), t.currency, t.description)
            decision = classify_duplicate(cand, cands)
            if decision.status == "duplicate":
                stats["duplicate"] += 1
                continue
            stats[decision.status if decision.status == "possible_duplicate" else "new"] += 1
            cands.append(cand)
            if dry_run:
                continue
            c = categorizer.categorize(t.description, t.merchant)
            typ = t.type_hint or ("income" if t.amount > 0 else "expense")
            cat_slug = c.category
            if typ == "transfer":
                cat_slug = "transfers"
            elif typ == "interest":
                cat_slug = "interest_income"
            elif cat_slug in INCOME_CATEGORIES and t.amount > 0:
                typ = "income"
            row = Transaction(
                account_id=account_id, external_transaction_id=t.external_id, transaction_date=t.occurred_at,
                posting_date=t.posted_at, raw_description=t.description, raw_payload=_jsonable(t.raw),
                amount=Decimal(t.amount), currency=t.currency, merchant_name=t.merchant or _merchant_guess(t.description),
                transaction_type=typ, category_id=cats.get(cat_slug) or cats.get("uncategorized"),
                category_source=c.source if typ not in ("transfer", "interest") else "system",
                transaction_status=t.status, source=source, import_batch_id=import_batch_id, is_demo=is_demo,
                duplicate_status="possible_duplicate" if decision.status == "possible_duplicate" else "unique",
                duplicate_of_id=existing[decision.matched_index].id if decision.status == "possible_duplicate"
                and decision.matched_index is not None and decision.matched_index < len(existing) else None,
            )
            db.add(row)
            if t.external_id:
                by_ext[t.external_id] = row
    if not dry_run:
        db.flush()
    return stats


def _merchant_guess(desc: str) -> str:
    words = [w for w in desc.replace("*", " ").split() if not any(ch.isdigit() for ch in w)]
    return " ".join(words[:3]).title() if words else desc[:40]


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)
