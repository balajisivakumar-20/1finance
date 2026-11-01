"""Synchronization engine.

Guarantees:
- All writes for one sync run happen inside a SAVEPOINT; any failure rolls back that run only, leaving previously
  synced data intact.
- Snapshots are append-only and only newer-than-checkpoint rows are inserted (idempotent re-runs).
- Rate limits: exponential backoff (base 2s, max 3 attempts, honours retry_after).
- Expired credentials → connection.status = "reauth_required" + notification. Never shown as live.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors import registry
from app.connectors.base import Capability, ConnectorError, FinancialConnector, RateLimited, ReauthRequired, SecurityData
from app.core.security import decrypt_secret
from app.models import (
    Account,
    AccountBalanceSnapshot,
    AuditLog,
    Connection,
    EncryptedCredential,
    HoldingSnapshot,
    InvestmentTransaction,
    Notification,
    Security,
    SyncJob,
)
from app.services.ingest import ingest_transactions

log = logging.getLogger("onefinance.sync")
MAX_ATTEMPTS = 3


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_connector(db: Session, conn: Connection) -> FinancialConnector:
    cls = registry.get(conn.connector)
    creds = {}
    enc = db.scalar(select(EncryptedCredential).where(EncryptedCredential.connection_id == conn.id))
    if enc:
        creds = decrypt_secret(enc.ciphertext, aad=f"connection:{conn.id}")
    return cls(creds)


def _security(db: Session, s: SecurityData, cache: dict) -> Security:
    key = (s.ticker, s.exchange)
    if key in cache:
        return cache[key]
    sec = db.scalar(select(Security).where(Security.ticker == s.ticker, Security.exchange == s.exchange))
    if not sec:
        sec = Security(ticker=s.ticker, name=s.name, asset_class=s.asset_class, trading_currency=s.currency, isin=s.isin,
                       exchange=s.exchange, country=s.country, sector=s.sector)
        db.add(sec)
        db.flush()
    cache[key] = sec
    return sec


def _sync_once(db: Session, conn: Connection, connector: FinancialConnector, backfill: bool) -> dict:
    stats: dict = {}
    source = "mock" if connector.info.is_mock else "api"
    demo = connector.info.is_mock
    # accounts
    accounts: dict[str, Account] = {
        a.external_account_reference: a
        for a in db.scalars(select(Account).where(Account.connection_id == conn.id))
        if a.external_account_reference
    }
    if connector.supports(Capability.ACCOUNTS):
        for a in connector.list_accounts():
            if a.external_ref not in accounts:
                acct = Account(user_id=conn.user_id, connection_id=conn.id, external_account_reference=a.external_ref,
                               account_name=a.name, account_type=a.account_type, currency=a.currency, is_demo=demo)
                db.add(acct)
                db.flush()
                accounts[a.external_ref] = acct
        stats["accounts"] = len(accounts)
    checkpoint = dict(conn.sync_checkpoint or {})
    since = None if backfill or not checkpoint.get("last_run") else datetime.fromisoformat(checkpoint["last_run"])

    # balances (append newer snapshots only)
    if connector.supports(Capability.BALANCES):
        last = dict(db.execute(select(AccountBalanceSnapshot.account_id, func.max(AccountBalanceSnapshot.valuation_timestamp))
                               .where(AccountBalanceSnapshot.account_id.in_([a.id for a in accounts.values()]))
                               .group_by(AccountBalanceSnapshot.account_id)).all())
        n = 0
        for b in connector.fetch_balances(since=None if backfill else since):
            acct = accounts.get(b.external_account_ref)
            if not acct or (last.get(acct.id) and b.as_of <= last[acct.id]):
                continue
            db.add(AccountBalanceSnapshot(account_id=acct.id, balance=b.balance, available_balance=b.available,
                                          currency=b.currency, valuation_timestamp=b.as_of, source=source))
            n += 1
        stats["balances"] = n

    # transactions
    if connector.supports(Capability.TRANSACTIONS):
        stats["transactions"] = ingest_transactions(db, conn.user_id, accounts, connector.fetch_transactions(since=since),
                                                    source, is_demo=demo)

    # holdings
    if connector.supports(Capability.HOLDINGS):
        cache: dict = {}
        last = dict(db.execute(select(HoldingSnapshot.account_id, func.max(HoldingSnapshot.valuation_timestamp))
                               .where(HoldingSnapshot.account_id.in_([a.id for a in accounts.values()]))
                               .group_by(HoldingSnapshot.account_id)).all())
        rows = connector.fetch_holdings_history() if backfill else []
        rows = rows or connector.fetch_holdings()
        n = 0
        for h in rows:
            acct = accounts.get(h.external_account_ref)
            if not acct or (last.get(acct.id) and h.as_of <= last[acct.id]):
                continue
            sec = _security(db, h.security, cache)
            db.add(HoldingSnapshot(account_id=acct.id, security_id=sec.id, quantity=h.quantity, average_price=h.average_price,
                                   market_price=h.market_price, market_value=h.quantity * h.market_price,
                                   cost_basis=h.quantity * h.average_price, currency=h.currency, price_type=h.price_type,
                                   valuation_timestamp=h.as_of, source=source))
            n += 1
        stats["holdings"] = n

    # investment activity (idempotent by external id)
    if connector.supports(Capability.INVESTMENT_ACTIVITY):
        cache = {}
        existing = {(r.account_id, r.external_id) for r in db.execute(
            select(InvestmentTransaction.account_id, InvestmentTransaction.external_id)
            .where(InvestmentTransaction.account_id.in_([a.id for a in accounts.values()])))}
        n = 0
        for a in connector.fetch_investment_activity(since=since):
            acct = accounts.get(a.external_account_ref)
            if not acct or (acct.id, a.external_id) in existing:
                continue
            sec = _security(db, a.security, cache) if a.security else None
            db.add(InvestmentTransaction(account_id=acct.id, security_id=sec.id if sec else None, external_id=a.external_id,
                                         activity_type=a.activity_type, quantity=a.quantity, price=a.price, amount=a.amount,
                                         fees=a.fees, realized_pl=a.realized_pl, currency=a.currency,
                                         execution_timestamp=a.executed_at, source=source))
            existing.add((acct.id, a.external_id))
            n += 1
        stats["investment_activity"] = n
    db.flush()
    return stats


def run_sync(db: Session, conn: Connection, trigger: str = "manual", backfill: bool = False,
             sleep: Callable[[float], None] = time.sleep) -> SyncJob:
    job = SyncJob(connection_id=conn.id, status="running", trigger=trigger)
    db.add(job)
    conn.connection_status = "syncing"
    db.flush()
    try:
        connector = build_connector(db, conn)
    except Exception as e:  # unknown connector, undecryptable credentials
        job.status, job.error_details, job.completed_at = "failed", str(e)[:500], utcnow()
        conn.connection_status, conn.last_error = "error", "Connector unavailable"
        return job

    delay = 2.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        job.attempts = attempt
        sp = db.begin_nested()
        try:
            stats = _sync_once(db, conn, connector, backfill or conn.last_successful_sync is None)
            sp.commit()
        except RateLimited as e:
            sp.rollback()
            if attempt == MAX_ATTEMPTS:
                job.status, job.error_details = "failed", "Provider rate limit — will retry on next schedule"
                conn.connection_status, conn.last_error = "error", job.error_details
                break
            sleep(e.retry_after or delay)
            delay *= 2
            continue
        except ReauthRequired as e:
            sp.rollback()
            job.status, job.error_details = "failed", str(e)
            conn.connection_status, conn.last_error = "reauth_required", str(e)
            db.add(Notification(user_id=conn.user_id, kind="reconnect", title=f"{conn.institution.name}: reconnection required",
                                body="Your access has expired. Reconnect to resume syncing."))
            break
        except (ConnectorError, Exception) as e:  # noqa: BLE001 — sync must never crash the worker
            sp.rollback()
            log.exception("sync failed for connection %s", conn.id)
            job.status = "failed"
            job.error_details = str(e)[:500] if isinstance(e, ConnectorError) else "Unexpected error during sync"
            conn.connection_status, conn.last_error = "error", job.error_details
            db.add(Notification(user_id=conn.user_id, kind="sync_failed", title=f"{conn.institution.name}: sync failed",
                                body=job.error_details))
            break
        else:
            now = utcnow()
            job.status, job.stats = "succeeded", stats
            conn.connection_status, conn.last_error, conn.last_successful_sync = "active", None, now
            conn.sync_checkpoint = {**(conn.sync_checkpoint or {}), "last_run": now.isoformat()}
            break
    job.completed_at = utcnow()
    db.add(AuditLog(user_id=conn.user_id, action="sync", meta={"connection_id": conn.id, "status": job.status}))
    db.flush()
    return job


def money(v) -> Decimal:
    return Decimal(v)
