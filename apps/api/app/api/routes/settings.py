from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import base_currency, current_user, require_mfa
from app.core.db import get_db
from app.models import Account, Asset, AuditLog, Budget, CategorizationRule, Connection, Goal, ImportBatch, Liability, Notification, Transaction, User, UserPreferences
from app.services import reports

router = APIRouter(tags=["settings"])
CURRENCIES = {"EUR", "INR", "USD", "GBP"}


class PrefsPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    base_currency: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    theme: str | None = Field(default=None, pattern="^(light|dark|system)$")
    number_format: str | None = Field(default=None, max_length=16)
    date_format: str | None = Field(default=None, max_length=16)
    ai_categorization_consent: bool | None = None


@router.patch("/settings/preferences")
def patch_prefs(body: PrefsPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(UserPreferences, user.id)
    if body.base_currency:
        if body.base_currency.upper() not in CURRENCIES:
            raise HTTPException(422, "Unsupported currency")
        p.base_currency = body.base_currency.upper()
    if body.display_name:
        user.display_name = body.display_name.strip()
    for f in ("timezone", "theme", "number_format", "date_format", "ai_categorization_consent"):
        v = getattr(body, f)
        if v is not None:
            setattr(p, f, v)
    if body.ai_categorization_consent is not None:
        db.add(AuditLog(user_id=user.id, action="ai_consent_changed", meta={"value": body.ai_categorization_consent}))
    return {"ok": True}


@router.get("/settings/audit-log")
def audit(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.timestamp.desc()).limit(50))
    return [{"id": r.id, "action": r.action, "timestamp": r.timestamp, "ip": r.ip, "meta": r.meta} for r in rows]


@router.get("/settings/imports")
def imports(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ImportBatch).where(ImportBatch.user_id == user.id).order_by(ImportBatch.imported_at.desc()).limit(30))
    return [{"id": b.id, "file_name": b.file_name, "source": b.source, "status": b.import_status, "imported_at": b.imported_at,
             "summary": {k: v for k, v in (b.summary or {}).items() if not k.startswith("_")}} for b in rows]


@router.delete("/settings/imports/{batch_id}")
def revert_import(batch_id: int, user: User = Depends(require_mfa), db: Session = Depends(get_db)):
    b = db.get(ImportBatch, batch_id)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "Import not found")
    n = db.execute(delete(Transaction).where(Transaction.import_batch_id == b.id)).rowcount
    b.import_status = "reverted"
    db.add(AuditLog(user_id=user.id, action="import_reverted", meta={"batch_id": b.id, "deleted": n}))
    return {"deleted_transactions": n}


@router.get("/reports/{kind}")
def report(kind: str, format: str = Query("pdf", pattern="^(pdf|csv|xlsx)$"), date_from: date | None = None,
           date_to: date | None = None, user: User = Depends(current_user), db: Session = Depends(get_db),
           base: str = Depends(base_currency)):
    try:
        r = reports.build(db, user.id, kind, base, date_from, date_to)
    except KeyError:
        raise HTTPException(404, "Unknown report")
    body, media = {"pdf": (reports.to_pdf, "application/pdf"), "csv": (reports.to_csv, "text/csv; charset=utf-8"),
                   "xlsx": (reports.to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}[format]
    db.add(AuditLog(user_id=user.id, action="data_export", meta={"report": kind, "format": format}))
    fname = f"1finance-{kind}-{r.period[0]}_{r.period[1]}.{format}"
    return Response(body(r), media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"',
                                                         "Cache-Control": "no-store"})


@router.get("/reports")
def report_kinds(user: User = Depends(current_user)):
    return [{"kind": k, "title": v} for k, v in reports.KINDS.items()]


@router.get("/settings/export")
def export_all(user: User = Depends(require_mfa), db: Session = Depends(get_db), base: str = Depends(base_currency)):
    """Full JSON export of the user's financial data. Credentials are never included."""
    accts = list(db.scalars(select(Account).where(Account.user_id == user.id)))
    txns = db.scalars(select(Transaction).where(Transaction.account_id.in_([a.id for a in accts] or [-1])))
    data = {
        "exported_for": user.email, "base_currency": base,
        "accounts": [{"id": a.id, "name": a.account_name, "type": a.account_type, "currency": a.currency, "status": a.status} for a in accts],
        "transactions": [{"id": t.id, "account_id": t.account_id, "date": t.transaction_date.isoformat(), "description": t.raw_description,
                          "amount": str(t.amount), "currency": t.currency, "type": t.user_type or t.transaction_type,
                          "status": t.transaction_status, "notes": t.user_notes, "tags": t.tags} for t in txns],
    }
    db.add(AuditLog(user_id=user.id, action="data_export", meta={"kind": "full_json"}))
    return Response(json.dumps(data, indent=1), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="1finance-export.json"', "Cache-Control": "no-store"})


class DeleteAll(BaseModel):
    confirm: str


@router.post("/settings/delete-data")
def delete_all(body: DeleteAll, user: User = Depends(require_mfa), db: Session = Depends(get_db)):
    if body.confirm != "DELETE":
        raise HTTPException(400, 'Type "DELETE" to confirm')
    for model in (Account, Connection, Asset, Liability, Budget, Goal, CategorizationRule, ImportBatch, Notification):
        db.execute(delete(model).where(model.user_id == user.id))  # child rows cascade via FK ON DELETE CASCADE
    db.add(AuditLog(user_id=user.id, action="data_deleted"))
    return {"ok": True}
