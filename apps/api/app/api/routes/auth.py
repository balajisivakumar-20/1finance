from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CSRF_COOKIE, SESSION_COOKIE, auth_limiter, cookie_name, current_session, current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    new_token,
    new_totp_secret,
    token_hash,
    totp_uri,
    verify_password,
    verify_totp,
)
from app.models import AuditLog, User, UserPreferences, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    totp: str | None = Field(default=None, max_length=8)


def _set_cookies(resp: Response, token: str, csrf: str) -> None:
    s = get_settings()
    max_age = s.session_absolute_hours * 3600
    resp.set_cookie(cookie_name(SESSION_COOKIE), token, max_age=max_age, httponly=True, secure=s.cookie_secure,
                    samesite="lax", path="/")
    # CSRF cookie must be readable by the SPA (double-submit pattern)
    resp.set_cookie(cookie_name(CSRF_COOKIE), csrf, max_age=max_age, httponly=False, secure=s.cookie_secure,
                    samesite="lax", path="/")


def _user_out(u: User, db: Session) -> dict:
    p = db.get(UserPreferences, u.id)
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "mfa_enabled": u.mfa_enabled,
            "preferences": {"base_currency": p.base_currency, "timezone": p.timezone, "theme": p.theme,
                            "number_format": p.number_format, "date_format": p.date_format,
                            "ai_categorization_consent": p.ai_categorization_consent} if p else None,
            "demo_mode": get_settings().demo_mode}


@router.post("/login", dependencies=[Depends(auth_limiter)])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not user.password_hash or not verify_password(user.password_hash, body.password):
        db.add(AuditLog(user_id=user.id if user else None, action="login_failed", ip=ip, meta={"reason": "credentials"}))
        db.commit()
        raise HTTPException(401, "Incorrect email or password")
    mfa_ok = False
    if user.mfa_enabled:
        secret = decrypt_secret(user.totp_secret_enc, aad=f"totp:{user.id}") if user.totp_secret_enc else {}
        if not body.totp:
            raise HTTPException(401, detail={"code": "mfa_required", "message": "Enter the 6-digit code from your authenticator"})
        if not verify_totp(secret.get("secret", ""), body.totp):
            db.add(AuditLog(user_id=user.id, action="login_failed", ip=ip, meta={"reason": "mfa"}))
            db.commit()
            raise HTTPException(401, detail={"code": "mfa_invalid", "message": "Invalid verification code"})
        mfa_ok = True
    token, csrf = new_token(), new_token()
    now = datetime.now(timezone.utc)
    db.add(UserSession(user_id=user.id, token_hash=token_hash(token), expires_at=now + timedelta(hours=get_settings().session_absolute_hours),
                       user_agent=(request.headers.get("user-agent") or "")[:400], ip=ip, mfa_verified=mfa_ok, last_seen_at=now))
    db.add(AuditLog(user_id=user.id, action="login", ip=ip))
    _set_cookies(response, token, csrf)
    return _user_out(user, db)


@router.post("/logout")
def logout(response: Response, sess: UserSession = Depends(current_session)):
    sess.revoked_at = datetime.now(timezone.utc)
    response.delete_cookie(cookie_name(SESSION_COOKIE), path="/")
    response.delete_cookie(cookie_name(CSRF_COOKIE), path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _user_out(user, db)


@router.get("/sessions")
def sessions(sess: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(UserSession).where(UserSession.user_id == sess.user_id, UserSession.revoked_at.is_(None),
                                                UserSession.expires_at > now).order_by(UserSession.last_seen_at.desc()))
    return [{"id": r.id, "user_agent": r.user_agent, "ip": r.ip, "created_at": r.created_at, "last_seen_at": r.last_seen_at,
             "current": r.id == sess.id} for r in rows]


@router.post("/sessions/revoke-others")
def revoke_others(sess: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    n = 0
    for r in db.scalars(select(UserSession).where(UserSession.user_id == sess.user_id, UserSession.id != sess.id,
                                                  UserSession.revoked_at.is_(None))):
        r.revoked_at = now
        n += 1
    db.add(AuditLog(user_id=sess.user_id, action="sessions_revoked", meta={"count": n}))
    return {"revoked": n}


@router.delete("/sessions/{session_id}")
def revoke(session_id: int, sess: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    r = db.get(UserSession, session_id)
    if not r or r.user_id != sess.user_id:
        raise HTTPException(404, "Session not found")
    r.revoked_at = datetime.now(timezone.utc)
    return {"ok": True}


class TotpIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/mfa/setup")
def mfa_setup(user: User = Depends(current_user)):
    if user.mfa_enabled:
        raise HTTPException(409, "MFA already enabled")
    secret = new_totp_secret()
    user.totp_secret_enc = encrypt_secret({"secret": secret, "pending": True}, aad=f"totp:{user.id}")
    return {"otpauth_uri": totp_uri(secret, user.email), "secret": secret}


@router.post("/mfa/enable")
def mfa_enable(body: TotpIn, sess: UserSession = Depends(current_session), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.totp_secret_enc:
        raise HTTPException(400, "Run MFA setup first")
    secret = decrypt_secret(user.totp_secret_enc, aad=f"totp:{user.id}")["secret"]
    if not verify_totp(secret, body.code):
        raise HTTPException(400, "Invalid code")
    user.totp_secret_enc = encrypt_secret({"secret": secret}, aad=f"totp:{user.id}")
    user.mfa_enabled = True
    sess.mfa_verified = True
    db.add(AuditLog(user_id=user.id, action="mfa_enabled"))
    return {"ok": True}


@router.get("/passkeys/status")
def passkeys_status():
    """WebAuthn is designed in (table `webauthn_credentials`) but requires RP configuration — see docs/SETUP.md."""
    return {"available": False, "reason": "Passkeys require ONEFINANCE_WEBAUTHN_RP_ID and HTTPS origin configuration."}
