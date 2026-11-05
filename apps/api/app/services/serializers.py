from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.api.fmt import m, pct
from app.core.security import mask_reference
from app.models import Account, Connection, Transaction
from app.services.ledger import LIABILITY_ACCOUNT_TYPES, STALE_AFTER, Ledger, to_base


def account_out(a: Account, ledger: Ledger, conn: Connection | None, base: str, now: datetime) -> dict:
    snaps = ledger.latest_balances(a.id)
    holdings = ledger.latest_holdings(a.id)
    # cash may be held in several currencies; it is shown in the account's currency (the UI labels it that way)
    cash: Decimal | None = Decimal(0)
    for b in snaps:
        v = to_base(ledger.fx, b.balance, b.currency, a.currency, now)
        cash = None if v is None or cash is None else cash + v
    inv_local = sum((h.market_value for h in holdings if h.currency == a.currency), Decimal(0))
    # total in base = cash + all holdings (each converted from its own currency)
    total_base = Decimal(0)
    for b in snaps:
        v = to_base(ledger.fx, b.balance, b.currency, base, now)
        total_base = None if v is None or total_base is None else total_base + v
    for h in holdings:
        v = to_base(ledger.fx, h.market_value, h.currency, base, now)
        total_base = None if v is None or total_base is None else total_base + v
    if a.account_type in LIABILITY_ACCOUNT_TYPES and total_base is not None:
        total_base = -abs(total_base)
    total_local = to_base(ledger.fx, total_base, base, a.currency, now) if total_base is not None else None
    last_ts = max([b.valuation_timestamp for b in snaps] + [h.valuation_timestamp for h in holdings], default=None)
    status = conn.connection_status if conn else "manual"
    return {
        "id": a.id,
        "name": a.nickname or a.account_name,
        "official_name": a.account_name,
        "nickname": a.nickname,
        "institution": conn.institution.name if conn else "Manual",
        "institution_slug": conn.institution.slug if conn else "manual",
        "connector": conn.connector if conn else "manual",
        "account_type": a.account_type,
        "currency": a.currency,
        "masked_reference": mask_reference(a.external_account_reference),
        "balance": m(total_local, a.currency),
        "cash_balance": m(cash, a.currency),
        "investments_value_local": m(inv_local, a.currency) if holdings else None,
        "balance_base": m(total_base, base),
        "base_currency": base,
        "valuation_timestamp": last_ts,
        "last_sync": conn.last_successful_sync if conn else None,
        "connection_status": status,
        "connection_id": conn.id if conn else None,
        "is_stale": bool(last_ts and now - last_ts > STALE_AFTER),
        "is_demo": a.is_demo,
        "status": a.status,
        "counts_toward_net_worth": a.counts_toward_net_worth,
    }


def txn_out(t: Transaction, cats: dict | None = None, base: str | None = None, fx=None, mask: bool = False) -> dict:
    cat_id = t.user_category_id or t.category_id
    cat = (cats or {}).get(cat_id)
    conv = None
    if base and fx is not None:
        v = to_base(fx, t.amount, t.currency, base, t.transaction_date)
        conv = m(v, base) if v is not None else None
    acct = t.account
    return {
        "id": t.id,
        "date": t.transaction_date,
        "posting_date": t.posting_date,
        "description": t.raw_description,
        "merchant": t.merchant_name,
        "amount": m(t.amount, t.currency),
        "currency": t.currency,
        "amount_base": conv,
        "base_currency": base,
        "type": t.user_type or t.transaction_type,
        "system_type": t.transaction_type,
        "category": {"id": cat.id, "slug": cat.slug, "name": cat.name, "color": cat.color, "icon": cat.icon} if cat else None,
        "category_source": "user" if t.user_category_id else t.category_source,
        "status": t.transaction_status,
        "account": {"id": acct.id, "name": acct.nickname or acct.account_name,
                    "institution": acct.connection.institution.name if acct.connection else "Manual"} if acct else None,
        "notes": t.user_notes,
        "tags": t.tags or [],
        "source": t.source,
        "external_reference": mask_reference(t.external_transaction_id, 6),  # never expose full provider refs
        "duplicate_status": t.duplicate_status,
        "transfer_group": t.transfer_group,
        "is_demo": t.is_demo,
    }


__all__ = ["account_out", "txn_out", "pct"]
