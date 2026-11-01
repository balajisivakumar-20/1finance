from decimal import Decimal

from app.finance.money import quantize


def m(v: Decimal | None, currency: str) -> Decimal | None:
    """Presentation rounding (ISO minor units). Only used at the API boundary."""
    return None if v is None else quantize(Decimal(v), currency)


def pct(v: Decimal | None) -> Decimal | None:
    return None if v is None else Decimal(v).quantize(Decimal("0.01"))


def qty(v: Decimal | None) -> Decimal | None:
    return None if v is None else Decimal(v).normalize() if Decimal(v) == Decimal(v).to_integral() else Decimal(v).quantize(Decimal("0.0001"))
