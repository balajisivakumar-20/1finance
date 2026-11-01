"""Reference data + clearly-labeled demo data.

    python -m app.seed            # reference data (+ demo data when ONEFINANCE_DEMO_MODE=true)
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import session_factory
from app.core.security import hash_password
from app.models import (
    Asset,
    AssetValuation,
    Budget,
    Category,
    Connection,
    ExchangeRate,
    Goal,
    GoalContribution,
    Institution,
    Liability,
    LiabilitySnapshot,
    Notification,
    User,
    UserPreferences,
)
from app.sync.engine import run_sync

DEMO_EMAIL = "demo@1finance.app"
DEMO_PASSWORD = "demo-1finance"

CATEGORIES: list[tuple[str, str, str, str, str, list[tuple[str, str]]]] = [
    # slug, name, type, icon, color, children
    ("housing", "Housing", "expense", "home", "#0F766E", [("rent", "Rent"), ("mortgage", "Mortgage"), ("maintenance", "Maintenance")]),
    ("food", "Food", "expense", "utensils", "#047857", [("groceries", "Groceries"), ("restaurants", "Restaurants"),
                                                        ("food_delivery", "Food delivery"), ("coffee", "Coffee")]),
    ("transport", "Transport", "expense", "train-front", "#2563EB", [("public_transport", "Public transport"), ("fuel", "Fuel"),
                                                                    ("taxi", "Taxi"), ("parking", "Parking")]),
    ("shopping", "Shopping", "expense", "shopping-bag", "#B45309", [("clothing", "Clothing"), ("electronics", "Electronics"),
                                                                  ("household", "Household")]),
    ("utilities", "Utilities", "expense", "plug", "#7C3AED", [("electricity", "Electricity"), ("internet", "Internet"),
                                                              ("mobile", "Mobile"), ("water", "Water")]),
    ("subscriptions", "Subscriptions", "expense", "repeat", "#DB2777", [("streaming", "Streaming"), ("software", "Software"),
                                                                       ("memberships", "Memberships")]),
    ("health", "Health", "expense", "heart-pulse", "#DC2626", [("pharmacy", "Pharmacy"), ("medical", "Medical"), ("fitness", "Fitness")]),
    ("entertainment", "Entertainment", "expense", "ticket", "#9333EA", [("movies", "Movies"), ("events", "Events"), ("hobbies", "Hobbies")]),
    ("travel", "Travel", "expense", "plane", "#0891B2", [("flights", "Flights"), ("hotels", "Hotels"), ("holidays", "Holidays")]),
    ("financial", "Financial", "expense", "landmark", "#475569", [("bank_fees", "Bank fees"), ("brokerage_fees", "Brokerage fees"),
                                                                 ("interest_expenses", "Interest expenses")]),
    ("other", "Other", "expense", "circle-dashed", "#64748B", [("miscellaneous", "Miscellaneous"), ("cash", "Cash withdrawals"),
                                                               ("uncategorized", "Uncategorized")]),
    ("income", "Income", "income", "wallet", "#15803D", [("salary", "Salary"), ("interest_income", "Interest"),
                                                         ("other_income", "Other income")]),
    ("transfers", "Transfers", "transfer", "arrow-left-right", "#6B7280", []),
]

INSTITUTIONS = [
    ("interactive-brokers", "Interactive Brokers", "brokerage", "US", {"holdings": True, "transactions": True, "history": True}),
    ("groww", "Groww", "brokerage", "IN", {"holdings": True, "transactions": False, "mutual_funds": "manual_import"}),
    ("revolut", "Revolut", "bank", "LT", {"balances": "aggregator", "transactions": "statement_import"}),
    ("statement-import", "Statement import", "import", None, {"transactions": True}),
    ("manual", "Manual", "manual", None, {"balances": True}),
]


def seed_reference(db: Session) -> None:
    for slug, name, ptype, country, feats in INSTITUTIONS:
        if not db.scalar(select(Institution).where(Institution.slug == slug)):
            db.add(Institution(slug=slug, name=name, provider_type=ptype, country=country, supported_features=feats))
    for slug, name, ctype, icon, color, children in CATEGORIES:
        parent = db.scalar(select(Category).where(Category.user_id.is_(None), Category.slug == slug))
        if not parent:
            parent = Category(slug=slug, name=name, category_type=ctype, icon=icon, color=color)
            db.add(parent)
            db.flush()
        for cslug, cname in children:
            if not db.scalar(select(Category).where(Category.user_id.is_(None), Category.slug == cslug)):
                db.add(Category(slug=cslug, name=cname, category_type=ctype, parent_category_id=parent.id, color=color, icon=icon))
    db.flush()


def _seed_fx(db: Session, days: int = 410) -> None:
    """DEMO exchange rates (provider='demo'). Production uses the ECB provider in app/fx/providers.py."""
    if db.scalar(select(ExchangeRate).where(ExchangeRate.provider == "demo").limit(1)):
        return
    rng = random.Random(42)
    today = datetime.now(timezone.utc).date()
    levels = {"INR": 96.2, "USD": 1.085, "GBP": 0.848}
    vol = {"INR": 0.004, "USD": 0.004, "GBP": 0.002}
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        ts = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
        for q in levels:
            levels[q] *= math.exp(vol[q] * rng.gauss(0, 1))
            db.add(ExchangeRate(base_currency="EUR", quote_currency=q, rate=Decimal(f"{levels[q]:.6f}"), provider="demo", effective_timestamp=ts))
    db.flush()


def seed_demo(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user:
        return user
    user = User(email=DEMO_EMAIL, display_name="Balaji", password_hash=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.flush()
    db.add(UserPreferences(user_id=user.id, base_currency="EUR", timezone="Europe/Dublin"))
    _seed_fx(db)
    inst = {i.slug: i for i in db.scalars(select(Institution))}
    for key, slug in (("mock_revolut", "revolut"), ("mock_ibkr", "interactive-brokers"), ("mock_groww", "groww")):
        conn = Connection(user_id=user.id, institution_id=inst[slug].id, connector=key, authentication_method="mock", is_demo=True)
        db.add(conn)
        db.flush()
        run_sync(db, conn, trigger="seed", backfill=True)

    today = datetime.now(timezone.utc).date()
    # manual asset + liabilities (estimates are labeled as such)
    fd = Asset(user_id=user.id, asset_name="SBI Fixed Deposit", asset_type="fixed_deposit", currency="INR",
               valuation_method="manual_estimate", notes="Demo: 7.1% p.a., matures 2027", is_demo=True)
    db.add(fd)
    db.flush()
    for m in range(13, -1, -1):
        d = today - timedelta(days=30 * m)
        db.add(AssetValuation(asset_id=fd.id, valuation_amount=Decimal(500000) * Decimal(str((1 + 0.071 / 12) ** (13 - m))),
                              valuation_date=d, valuation_source="manual"))
    loan = Liability(user_id=user.id, liability_name="Education loan", liability_type="education_loan", currency="INR",
                     interest_rate=Decimal("9.25"), payment_amount=Decimal("18500"), payment_frequency="monthly",
                     next_payment_date=(today.replace(day=1) + timedelta(days=35)).replace(day=5), is_demo=True)
    card = Liability(user_id=user.id, liability_name="AIB Credit Card", liability_type="credit_card", currency="EUR",
                     interest_rate=Decimal("22.9"), payment_frequency="monthly", is_demo=True)
    db.add_all([loan, card])
    db.flush()
    rng = random.Random(7)
    for m in range(13, -1, -1):
        d = today - timedelta(days=30 * m)
        db.add(LiabilitySnapshot(liability_id=loan.id, outstanding_amount=Decimal(820000 - (13 - m) * 11800), snapshot_date=d))
        db.add(LiabilitySnapshot(liability_id=card.id, outstanding_amount=Decimal(f"{rng.uniform(250, 900):.2f}"), snapshot_date=d))
    # budgets
    cats = {c.slug: c.id for c in db.scalars(select(Category).where(Category.user_id.is_(None)))}
    for slug, amt in (("groceries", 420), ("restaurants", 220), ("shopping", 200), ("transport", 120),
                      ("subscriptions", 60), ("entertainment", 60), ("utilities", 200)):
        db.add(Budget(user_id=user.id, category_id=cats[slug], amount=Decimal(amt), currency="EUR"))
    # goals
    g1 = Goal(user_id=user.id, goal_name="Emergency fund", goal_type="emergency", target_amount=Decimal(15000),
              target_currency="EUR", target_date=today.replace(year=today.year + 1), monthly_contribution_plan=Decimal(600))
    g2 = Goal(user_id=user.id, goal_name="Japan holiday", goal_type="holiday", target_amount=Decimal(4500),
              target_currency="EUR", target_date=today + timedelta(days=240), monthly_contribution_plan=Decimal(300))
    g3 = Goal(user_id=user.id, goal_name="Home down payment", goal_type="home", target_amount=Decimal(60000),
              target_currency="EUR", target_date=today.replace(year=today.year + 4), monthly_contribution_plan=Decimal(900))
    db.add_all([g1, g2, g3])
    db.flush()
    for i in range(8):
        d = today - timedelta(days=30 * (8 - i))
        db.add(GoalContribution(goal_id=g1.id, amount=Decimal(600), currency="EUR", contribution_date=d))
        if i % 2 == 0:
            db.add(GoalContribution(goal_id=g2.id, amount=Decimal(300), currency="EUR", contribution_date=d))
        db.add(GoalContribution(goal_id=g3.id, amount=Decimal(900), currency="EUR", contribution_date=d))
    db.add(Notification(user_id=user.id, kind="info", title="Welcome to 1Finance",
                        body="You're viewing demonstration data. Connect a real account from Accounts → Add account."))
    db.flush()
    return user


def main() -> None:
    db = session_factory()()
    try:
        seed_reference(db)
        if get_settings().demo_mode:
            seed_demo(db)
        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
