import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import auth
from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.models import User

CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.fixture
def google(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(s, "google_client_secret", "test-secret")
    claims: dict = {}
    calls: list[dict] = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
            return {"id_token": f"e30.{body}.sig"}

    def fake_post(url, data, timeout):
        calls.append(data)
        return Resp()

    monkeypatch.setattr(auth.httpx, "post", fake_post)
    return claims, calls


def _web():
    from app.main import app

    return TestClient(app, follow_redirects=False)


def _start(c: TestClient, next_path: str = "/goals") -> dict:
    r = c.get("/api/v1/auth/google/start", params={"next": next_path})
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    assert url.netloc == "accounts.google.com"
    return {k: v[0] for k, v in parse_qs(url.query).items()}


def _claims(q: dict, **over) -> dict:
    return {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "exp": time.time() + 300, "nonce": q["nonce"],
            "sub": "g-1001", "email": "New.Person@gmail.com", "email_verified": True, "name": "New Person", **over}


def test_google_disabled_without_credentials(monkeypatch):
    # Clear credentials explicitly so a developer's local .env doesn't change the outcome.
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    monkeypatch.setattr(get_settings(), "google_client_secret", "")
    assert _web().get("/api/v1/auth/google/start").status_code == 404
    assert _web().get("/api/health").json()["google_enabled"] is False


def test_google_signup_then_signin(google, db):
    claims, calls = google
    c = _web()
    q = _start(c)
    assert q["redirect_uri"] == "http://localhost:3000/api/v1/auth/google/callback"
    assert q["code_challenge_method"] == "S256" and q["scope"] == "openid email profile"
    claims.update(_claims(q))
    r = c.get("/api/v1/auth/google/callback", params={"code": "abc", "state": q["state"]})
    assert r.status_code == 302 and r.headers["location"] == "/goals"
    assert calls[-1]["code"] == "abc" and calls[-1]["code_verifier"]
    me = c.get("/api/v1/auth/me").json()
    assert me["email"] == "new.person@gmail.com" and me["display_name"] == "New Person"
    assert me["preferences"]["base_currency"] == "EUR"
    assert c.get("/api/v1/goals").json()["items"] == []  # brand-new account sees none of the demo data

    # second sign-in reuses the same account
    c2 = _web()
    q2 = _start(c2, "/")
    claims.update(_claims(q2, email="renamed@gmail.com"))
    assert c2.get("/api/v1/auth/google/callback", params={"code": "x", "state": q2["state"]}).headers["location"] == "/"
    assert c2.get("/api/v1/auth/me").json()["id"] == me["id"]
    assert db.scalar(select(User).where(User.google_sub == "g-1001")).email == "new.person@gmail.com"


@pytest.mark.parametrize("bad", [{"aud": "someone-else"}, {"iss": "https://evil.example"}, {"nonce": "replayed"},
                                 {"exp": 1}, {"email_verified": False}])
def test_google_rejects_bad_tokens(google, bad):
    claims, _ = google
    c = _web()
    q = _start(c)
    claims.update(_claims(q, sub="g-bad", **bad))
    r = c.get("/api/v1/auth/google/callback", params={"code": "abc", "state": q["state"]})
    assert r.status_code == 302 and r.headers["location"].startswith("/login?error=google_")
    assert c.get("/api/v1/auth/me").status_code == 401


def test_google_rejects_state_mismatch_and_missing_cookie(google):
    claims, calls = google
    c = _web()
    q = _start(c)
    claims.update(_claims(q))
    assert c.get("/api/v1/auth/google/callback", params={"code": "abc", "state": "forged"}).headers["location"] == "/login?error=google_failed"
    # the flow cookie is single-use, and a callback without it is refused
    assert _web().get("/api/v1/auth/google/callback", params={"code": "abc", "state": q["state"]}).headers["location"] == "/login?error=google_expired"
    assert not calls


def test_google_open_redirect_blocked(google):
    claims, _ = google
    c = _web()
    q = _start(c, "//evil.example/phish")
    claims.update(_claims(q, sub="g-redirect", email="r@gmail.com"))
    assert c.get("/api/v1/auth/google/callback", params={"code": "abc", "state": q["state"]}).headers["location"] == "/"


def test_google_links_existing_account_and_enforces_mfa(google, db):
    claims, _ = google
    secret = pyotp.random_base32()
    u = User(email="mfa.user@gmail.com", display_name="MFA", mfa_enabled=True)
    db.add(u)
    db.flush()
    u.totp_secret_enc = encrypt_secret({"secret": secret}, aad=f"totp:{u.id}")
    db.commit()

    c = _web()
    q = _start(c)
    claims.update(_claims(q, sub="g-mfa", email="MFA.user@gmail.com"))
    r = c.get("/api/v1/auth/google/callback", params={"code": "abc", "state": q["state"]})
    assert r.headers["location"].startswith("/login?mfa=google")
    assert c.get("/api/v1/auth/me").status_code == 401  # no session until the code is entered
    assert c.post("/api/v1/auth/google/mfa", json={"totp": "000000"}).status_code == 401
    r = c.post("/api/v1/auth/google/mfa", json={"totp": pyotp.TOTP(secret).now()})
    assert r.status_code == 200 and r.json()["id"] == u.id
    assert c.get("/api/v1/auth/me").json()["email"] == "mfa.user@gmail.com"
    db.expire_all()
    assert db.get(User, u.id).google_sub == "g-mfa"


def test_google_account_and_data_persist_across_logout(google, db):
    claims, _ = google

    def sign_in() -> TestClient:
        c = _web()
        q = _start(c)
        claims.update(_claims(q, sub="g-persist", email="persist@gmail.com"))
        c.get("/api/v1/auth/google/callback", params={"code": "abc", "state": q["state"]})
        c.headers["X-CSRF-Token"] = c.cookies.get("1f_csrf")
        return c

    c = sign_in()
    uid = c.get("/api/v1/auth/me").json()["id"]
    gid = c.post("/api/v1/goals", json={"name": "Buy Car", "goal_type": "car", "target_amount": "20000", "currency": "EUR"}).json()["id"]
    c.post(f"/api/v1/goals/{gid}/contributions", json={"amount": "750", "note": "First saving"})
    assert c.post("/api/v1/auth/logout").status_code == 200
    assert c.get("/api/v1/auth/me").status_code == 401

    c2 = sign_in()  # a later, separate sign-in with the same Google account
    assert c2.get("/api/v1/auth/me").json()["id"] == uid
    g = next(x for x in c2.get("/api/v1/goals").json()["items"] if x["id"] == gid)
    assert g["name"] == "Buy Car" and g["contributions"][0]["note"] == "First saving"


def test_session_survives_long_idle_gap(google, db):
    from datetime import datetime, timedelta, timezone
    from app.models import UserSession

    claims, _ = google
    c = _web()
    q = _start(c)
    claims.update(_claims(q, sub="g-idle", email="idle@gmail.com"))
    r = c.get("/api/v1/auth/google/callback", params={"code": "abc", "state": q["state"]})
    assert "max-age=2592000" in r.headers["set-cookie"].lower()  # cookie kept for 30 days, survives browser restarts
    sess = db.scalars(select(UserSession).order_by(UserSession.id.desc())).first()
    sess.last_seen_at = datetime.now(timezone.utc) - timedelta(days=3)
    db.commit()
    assert c.get("/api/v1/auth/me").status_code == 200  # 3 days away: still signed in
    sess.last_seen_at = datetime.now(timezone.utc) - timedelta(days=15)
    db.commit()
    assert c.get("/api/v1/auth/me").status_code == 401  # unused for over 14 days: signed out
