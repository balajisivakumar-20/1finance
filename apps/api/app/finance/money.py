"""Money primitives. All monetary math uses Decimal; floats are rejected."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, getcontext

getcontext().prec = 38

# ISO 4217 minor units for supported currencies (extend freely).
MINOR_UNITS: dict[str, int] = {"EUR": 2, "USD": 2, "GBP": 2, "INR": 2, "CHF": 2, "JPY": 0, "SGD": 2}
SUPPORTED_CURRENCIES = ("EUR", "INR", "USD", "GBP")

ZERO = Decimal("0")


def to_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("Floats are not allowed for money; pass str or Decimal")
    return value if isinstance(value, Decimal) else Decimal(value)


def quantize(amount: Decimal, currency: str) -> Decimal:
    """Round for display/export only — never for intermediate calculations."""
    places = MINOR_UNITS.get(currency.upper(), 2)
    return amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_decimal(self.amount))
        object.__setattr__(self, "currency", self.currency.upper())

    def _check(self, other: "Money") -> None:
        if other.currency != self.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def rounded(self) -> Decimal:
        return quantize(self.amount, self.currency)


def pct_change(current: Decimal, previous: Decimal) -> Decimal | None:
    """Percentage change; None when the base is zero (undefined)."""
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100
