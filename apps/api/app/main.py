from __future__ import annotations

import logging

from decimal import Decimal

import fastapi.encoders
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import DecimalJSON
from app.api.routes import accounts, auth, investments, overview, planning, settings, transactions
from app.core.config import get_settings
from app.core.security import RedactingFilter

# Money leaves the API as exact decimal strings, never binary floats.
fastapi.encoders.ENCODERS_BY_TYPE[Decimal] = lambda d: format(d, "f")

logging.basicConfig(level=logging.INFO)
for h in logging.getLogger().handlers:
    h.addFilter(RedactingFilter())
log = logging.getLogger("onefinance")

s = get_settings()
app = FastAPI(
    title="1Finance API",
    version="0.1.0",
    default_response_class=DecimalJSON,
    docs_url=None if s.is_production else "/api/docs",
    openapi_url=None if s.is_production else "/api/openapi.json",
)
app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/api/v1"):
        resp.headers["Cache-Control"] = "no-store"  # financial data is never cached by browsers or the service worker
    if s.is_production:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return resp


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    errs = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse({"detail": "Invalid request", "errors": errs}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error")  # stack trace stays server-side
    return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)


@app.get("/api/health")
def health():
    return {"status": "ok", "env": s.env, "demo_mode": s.demo_mode, "google_enabled": s.google_enabled}


for r in (auth, overview, accounts, transactions, investments, planning, settings):
    app.include_router(r.router, prefix="/api/v1")
