from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
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
log = logging.getLogger("onefinance.auth")


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
    _start_session(db, user, request, response, mfa_ok)
    return _user_out(user, db)


def _start_session(db: Session, user: User, request: Request, response: Response, mfa_ok: bool, method: str = "password") -> None:
    ip = request.client.host if request.client else None
    token, csrf = new_token(), new_token()
    now = datetime.now(timezone.utc)
    db.add(UserSession(user_id=user.id, token_hash=token_hash(token), expires_at=now + timedelta(hours=get_settings().session_absolute_hours),
                       user_agent=(request.headers.get("user-agent") or "")[:400], ip=ip, mfa_verified=mfa_ok, last_seen_at=now))
    db.add(AuditLog(user_id=user.id, action="login", ip=ip, meta={"method": method}))
    _set_cookies(response, token, csrf)


# ------------------------------------------------------------------ Google sign-in / sign-up
# Server-side authorization-code flow with PKCE. The first Google sign-in creates the account.
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
OAUTH_COOKIE = "1f_oauth"      # state/nonce/PKCE verifier for an in-flight Google redirect
PENDING_COOKIE = "1f_pending"  # Google succeeded, waiting for the user's TOTP code
OAUTH_TTL = 600


def _google_redirect_uri() -> str:
    return get_settings().public_url.rstrip("/") + "/api/v1/auth/google/callback"


def _safe_next(n: str | None) -> str:
    return n if n and n.startswith("/") and not n.startswith("//") and "\\" not in n else "/"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _short_cookie(resp: Response, name: str, value: str) -> None:
    resp.set_cookie(cookie_name(name), value, max_age=OAUTH_TTL, httponly=True, secure=get_settings().cookie_secure,
                    samesite="lax", path="/")


def _read_short_cookie(request: Request, name: str, aad: str) -> dict | None:
    blob = request.cookies.get(cookie_name(name))
    if not blob:
        return None
    try:
        data = decrypt_secret(blob, aad=aad)
    except Exception:
        return None
    return data if data.get("exp", 0) > time.time() else None


def _login_redirect(error: str) -> RedirectResponse:
    return RedirectResponse(f"/login?{urlencode({'error': error})}", status_code=302)


def _id_token_claims(id_token: str) -> dict:
    # The token came straight from Google's token endpoint over TLS, so per OIDC Core §3.1.3.7 the
    # signature check may be skipped; issuer, audience, expiry and nonce are still verified by the caller.
    payload = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


@router.get("/google/start", dependencies=[Depends(auth_limiter)])
def google_start(next: str | None = None):
    s = get_settings()
    if not s.google_enabled:
        raise HTTPException(404, "Google sign-in is not configured")
    state, nonce, verifier = new_token(), new_token(), new_token()
    params = {"client_id": s.google_client_id, "redirect_uri": _google_redirect_uri(), "response_type": "code",
              "scope": "openid email profile", "state": state, "nonce": nonce, "prompt": "select_account",
              "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256"}
    resp = RedirectResponse(f"{GOOGLE_AUTHORIZE}?{urlencode(params)}", status_code=302)
    _short_cookie(resp, OAUTH_COOKIE, encrypt_secret({"state": state, "nonce": nonce, "verifier": verifier, "next": _safe_next(next),
                                                      "exp": time.time() + OAUTH_TTL}, aad="oauth:google"))
    return resp


@router.get("/google/callback")
def google_callback(request: Request, db: Session = Depends(get_db), code: str | None = None, state: str | None = None,
                    error: str | None = None):
    s = get_settings()
    flow = _read_short_cookie(request, OAUTH_COOKIE, aad="oauth:google")
    if not s.google_enabled or not flow:
        resp = _login_redirect("google_expired")
    elif error or not code or not state or not hmac.compare_digest(state.encode(), flow["state"].encode()):
        resp = _login_redirect("google_cancelled" if error == "access_denied" else "google_failed")
    else:
        resp = _finish_google(request, db, code, flow)
    resp.delete_cookie(cookie_name(OAUTH_COOKIE), path="/")
    return resp


def _finish_google(request: Request, db: Session, code: str, flow: dict) -> RedirectResponse:
    s = get_settings()
    try:
        r = httpx.post(GOOGLE_TOKEN, timeout=10, data={
            "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "redirect_uri": _google_redirect_uri(), "grant_type": "authorization_code", "code_verifier": flow["verifier"]})
        r.raise_for_status()
        claims = _id_token_claims(r.json()["id_token"])
    except Exception:
        log.warning("Google token exchange failed", exc_info=True)
        return _login_redirect("google_failed")
    if (claims.get("iss") not in GOOGLE_ISSUERS or claims.get("aud") != s.google_client_id
            or claims.get("exp", 0) < time.time() or not hmac.compare_digest(str(claims.get("nonce", "")).encode(), flow["nonce"].encode())
            or not claims.get("sub") or not claims.get("email")):
        return _login_redirect("google_failed")
    if not claims.get("email_verified"):
        return _login_redirect("google_unverified")

    ip = request.client.host if request.client else None
    email = claims["email"].lower()
    user = db.scalar(select(User).where(User.google_sub == claims["sub"]))
    if not user:
        user = db.scalar(select(User).where(User.email == email))
        if user:  # existing account with the same (Google-verified) email: link it
            user.google_sub = claims["sub"]
            db.add(AuditLog(user_id=user.id, action="google_linked", ip=ip))
        else:
            user = User(email=email, display_name=(claims.get("name") or email.split("@")[0])[:120], google_sub=claims["sub"])
            db.add(user)
            db.flush()
            db.add(UserPreferences(user_id=user.id, base_currency=s.base_currency_default))
            db.add(AuditLog(user_id=user.id, action="signup", ip=ip, meta={"method": "google"}))
    if user.mfa_enabled:
        resp = RedirectResponse(f"/login?{urlencode({'mfa': 'google', 'next': flow['next']})}", status_code=302)
        _short_cookie(resp, PENDING_COOKIE, encrypt_secret({"uid": user.id, "exp": time.time() + OAUTH_TTL}, aad="oauth:pending"))
        return resp
    resp = RedirectResponse(flow["next"], status_code=302)
    _start_session(db, user, request, resp, mfa_ok=False, method="google")
    return resp


class GoogleMfaIn(BaseModel):
    totp: str = Field(min_length=6, max_length=8)


@router.post("/google/mfa", dependencies=[Depends(auth_limiter)])
def google_mfa(body: GoogleMfaIn, request: Request, response: Response, db: Session = Depends(get_db)):
    pending = _read_short_cookie(request, PENDING_COOKIE, aad="oauth:pending")
    user = db.get(User, pending["uid"]) if pending else None
    if not user:
        raise HTTPException(401, detail={"code": "mfa_expired", "message": "Sign-in expired — continue with Google again"})
    secret = decrypt_secret(user.totp_secret_enc, aad=f"totp:{user.id}") if user.totp_secret_enc else {}
    if not verify_totp(secret.get("secret", ""), body.totp):
        db.add(AuditLog(user_id=user.id, action="login_failed", ip=request.client.host if request.client else None, meta={"reason": "mfa"}))
        db.commit()
        raise HTTPException(401, detail={"code": "mfa_invalid", "message": "Invalid verification code"})
    _start_session(db, user, request, response, mfa_ok=True, method="google")
    response.delete_cookie(cookie_name(PENDING_COOKIE), path="/")
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
