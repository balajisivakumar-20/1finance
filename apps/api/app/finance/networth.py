"""Net worth and asset allocation."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from .fx import FxConverter, MissingRateError
from .money import ZERO, Money

ASSET, LIABILITY = "asset", "liability"


@dataclass(frozen=True, slots=True)
class Position:
    """One balance line contributing to net worth (an account balance, a holding, a manual asset, a loan)."""

    key: str  # stable id, e.g. "account:42" — used for de-duplication
    side: str  # "asset" | "liability"
    category: str  # allocation bucket (bank, stocks, etfs, mutual_funds, fixed_deposits, cash, other, …)
    value: Money  # liabilities are positive amounts owed
    is_demo: bool = False
    is_estimate: bool = False


@dataclass
class NetWorthResult:
    currency: str
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    allocation: dict[str, Decimal]
    missing_rates: list[str] = field(default_factory=list)
    includes_demo: bool = False
    includes_estimates: bool = False


def compute_net_worth(positions: list[Position], fx: FxConverter, base: str, at: datetime) -> NetWorthResult:
    """Net worth = Σ assets − Σ liabilities, all converted at the same instant.

    Positions with duplicate keys are counted once (the first wins) — callers must pass the canonical source.
    Positions whose currency cannot be converted are excluded and reported in `missing_rates`
    rather than silently valued at zero or 1:1.
    """
    seen: set[str] = set()
    assets = liabilities = ZERO
    allocation: dict[str, Decimal] = defaultdict(lambda: ZERO)
    missing: list[str] = []
    demo = estimate = False
    for p in positions:
        if p.key in seen:
            continue
        seen.add(p.key)
        try:
            v = fx.convert(p.value, base, at).converted.amount
        except MissingRateError:
            missing.append(f"{p.value.currency}->{base}")
            continue
        demo |= p.is_demo
        estimate |= p.is_estimate
        if p.side == LIABILITY:
            # A liability balance below zero (overpaid card) is an asset-like credit; keep sign semantics simple:
            liabilities += v
        else:
            assets += v
            allocation[p.category] += v
    return NetWorthResult(
        currency=base,
        total_assets=assets,
        total_liabilities=liabilities,
        net_worth=assets - liabilities,
        allocation=dict(allocation),
        missing_rates=sorted(set(missing)),
        includes_demo=demo,
        includes_estimates=estimate,
    )


def allocation_percentages(allocation: dict[str, Decimal]) -> dict[str, Decimal]:
    """Share of each *positive* bucket in total positive assets (negative cash is shown but not a share)."""
    total = sum((v for v in allocation.values() if v > 0), ZERO)
    if total == 0:
        return {k: ZERO for k in allocation}
    return {k: (v / total * 100 if v > 0 else ZERO) for k, v in allocation.items()}
