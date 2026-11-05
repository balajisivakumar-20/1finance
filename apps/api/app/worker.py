"""Celery worker + beat schedule: periodic sync and daily FX refresh.

    celery -A app.worker worker -B --loglevel=info
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from celery import Celery
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import session_factory
from app.fx.providers import ECBProvider, store_rates
from app.models import Connection, ExchangeRate
from app.sync.engine import run_sync

celery = Celery("onefinance", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "sync-all-every-6h": {"task": "app.worker.sync_all_connections", "schedule": 6 * 3600},
        "fx-daily": {"task": "app.worker.refresh_fx", "schedule": 6 * 3600},
    },
)


@celery.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=900, max_retries=5)
def sync_connection(connection_id: int) -> str:
    db = session_factory()()
    try:
        conn = db.get(Connection, connection_id)
        if not conn or conn.connection_status in ("disconnected", "reauth_required"):
            return "skipped"
        job = run_sync(db, conn, trigger="scheduled")
        db.commit()
        return job.status
    finally:
        db.close()


@celery.task
def sync_all_connections() -> int:
    db = session_factory()()
    try:
        ids = list(db.scalars(select(Connection.id).where(Connection.connection_status.in_(("active", "error")),
                                                          Connection.connector != "manual")))
    finally:
        db.close()
    for cid in ids:
        sync_connection.delay(cid)
    return len(ids)


@celery.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def refresh_fx() -> int:
    db = session_factory()()
    try:
        # past activity (dividends, trades) is converted at its own date, so fetch the full history once
        oldest = db.scalar(select(func.min(ExchangeRate.effective_timestamp)))
        full = oldest is None or oldest > datetime.now(timezone.utc) - timedelta(days=400)
        n = store_rates(db, ECBProvider(), history=full)
        db.commit()
        return n
    finally:
        db.close()
