from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from app.categorization.engine import Categorizer, Rule, merchant_key
from app.finance.cashflow import Txn, budget_status, savings_rate, summarize
from app.finance.fx import FxConverter, MissingRateError, Rate
from app.finance.money import Money, pct_change, quantize
from app.finance.networth import Position, allocation_percentages, compute_net_worth
from app.finance.reconcile import Candidate, TransferLeg, classify_duplicate, find_transfer_pairs, normalize_description
from app.finance.returns import HoldingPL, ValuationPoint, decompose_change, money_weighted_return, time_weighted_return, xirr


def dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


RATES = [
    Rate("EUR", "INR", D("90"), "test", dt(2026, 1, 1)),
    Rate("EUR", "INR", D("95"), "test", dt(2026, 6, 1)),
    Rate("EUR", "USD", D("1.10"), "test", dt(2026, 1, 1)),
    Rate("EUR", "GBP", D("0.85"), "test", dt(2026, 1, 1)),
]
FX = FxConverter(RATES)


# ---------- money ----------
def test_money_rejects_float():
    with pytest.raises(TypeError):
        Money(1.1, "EUR")


def test_money_currency_mismatch():
    with pytest.raises(ValueError):
        Money(D(1), "EUR") + Money(D(1), "USD")


def test_quantize_bankers_rounding_display_only():
    assert quantize(D("2.345"), "EUR") == D("2.34")
    assert quantize(D("2.355"), "EUR") == D("2.36")
    assert quantize(D("1234.5"), "JPY") == D("1234")


def test_pct_change_zero_base():
    assert pct_change(D(10), D(0)) is None
    assert pct_change(D(110), D(100)) == D(10)
    assert pct_change(D(-50), D(-100)) == D(50)  # debt shrinking is an improvement


# ---------- fx ----------
def test_fx_direct_uses_rate_effective_on_date():
    assert FX.convert(Money(D(900), "INR"), "EUR", dt(2026, 3, 1)).converted.amount == D(10)
    assert FX.convert(Money(D(950), "INR"), "EUR", dt(2026, 7, 1)).converted.amount == D(10)


def test_fx_inverse_and_cross_are_marked_derived():
    c = FX.convert(Money(D(100), "EUR"), "INR", dt(2026, 2, 1))
    assert c.converted.amount == D(9000) and not c.derived
    c = FX.convert(Money(D(110), "USD"), "GBP", dt(2026, 2, 1))
    assert c.derived and abs(c.converted.amount - D("85")) < D("1e-20")


def test_fx_missing_rate_raises_not_guesses():
    with pytest.raises(MissingRateError):
        FX.convert(Money(D(1), "INR"), "EUR", dt(2025, 12, 1))
    with pytest.raises(MissingRateError):
        FX.convert(Money(D(1), "CHF"), "EUR", dt(2026, 2, 1))


# ---------- net worth ----------
def test_net_worth_assets_minus_liabilities_multi_currency():
    pos = [
        Position("acc:1", "asset", "bank", Money(D("1000"), "EUR")),
        Position("acc:2", "asset", "stocks", Money(D("95000"), "INR")),
        Position("acc:3", "liability", "credit_card", Money(D("250"), "EUR")),
    ]
    r = compute_net_worth(pos, FX, "EUR", dt(2026, 7, 1))
    assert r.total_assets == D(2000)
    assert r.total_liabilities == D(250)
    assert r.net_worth == D(1750)


def test_net_worth_deduplicates_same_key():
    pos = [Position("ibkr:cash", "asset", "cash", Money(D(500), "EUR"))] * 2
    assert compute_net_worth(pos, FX, "EUR", dt(2026, 7, 1)).total_assets == D(500)


def test_net_worth_reports_missing_rates_instead_of_zero():
    pos = [Position("a", "asset", "bank", Money(D(10), "CHF")), Position("b", "asset", "bank", Money(D(10), "EUR"))]
    r = compute_net_worth(pos, FX, "EUR", dt(2026, 7, 1))
    assert r.total_assets == D(10) and r.missing_rates == ["CHF->EUR"]


def test_negative_cash_balance_reduces_assets():
    pos = [Position("a", "asset", "bank", Money(D(100), "EUR")), Position("b", "asset", "cash", Money(D(-30), "EUR"))]
    r = compute_net_worth(pos, FX, "EUR", dt(2026, 7, 1))
    assert r.total_assets == D(70)
    pct = allocation_percentages(r.allocation)
    assert pct["bank"] == D(100) and pct["cash"] == D(0)


def test_allocation_empty():
    assert allocation_percentages({"bank": D(0)}) == {"bank": D(0)}


# ---------- cash flow ----------
def _t(i, amt, typ, cat=None, status="posted", cur="EUR", when=dt(2026, 7, 2)):
    return Txn(str(i), when, Money(D(amt), cur), typ, cat, status)


def test_cashflow_excludes_transfers_and_investments_and_handles_refunds():
    txns = [
        _t(1, "3000", "income", "salary"),
        _t(2, "-100", "expense", "groceries"),
        _t(3, "20", "refund", "groceries"),
        _t(4, "-500", "transfer"),
        _t(5, "-1000", "investment_buy"),
        _t(6, "-9500", "expense", "rent", cur="INR"),
        _t(7, "-50", "expense", "restaurants", status="pending"),
        _t(8, "-70", "expense", "shopping", status="reversed"),
        _t(9, "12", "dividend"),
    ]
    s = summarize(txns, FX, "EUR")
    assert s.income == D(3000)
    assert s.expenses == D(180)  # 100 − 20 + 100 (9500 INR @95)
    assert s.by_category == {"groceries": D(80), "rent": D(100)}
    assert s.transfers_excluded == 1 and s.pending_excluded == 1
    assert s.investment_income == D(12)
    assert s.savings == D(2820)
    assert s.savings_rate == D(94)


def test_savings_rate_zero_income_is_undefined():
    assert savings_rate(D(0), D(100)) is None
    assert savings_rate(D(-5), D(0)) is None
    assert savings_rate(D(1000), D(1200)) == D(-20)


def test_budget_status_thresholds():
    assert budget_status(D(50), D(100)) == (D(50), "ok")
    assert budget_status(D(80), D(100)) == (D(80), "warning")
    assert budget_status(D(101), D(100))[1] == "over"
    assert budget_status(D(10), D(0)) == (None, "no_budget")


# ---------- returns ----------
def test_holding_pl():
    h = HoldingPL(D(1200), D(1000))
    assert h.unrealized == D(200) and h.unrealized_pct == D(20)
    assert HoldingPL(D(5), D(0)).unrealized_pct is None


def test_twr_ignores_deposits():
    # 1000 → grows 10% to 1100, deposit 1000 → 2100, grows 10% → 2310. TWR = 1.1*1.1 − 1 = 21 %
    pts = [
        ValuationPoint(date(2026, 1, 1), D(1000)),
        ValuationPoint(date(2026, 2, 1), D(2100), D(1000)),
        ValuationPoint(date(2026, 3, 1), D(2310)),
    ]
    assert time_weighted_return(pts) == D(21)


def test_twr_insufficient_data():
    assert time_weighted_return([ValuationPoint(date(2026, 1, 1), D(1))]) is None


def test_xirr_simple_one_year():
    r = xirr([(date(2025, 1, 1), D(-1000)), (date(2026, 1, 1), D(1100))])
    assert abs(r - D(10)) < D("0.0001")


def test_xirr_no_sign_change():
    assert xirr([(date(2025, 1, 1), D(100)), (date(2026, 1, 1), D(100))]) is None


def test_mwr_reflects_timing():
    pts = [
        ValuationPoint(date(2025, 1, 1), D(1000)),
        ValuationPoint(date(2026, 1, 1), D(1100)),
    ]
    assert abs(money_weighted_return(pts) - D(10)) < D("0.0001")


def test_decompose_change_separates_contributions_fx_market():
    d = decompose_change(D(10000), D(12500), D(1500), D(-200))
    assert d == {"total_change": D(2500), "contributions": D(1500), "fx_effect": D(-200), "market": D(1200)}


# ---------- dedup & transfers ----------
def test_dedup_by_provider_id():
    e = [Candidate("a", "X1", dt(2026, 7, 1), D(-10), "EUR", "Tesco")]
    n = Candidate("a", "X1", dt(2026, 7, 1), D(-10), "EUR", "Tesco")
    assert classify_duplicate(n, e).status == "duplicate"


def test_dedup_fuzzy_is_only_flagged():
    e = [Candidate("a", None, dt(2026, 7, 1), D(-10), "EUR", "TESCO STORES 3321 DUBLIN")]
    n = Candidate("a", None, dt(2026, 7, 2), D(-10), "EUR", "Tesco Stores 9981 Dublin")
    assert classify_duplicate(n, e).status == "possible_duplicate"


def test_dedup_different_ids_are_not_duplicates():
    e = [Candidate("a", "X1", dt(2026, 7, 1), D(-3), "EUR", "Coffee")]
    n = Candidate("a", "X2", dt(2026, 7, 1), D(-3), "EUR", "Coffee")
    assert classify_duplicate(n, e).status == "new"


def test_dedup_different_amount_is_new():
    e = [Candidate("a", None, dt(2026, 7, 1), D(-10), "EUR", "Tesco")]
    assert classify_duplicate(Candidate("a", None, dt(2026, 7, 1), D(-11), "EUR", "Tesco"), e).status == "new"


def test_normalize_description():
    assert normalize_description("CARD 1234 *TESCO* Ref:99881") == "tesco"


def test_transfer_pairs_cross_account_with_fx_tolerance():
    legs = [
        TransferLeg("o1", "revolut", dt(2026, 7, 1), D("-1000"), "transfer"),
        TransferLeg("i1", "ibkr", dt(2026, 7, 2), D("995"), "deposit"),
        TransferLeg("i2", "revolut", dt(2026, 7, 1), D("1000"), "income"),  # same account → not a pair
        TransferLeg("o2", "revolut", dt(2026, 7, 5), D("-50"), "expense"),
    ]
    assert find_transfer_pairs(legs) == [("o1", "i1")]


# ---------- categorization ----------
def test_categorizer_precedence():
    c = Categorizer(rules=[Rule("r1", "tesco", "household", 10)], learned={})
    assert c.categorize("TESCO STORES").source == "rule"
    c = Categorizer()
    r = c.categorize("TESCO STORES 3321")
    assert (r.category, r.source) == ("groceries", "dictionary")
    c.learn("Corner Shop Rathmines", None, "groceries")
    assert c.categorize("CORNER SHOP RATHMINES 99812").source == "learned"
    assert c.categorize("zzqx unknown").category == "uncategorized"


def test_categorizer_ai_needs_consent():
    calls = []

    def ai(desc):
        calls.append(desc)
        return "hobbies"

    assert Categorizer(ai=ai, ai_consent=False).categorize("zzqx").category == "uncategorized"
    assert calls == []
    assert Categorizer(ai=ai, ai_consent=True).categorize("zzqx").source == "ai"


def test_regex_rule_and_bad_regex():
    assert Rule("r", "/^net.*x$/", "streaming").matches("Netflix", None)
    assert not Rule("r", "/[/", "x").matches("anything", None)


def test_merchant_key_stable():
    assert merchant_key("SPOTIFY P1234567 STOCKHOLM") == merchant_key("Spotify P7654321 Stockholm")
