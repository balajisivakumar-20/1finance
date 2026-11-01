from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import base_currency, current_user, sync_limiter
from app.api.fmt import m
from app.connectors import registry
from app.connectors.base import ConnectorError, ReauthRequired
from app.core.db import get_db
from app.core.security import encrypt_secret
from app.importers.statements import parse_csv
from app.models import (
    Account,
    AccountBalanceSnapshot,
    AuditLog,
    Connection,
    EncryptedCredential,
    HoldingSnapshot,
    ImportBatch,
    Institution,
    InvestmentTransaction,
    Notification,
    SyncJob,
    Transaction,
    User,
)
from app.services.ingest import ingest_transactions
from app.services.ledger import LIABILITY_ACCOUNT_TYPES, Ledger
from app.services.serializers import account_out
from app.sync.engine import run_sync

router = APIRouter(tags=["accounts"])
ACCOUNT_TYPES = {"checking", "savings", "brokerage", "investment", "cash", "credit_card", "loan", "fixed_deposit", "other"}
MAX_UPLOAD = 5 * 1024 * 1024


def _own_account(db: Session, user: User, account_id: int) -> Account:
    a = db.get(Account, account_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Account not found")
    return a


def _own_conn(db: Session, user: User, conn_id: int) -> Connection:
    c = db.get(Connection, conn_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Connection not found")
    return c


@router.get("/connectors")
def connectors(user: User = Depends(current_user)):
    return registry.describe()


@router.get("/accounts")
def list_accounts(user: User = Depends(current_user), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    now = datetime.now(timezone.utc)
    ledger = Ledger(db, user.id)
    conns = {c.id: c for c in db.scalars(select(Connection).where(Connection.user_id == user.id))}
    items = [account_out(a, ledger, conns.get(a.connection_id), base, now) for a in ledger.accounts.values()]
    def total(pred):
        return sum((Decimal(i["balance_base"]) for i in items if i["balance_base"] is not None and pred(i)), Decimal(0))
    return {
        "currency": base,
        "summary": {
            "bank": m(total(lambda i: i["account_type"] in ("checking", "savings", "cash")), base),
            "investments": m(total(lambda i: i["account_type"] in ("brokerage", "investment", "fixed_deposit")), base),
            "debt": m(-total(lambda i: i["account_type"] in LIABILITY_ACCOUNT_TYPES), base),
            "connected": sum(1 for c in conns.values() if c.connection_status in ("active", "syncing")),
        },
        "accounts": items,
        "connections": [{"id": c.id, "institution": c.institution.name, "connector": c.connector, "status": c.connection_status,
                         "last_successful_sync": c.last_successful_sync, "last_error": c.last_error, "is_demo": c.is_demo}
                        for c in conns.values() if c.connection_status != "disconnected"],
    }


class AccountPatch(BaseModel):
    nickname: str | None = Field(default=None, max_length=120)
    counts_toward_net_worth: bool | None = None


@router.patch("/accounts/{account_id}")
def patch_account(account_id: int, body: AccountPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _own_account(db, user, account_id)
    if body.nickname is not None:
        a.nickname = body.nickname.strip() or None
    if body.counts_toward_net_worth is not None:
        a.counts_toward_net_worth = body.counts_toward_net_worth
    return {"ok": True}


class ManualAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    account_type: str
    currency: str = Field(min_length=3, max_length=3)
    balance: Decimal

    @field_validator("account_type")
    @classmethod
    def _t(cls, v):
        if v not in ACCOUNT_TYPES:
            raise ValueError("invalid account type")
        return v


@router.post("/accounts/manual", status_code=201)
def create_manual(body: ManualAccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inst = db.scalar(select(Institution).where(Institution.slug == "manual"))
    conn = Connection(user_id=user.id, institution_id=inst.id, connector="manual", authentication_method="manual",
                      connection_status="active", last_successful_sync=datetime.now(timezone.utc))
    db.add(conn)
    db.flush()
    a = Account(user_id=user.id, connection_id=conn.id, account_name=body.name, account_type=body.account_type,
                currency=body.currency.upper(), external_account_reference=f"manual-{conn.id}")
    db.add(a)
    db.flush()
    db.add(AccountBalanceSnapshot(account_id=a.id, balance=body.balance, currency=a.currency,
                                  valuation_timestamp=datetime.now(timezone.utc), source="manual"))
    return {"id": a.id}


class BalanceIn(BaseModel):
    balance: Decimal


@router.post("/accounts/{account_id}/balance")
def update_manual_balance(account_id: int, body: BalanceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _own_account(db, user, account_id)
    if not a.connection or a.connection.connector != "manual":
        raise HTTPException(400, "Only manual accounts accept balance updates")
    db.add(AccountBalanceSnapshot(account_id=a.id, balance=body.balance, currency=a.currency,
                                  valuation_timestamp=datetime.now(timezone.utc), source="manual"))
    return {"ok": True}


class ConnectIn(BaseModel):
    connector: str
    credentials: dict[str, str] = {}


@router.post("/connections", status_code=201, dependencies=[Depends(sync_limiter)])
def create_connection(body: ConnectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        cls = registry.get(body.connector)
    except KeyError:
        raise HTTPException(404, "Unknown connector")
    if cls.info.auth_method in ("manual", "file_import"):
        raise HTTPException(400, "Use the manual-account or import endpoints for this method")
    creds = {k: v.strip() for k, v in body.credentials.items() if k in cls.info.credential_fields and v.strip()}
    # A connection is only created after a real validation call succeeds.
    try:
        cls(dict(creds)).validate_connection()
    except ReauthRequired as e:
        raise HTTPException(400, f"Authorization failed: {e}")
    except ConnectorError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(502, "Could not reach the provider. Please try again.")
    inst = db.scalar(select(Institution).where(Institution.slug == cls.info.institution_slug))
    conn = Connection(user_id=user.id, institution_id=inst.id, connector=cls.info.key, authentication_method=cls.info.auth_method,
                      connection_status="active", is_demo=cls.info.is_mock)
    db.add(conn)
    db.flush()
    if creds:
        db.add(EncryptedCredential(connection_id=conn.id, ciphertext=encrypt_secret(creds, aad=f"connection:{conn.id}")))
    job = run_sync(db, conn, trigger="connect", backfill=True)
    db.add(AuditLog(user_id=user.id, action="account_connected", meta={"connector": cls.info.key}))
    db.add(Notification(user_id=user.id, kind="connected", title=f"{inst.name} connected",
                        body="Initial sync " + ("completed." if job.status == "succeeded" else "had problems — see Accounts.")))
    return {"connection_id": conn.id, "sync": {"status": job.status, "stats": job.stats, "error": job.error_details}}


@router.post("/connections/{conn_id}/sync", dependencies=[Depends(sync_limiter)])
def sync_connection(conn_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conn = _own_conn(db, user, conn_id)
    if conn.connector == "manual" or conn.connection_status == "disconnected":
        raise HTTPException(400, "This connection cannot be synchronized")
    job = run_sync(db, conn)
    return {"status": job.status, "stats": job.stats, "error": job.error_details, "connection_status": conn.connection_status,
            "last_successful_sync": conn.last_successful_sync}


@router.post("/sync-all", dependencies=[Depends(sync_limiter)])
def sync_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for conn in db.scalars(select(Connection).where(Connection.user_id == user.id,
                                                    Connection.connection_status.in_(("active", "error")),
                                                    Connection.connector != "manual")):
        job = run_sync(db, conn)
        out.append({"connection_id": conn.id, "status": job.status})
    return {"results": out}


@router.get("/connections/{conn_id}/jobs")
def jobs(conn_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own_conn(db, user, conn_id)
    rows = db.scalars(select(SyncJob).where(SyncJob.connection_id == conn_id).order_by(SyncJob.started_at.desc()).limit(20))
    return [{"id": j.id, "status": j.status, "trigger": j.trigger, "started_at": j.started_at, "completed_at": j.completed_at,
             "stats": j.stats, "error": j.error_details} for j in rows]


class DisconnectIn(BaseModel):
    delete_data: bool = False


@router.post("/connections/{conn_id}/disconnect")
def disconnect(conn_id: int, body: DisconnectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Removes credentials. Historical data is retained unless the user explicitly asks to delete it."""
    conn = _own_conn(db, user, conn_id)
    db.execute(delete(EncryptedCredential).where(EncryptedCredential.connection_id == conn.id))
    conn.connection_status = "disconnected"
    accts = list(db.scalars(select(Account).where(Account.connection_id == conn.id)))
    if body.delete_data:
        ids = [a.id for a in accts]
        for model in (Transaction, AccountBalanceSnapshot, HoldingSnapshot, InvestmentTransaction):
            db.execute(delete(model).where(model.account_id.in_(ids)))
        for a in accts:
            db.delete(a)
    else:
        for a in accts:
            a.status = "disconnected"
    db.add(AuditLog(user_id=user.id, action="account_disconnected", meta={"connection_id": conn.id, "deleted_data": body.delete_data}))
    return {"ok": True, "data_deleted": body.delete_data}


# ------------------------------------------------------------------ statement import
@router.post("/imports/preview")
async def import_preview(file: UploadFile = File(...), account_id: int = Form(...), user: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    acct = _own_account(db, user, account_id)
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 5 MB)")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(415, "Only CSV statements are supported. PDF parsing requires the validated preview pipeline (planned).")
    try:
        res = parse_csv(content, account_ref="target")
    except UnicodeDecodeError:
        raise HTTPException(400, "File is not valid UTF-8 text")
    if res.format == "unknown":
        raise HTTPException(400, res.errors[0]["error"])
    stats = ingest_transactions(db, user.id, {"target": acct}, res.rows, "import:csv", dry_run=True)
    batch = ImportBatch(user_id=user.id, account_id=acct.id, source=f"csv:{res.format}", file_name=(file.filename or "")[:255],
                        import_status="previewed",
                        summary={"rows": len(res.rows), "errors": res.errors[:50], "skipped": res.skipped, "dedup": stats,
                                 "currencies": sorted(res.currencies)})
    db.add(batch)
    db.flush()
    # The parsed rows are kept server-side for commit (re-parsed from the stored file content for integrity).
    batch.summary = {**batch.summary, "_content": content.decode("utf-8-sig")}
    return {
        "batch_id": batch.id, "format": res.format, "rows": len(res.rows), "skipped": res.skipped, "errors": res.errors[:50],
        "dedup": stats, "currency_mismatch": [c for c in res.currencies if c != acct.currency],
        "sample": [{"date": t.occurred_at, "description": t.description, "amount": t.amount, "currency": t.currency,
                    "type": t.type_hint, "status": t.status} for t in res.rows[:15]],
    }


@router.post("/imports/{batch_id}/commit")
def import_commit(batch_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(ImportBatch, batch_id)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "Import not found")
    if b.import_status != "previewed":
        raise HTTPException(409, "Import already processed")
    acct = _own_account(db, user, b.account_id)
    res = parse_csv(b.summary["_content"].encode(), account_ref="target")
    stats = ingest_transactions(db, user.id, {"target": acct}, res.rows, "import:csv", import_batch_id=b.id)
    b.import_status = "committed"
    b.summary = {k: v for k, v in b.summary.items() if k != "_content"} | {"committed": stats}
    db.add(AuditLog(user_id=user.id, action="statement_import", meta={"batch_id": b.id, "new": stats["new"]}))
    db.add(Notification(user_id=user.id, kind="import", title="Statement import completed",
                        body=f"{stats['new']} new transactions, {stats['duplicate']} duplicates skipped, "
                             f"{stats['possible_duplicate']} flagged for review."))
    return {"ok": True, "stats": stats}
