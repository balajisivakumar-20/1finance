"""Income, expenses, savings and cash-flow classification.

Transaction types (normalized):
  income, expense, refund, transfer, investment_buy, investment_sell, dividend, interest, fee, withdrawal, deposit

Sign convention: `amount` is signed from the account's perspective (+ inflow, − outflow), in original currency.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .fx import FxConverter, MissingRateError
from .money import ZERO, Money

INCOME_TYPES = {"income", "interest"}
INVESTMENT_INCOME_TYPES = {"dividend"}
EXPENSE_TYPES = {"expense", "fee"}
EXCLUDED_FROM_CASHFLOW = {"transfer"}
INVESTMENT_FLOW_TYPES = {"investment_buy", "investment_sell", "deposit", "withdrawal"}


@dataclass(frozen=True, slots=True)
class Txn:
    id: str
    occurred_at: datetime
    amount: Money
    type: str
    category: str | None = None
    status: str = "posted"  # posted | pending | reversed


@dataclass
class CashflowSummary:
    currency: str
    income: Decimal
    expenses: Decimal  # positive number (net of refunds)
    refunds: Decimal
    investment_income: Decimal
    transfers_excluded: int
    pending_excluded: int
    by_category: dict[str, Decimal]
    missing_rates: list[str]

    @property
    def savings(self) -> Decimal:
        return self.income - self.expenses

    @property
    def savings_rate(self) -> Decimal | None:
        return savings_rate(self.income, self.expenses)


def savings_rate(income: Decimal, expenses: Decimal) -> Decimal | None:
    """(Income − Expenses) / Income × 100. Undefined (None) when income ≤ 0."""
    if income <= 0:
        return None
    return (income - expenses) / income * 100


def summarize(txns: list[Txn], fx: FxConverter, base: str, include_pending: bool = False) -> CashflowSummary:
    """Each transaction is converted at the rate effective on its own date (historical FX)."""
    income = expenses = refunds = inv_income = ZERO
    by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    transfers = pending = 0
    missing: set[str] = set()
    for t in txns:
        if t.status == "reversed":
            continue
        if t.status == "pending" and not include_pending:
            pending += 1
            continue
        if t.type in EXCLUDED_FROM_CASHFLOW:
            transfers += 1
            continue
        try:
            v = fx.convert(t.amount, base, t.occurred_at).converted.amount
        except MissingRateError:
            missing.add(f"{t.amount.currency}->{base}")
            continue
        if t.type in INCOME_TYPES and v > 0:
            income += v
        elif t.type in INVESTMENT_INCOME_TYPES:
            inv_income += v
        elif t.type in EXPENSE_TYPES:
            # outflows are negative; an expense with positive amount is a reversal of that expense
            expenses += -v
            by_cat[t.category or "uncategorized"] += -v
        elif t.type == "refund":
            refunds += v
            expenses -= v
            by_cat[t.category or "uncategorized"] -= v
        # investment flows are deliberately neither income nor expense
    return CashflowSummary(
        currency=base,
        income=income,
        expenses=expenses,
        refunds=refunds,
        investment_income=inv_income,
        transfers_excluded=transfers,
        pending_excluded=pending,
        by_category={k: v for k, v in by_cat.items() if v != 0},
        missing_rates=sorted(missing),
    )


def budget_status(spent: Decimal, budget: Decimal) -> tuple[Decimal | None, str]:
    """Returns (percent used, status) with status ∈ ok | warning | over | no_budget."""
    if budget <= 0:
        return None, "no_budget"
    pct = spent / budget * 100
    if pct > 100:
        return pct, "over"
    if pct >= 80:
        return pct, "warning"
    return pct, "ok"
