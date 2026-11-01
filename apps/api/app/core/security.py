"""Password hashing, session tokens, CSRF, TOTP, credential encryption, log redaction."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_settings

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_valid(cookie: str | None, header: str | None) -> bool:
    return bool(cookie and header and hmac.compare_digest(cookie, header))


# ---- TOTP MFA ----
def new_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="1Finance")


# ---- credential encryption (AES-256-GCM) ----
def _key() -> bytes:
    k = get_settings().credential_key
    if not k:
        # Development only: derive a per-process key file so secrets are never stored in plaintext.
        path = os.path.join(os.path.dirname(__file__), "..", "..", ".dev_credential_key")
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(base64.b64encode(AESGCM.generate_key(bit_length=256)))
            os.chmod(path, 0o600)
        k = open(path, "rb").read().decode()
    raw = base64.b64decode(k)
    if len(raw) != 32:
        raise RuntimeError("Credential key must be 32 bytes (base64)")
    return raw


def encrypt_secret(data: dict, aad: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, json.dumps(data).encode(), aad.encode())
    return base64.b64encode(nonce + ct).decode()


def decrypt_secret(blob: str, aad: str) -> dict:
    raw = base64.b64decode(blob)
    return json.loads(AESGCM(_key()).decrypt(raw[:12], raw[12:], aad.encode()))


# ---- log redaction ----
_SECRET_RX = re.compile(r"(?i)(token|secret|password|authorization|api[_-]?key|totp)([\"'\s:=]+)([^\s\"'&,}]+)")


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _SECRET_RX.sub(r"\1\2[REDACTED]", str(record.msg))
        if record.args:
            record.args = tuple(_SECRET_RX.sub(r"\1\2[REDACTED]", a) if isinstance(a, str) else a for a in record.args)
        return True


def mask_reference(ref: str | None, visible: int = 4) -> str | None:
    if not ref:
        return ref
    return "•••• " + ref[-visible:] if len(ref) > visible else "••••"
