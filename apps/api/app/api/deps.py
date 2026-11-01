from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import Cookie, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import csrf_valid, token_hash
from app.models import User, UserPreferences, UserSession

SESSION_COOKIE = "1f_session"
CSRF_COOKIE = "1f_csrf"


class DecimalJSON(JSONResponse):
    """Decimals are serialized as strings so no precision is lost in transit."""

    def render(self, content: Any) -> bytes:
        def default(o):
            if isinstance(o, Decimal):
                return format(o, "f")
            if isinstance(o, datetime):
                return o.isoformat()
            if hasattr(o, "isoformat"):
                return o.isoformat()
            if isinstance(o, set):
                return sorted(o)
            raise TypeError(type(o))

        return json.dumps(content, default=default, separators=(",", ":")).encode()


def cookie_name(name: str) -> str:
    # __Host- prefix requires Secure; only use it when cookies are secure.
    return f"__Host-{name}" if get_settings().cookie_secure else name


def current_session(
    request: Request,
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None),
) -> UserSession:
    s = get_settings()
    token = request.cookies.get(cookie_name(SESSION_COOKIE))
    if not token:
        raise HTTPException(401, "Not authenticated")
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token)))
    now = datetime.now(timezone.utc)
    if (not sess or sess.revoked_at or sess.expires_at < now
            or now - sess.last_seen_at > timedelta(minutes=s.session_idle_minutes)):
        raise HTTPException(401, "Session expired")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not csrf_valid(request.cookies.get(cookie_name(CSRF_COOKIE)), x_csrf_token):
            raise HTTPException(403, "CSRF validation failed")
    if now - sess.last_seen_at > timedelta(seconds=60):
        sess.last_seen_at = now
    return sess


def current_user(sess: UserSession = Depends(current_session), db: Session = Depends(get_db)) -> User:
    user = db.get(User, sess.user_id)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def require_mfa(sess: UserSession = Depends(current_session), user: User = Depends(current_user)) -> User:
    """Sensitive settings: if MFA is enabled, the session must have passed it."""
    if user.mfa_enabled and not sess.mfa_verified:
        raise HTTPException(403, "MFA verification required")
    return user


def base_currency(user: User = Depends(current_user), db: Session = Depends(get_db), currency: str | None = None) -> str:
    if currency:
        c = currency.upper()
        if len(c) != 3 or not c.isalpha():
            raise HTTPException(422, "Invalid currency")
        return c
    prefs = db.get(UserPreferences, user.id)
    return prefs.base_currency if prefs else get_settings().base_currency_default


class RateLimiter:
    """Simple in-process token bucket (swap for Redis in multi-instance deployments)."""

    def __init__(self, capacity: int, per_seconds: float) -> None:
        self.capacity, self.rate = capacity, capacity / per_seconds
        self.buckets: dict[str, tuple[float, float]] = defaultdict(lambda: (capacity, time.monotonic()))

    def __call__(self, request: Request) -> None:
        if get_settings().env == "test":
            return
        key = f"{request.url.path}:{request.client.host if request.client else 'x'}"
        tokens, last = self.buckets[key]
        now = time.monotonic()
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        if tokens < 1:
            raise HTTPException(429, "Too many requests — please slow down")
        self.buckets[key] = (tokens - 1, now)


auth_limiter = RateLimiter(10, 60)
sync_limiter = RateLimiter(6, 60)
