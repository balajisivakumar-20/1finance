"""Investment return calculations.

- simple / unrealized return: (market value − cost basis) / cost basis
- TWR (time-weighted): chain-links sub-period returns between external cash flows. Removes the effect of
  deposits/withdrawals, so it measures the manager/market, not the investor's timing.
- MWR (money-weighted): XIRR of external flows plus terminal value. Reflects the investor's timing.

External flows are deposits (+, money into the portfolio) and withdrawals (−). Buys/sells inside the portfolio
are NOT external flows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import ZERO


@dataclass(frozen=True, slots=True)
class HoldingPL:
    market_value: Decimal
    cost_basis: Decimal

    @property
    def unrealized(self) -> Decimal:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pct(self) -> Decimal | None:
        return None if self.cost_basis == 0 else self.unrealized / self.cost_basis * 100


@dataclass(frozen=True, slots=True)
class ValuationPoint:
    on: date
    value: Decimal  # portfolio value at end of day, AFTER that day's external flow
    flow: Decimal = ZERO  # external flow on that day (+ deposit, − withdrawal)


def time_weighted_return(points: list[ValuationPoint]) -> Decimal | None:
    """TWR over the series. Sub-period return r_i = (V_i − F_i) / V_{i−1} − 1.

    Returns a percentage, or None if fewer than two points or a zero starting value makes it undefined.
    """
    pts = sorted(points, key=lambda p: p.on)
    if len(pts) < 2:
        return None
    growth = Decimal(1)
    for prev, cur in zip(pts, pts[1:]):
        if prev.value == 0:
            if cur.value - cur.flow == 0:
                continue  # empty period
            return None
        growth *= (cur.value - cur.flow) / prev.value
    return (growth - 1) * 100


def xirr(flows: list[tuple[date, Decimal]], guess: Decimal = Decimal("0.1")) -> Decimal | None:
    """Annualized IRR for irregular flows (investor perspective: contributions negative, proceeds positive).

    Newton–Raphson with bisection fallback. Returns a percentage or None if no sign change / no convergence.
    """
    if not flows or not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    flows = sorted(flows)
    t0 = flows[0][0]
    yrs = [(Decimal((d - t0).days) / Decimal(365), a) for d, a in flows]

    def npv(r: Decimal) -> Decimal:
        return sum((a / (1 + r) ** t for t, a in yrs), ZERO)

    def dnpv(r: Decimal) -> Decimal:
        return sum((-t * a / (1 + r) ** (t + 1) for t, a in yrs), ZERO)

    r = guess
    for _ in range(100):
        f, df = npv(r), dnpv(r)
        if df == 0:
            break
        nr = r - f / df
        if nr <= -1:
            break
        if abs(nr - r) < Decimal("1e-12"):
            return nr * 100
        r = nr
    lo, hi = Decimal("-0.9999"), Decimal("100")
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < Decimal("1e-10"):
            return mid * 100
        if flo * fm < 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2 * 100


def money_weighted_return(points: list[ValuationPoint]) -> Decimal | None:
    """MWR = XIRR of (−initial value, −deposits, +withdrawals, +terminal value)."""
    pts = sorted(points, key=lambda p: p.on)
    if len(pts) < 2:
        return None
    flows: list[tuple[date, Decimal]] = [(pts[0].on, -pts[0].value)]
    for p in pts[1:-1]:
        if p.flow:
            flows.append((p.on, -p.flow))
    last = pts[-1]
    flows.append((last.on, last.value - last.flow))
    if last.flow:
        flows.append((last.on, -last.flow))
    return xirr(flows)


def decompose_change(
    start_value_base: Decimal, end_value_base: Decimal, net_contributions_base: Decimal, fx_effect_base: Decimal
) -> dict[str, Decimal]:
    """Split the change in portfolio value (in base currency) into contributions, FX and market performance."""
    total = end_value_base - start_value_base
    market = total - net_contributions_base - fx_effect_base
    return {"total_change": total, "contributions": net_contributions_base, "fx_effect": fx_effect_base, "market": market}
