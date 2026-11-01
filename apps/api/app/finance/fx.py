"""Currency conversion from *stored* exchange rates. Never hardcoded."""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .money import Money


class MissingRateError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Rate:
    base: str
    quote: str
    rate: Decimal  # 1 base = rate quote
    provider: str
    effective_at: datetime


@dataclass(frozen=True, slots=True)
class Conversion:
    original: Money
    converted: Money
    rate: Decimal
    provider: str
    effective_at: datetime | None
    derived: bool  # True when computed via a cross rate / inversion


class FxConverter:
    """Looks up the latest rate effective on or before a given instant.

    Rates are indexed by (base, quote). Inverse and cross rates (via a pivot currency, EUR by default)
    are derived and marked `derived=True` so the UI can disclose them.
    """

    def __init__(self, rates: list[Rate], pivot: str = "EUR") -> None:
        self.pivot = pivot
        self._series: dict[tuple[str, str], list[Rate]] = {}
        for r in rates:
            self._series.setdefault((r.base, r.quote), []).append(r)
        for s in self._series.values():
            s.sort(key=lambda r: r.effective_at)
        self._keys = {k: [r.effective_at for r in v] for k, v in self._series.items()}

    def _direct(self, base: str, quote: str, at: datetime) -> Rate | None:
        series = self._series.get((base, quote))
        if not series:
            return None
        i = bisect.bisect_right(self._keys[(base, quote)], at) - 1
        return series[i] if i >= 0 else None

    def rate(self, base: str, quote: str, at: datetime) -> tuple[Decimal, str, datetime | None, bool]:
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return Decimal(1), "identity", None, False
        if r := self._direct(base, quote, at):
            return r.rate, r.provider, r.effective_at, False
        if r := self._direct(quote, base, at):
            return Decimal(1) / r.rate, r.provider, r.effective_at, True
        if self.pivot not in (base, quote):
            try:
                r1, p1, t1, _ = self.rate(base, self.pivot, at)
                r2, p2, t2, _ = self.rate(self.pivot, quote, at)
            except MissingRateError:
                pass
            else:
                ts = min(t for t in (t1, t2) if t) if (t1 or t2) else None
                return r1 * r2, p1 if p1 == p2 else f"{p1}+{p2}", ts, True
        raise MissingRateError(f"No {base}/{quote} rate on or before {at.isoformat()}")

    def convert(self, money: Money, to: str, at: datetime) -> Conversion:
        to = to.upper()
        # Inverse of a stored rate: divide by it (exact for the stored value) instead of multiplying by 1/rate.
        if money.currency != to and not self._direct(money.currency, to, at):
            if r := self._direct(to, money.currency, at):
                return Conversion(money, Money(money.amount / r.rate, to), Decimal(1) / r.rate, r.provider, r.effective_at, True)
        rate, provider, ts, derived = self.rate(money.currency, to, at)
        return Conversion(money, Money(money.amount * rate, to), rate, provider, ts, derived)
