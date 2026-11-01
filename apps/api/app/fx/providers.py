"""Exchange-rate providers. Rates are persisted with provider + effective timestamp; nothing is hardcoded."""
from __future__ import annotations

import abc
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExchangeRate

ECB_DAILY = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_HIST_90 = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
NS = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}


class ExchangeRateProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def fetch(self, history: bool = False) -> list[tuple[str, str, Decimal, datetime]]:
        """Return (base, quote, rate, effective_at) tuples."""


class ECBProvider(ExchangeRateProvider):
    """European Central Bank reference rates (EUR base, ~16:00 CET on TARGET business days)."""

    name = "ecb"

    def __init__(self, client: httpx.Client | None = None, quotes: tuple[str, ...] = ("USD", "GBP", "INR")):
        self.http = client or httpx.Client(timeout=20)
        self.quotes = quotes

    @staticmethod
    def parse(xml: str, quotes: tuple[str, ...]) -> list[tuple[str, str, Decimal, datetime]]:
        root = ET.fromstring(xml)
        out = []
        for day in root.findall(".//e:Cube[@time]", NS):
            ts = datetime.strptime(day.get("time"), "%Y-%m-%d").replace(hour=14, minute=0, tzinfo=timezone.utc)
            for c in day.findall("e:Cube", NS):
                if c.get("currency") in quotes:
                    out.append(("EUR", c.get("currency"), Decimal(c.get("rate")), ts))
        return out

    def fetch(self, history: bool = False):
        r = self.http.get(ECB_HIST_90 if history else ECB_DAILY)
        r.raise_for_status()
        return self.parse(r.text, self.quotes)


def store_rates(db: Session, provider: ExchangeRateProvider, history: bool = False) -> int:
    n = 0
    for base, quote, rate, ts in provider.fetch(history):
        exists = db.scalar(select(ExchangeRate.id).where(ExchangeRate.base_currency == base, ExchangeRate.quote_currency == quote,
                                                         ExchangeRate.provider == provider.name, ExchangeRate.effective_timestamp == ts))
        if not exists:
            db.add(ExchangeRate(base_currency=base, quote_currency=quote, rate=rate, provider=provider.name, effective_timestamp=ts))
            n += 1
    db.flush()
    return n
