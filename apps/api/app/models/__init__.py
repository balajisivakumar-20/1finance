"""SQLAlchemy ORM models. Money = NUMERIC(20, 8); timestamps = timestamptz (UTC)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

Money = Numeric(20, 8)
Json = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


TS = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)
    preferences: Mapped["UserPreferences"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Dublin")
    theme: Mapped[str] = mapped_column(String(10), default="system")
    number_format: Mapped[str] = mapped_column(String(16), default="en-IE")
    date_format: Mapped[str] = mapped_column(String(16), default="d MMM yyyy")
    ai_categorization_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    hide_balances_in_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    user: Mapped[User] = relationship(back_populates="preferences")


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip: Mapped[str | None] = mapped_column(String(64))
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[str] = mapped_column(String(512), unique=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    provider_type: Mapped[str] = mapped_column(String(32))  # brokerage | bank | import | manual
    country: Mapped[str | None] = mapped_column(String(2))
    supported_features: Mapped[dict] = mapped_column(Json, default=dict)


class Connection(Base):
    __tablename__ = "connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    connector: Mapped[str] = mapped_column(String(48))  # registry key, e.g. "ibkr_flex", "mock_ibkr"
    connection_status: Mapped[str] = mapped_column(String(24), default="pending")
    # pending | active | syncing | error | reauth_required | disconnected
    authentication_method: Mapped[str] = mapped_column(String(32))
    last_successful_sync: Mapped[datetime | None] = mapped_column(TS)
    last_error: Mapped[str | None] = mapped_column(Text)
    sync_checkpoint: Mapped[dict] = mapped_column(Json, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    institution: Mapped[Institution] = relationship()


class EncryptedCredential(Base):
    __tablename__ = "encrypted_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), unique=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    rotated_at: Mapped[datetime | None] = mapped_column(TS)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("connections.id", ondelete="SET NULL"), index=True)
    external_account_reference: Mapped[str | None] = mapped_column(String(128))
    account_name: Mapped[str] = mapped_column(String(120))
    nickname: Mapped[str | None] = mapped_column(String(120))
    account_type: Mapped[str] = mapped_column(String(24))
    # checking | savings | brokerage | investment | cash | credit_card | loan | fixed_deposit | other
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | disconnected | archived
    counts_toward_net_worth: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    connection: Mapped[Connection | None] = relationship()
    __table_args__ = (UniqueConstraint("connection_id", "external_account_reference", name="uq_account_ext_ref"),)


class AccountBalanceSnapshot(Base):
    __tablename__ = "account_balance_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    balance: Mapped[Decimal] = mapped_column(Money)
    available_balance: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    valuation_timestamp: Mapped[datetime] = mapped_column(TS)
    source: Mapped[str] = mapped_column(String(24))
    __table_args__ = (Index("ix_balance_account_time", "account_id", "valuation_timestamp"),)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(80))
    parent_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    category_type: Mapped[str] = mapped_column(String(16))  # expense | income | transfer | investment
    icon: Mapped[str | None] = mapped_column(String(32))
    color: Mapped[str | None] = mapped_column(String(16))
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_category_user_slug"),)


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    matching_rule: Mapped[str] = mapped_column(String(255))
    match_field: Mapped[str] = mapped_column(String(16), default="description")
    rule_kind: Mapped[str] = mapped_column(String(16), default="rule")  # rule | learned
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(32))
    file_name: Mapped[str | None] = mapped_column(String(255))
    import_status: Mapped[str] = mapped_column(String(16))  # previewed | committed | failed | reverted
    summary: Mapped[dict] = mapped_column(Json, default=dict)
    imported_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    external_transaction_id: Mapped[str | None] = mapped_column(String(128))
    transaction_date: Mapped[datetime] = mapped_column(TS)
    posting_date: Mapped[datetime | None] = mapped_column(TS)
    # raw (immutable once imported)
    raw_description: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(Json, default=dict)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    # normalized (system)
    merchant_name: Mapped[str | None] = mapped_column(String(160))
    transaction_type: Mapped[str] = mapped_column(String(24))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    category_source: Mapped[str | None] = mapped_column(String(16))
    transaction_status: Mapped[str] = mapped_column(String(16), default="posted")
    transfer_group: Mapped[str | None] = mapped_column(String(64))
    duplicate_status: Mapped[str] = mapped_column(String(24), default="unique")  # unique | possible_duplicate | confirmed_unique
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"))
    # user overrides (never overwrite raw)
    user_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    user_type: Mapped[str | None] = mapped_column(String(24))
    user_notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(Json, default=list)
    source: Mapped[str] = mapped_column(String(24))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    account: Mapped[Account] = relationship()
    __table_args__ = (
        Index("uq_txn_account_external", "account_id", "external_transaction_id", unique=True,
              postgresql_where="external_transaction_id IS NOT NULL"),
        Index("ix_txn_account_date", "account_id", "transaction_date"),
        Index("ix_txn_date", "transaction_date"),
    )


class Security(Base):
    __tablename__ = "securities"
    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    ticker: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    asset_class: Mapped[str] = mapped_column(String(24))  # stock | etf | mutual_fund | bond | other
    exchange: Mapped[str | None] = mapped_column(String(32))
    trading_currency: Mapped[str] = mapped_column(String(3))
    country: Mapped[str | None] = mapped_column(String(2))
    sector: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("ticker", "exchange", name="uq_security_ticker_exchange"),)


class HoldingSnapshot(Base):
    __tablename__ = "holdings_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    quantity: Mapped[Decimal] = mapped_column(Money)
    average_price: Mapped[Decimal] = mapped_column(Money)
    market_price: Mapped[Decimal] = mapped_column(Money)
    market_value: Mapped[Decimal] = mapped_column(Money)
    cost_basis: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    price_type: Mapped[str] = mapped_column(String(16))  # live | delayed | close | imported
    valuation_timestamp: Mapped[datetime] = mapped_column(TS)
    source: Mapped[str] = mapped_column(String(24))
    security: Mapped[Security] = relationship()
    __table_args__ = (Index("ix_holding_account_time", "account_id", "valuation_timestamp"),)


class InvestmentTransaction(Base):
    __tablename__ = "investment_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"))
    external_id: Mapped[str | None] = mapped_column(String(128))
    activity_type: Mapped[str] = mapped_column(String(24))  # buy | sell | dividend | fee | deposit | withdrawal | interest
    quantity: Mapped[Decimal | None] = mapped_column(Money)
    price: Mapped[Decimal | None] = mapped_column(Money)
    amount: Mapped[Decimal] = mapped_column(Money)
    fees: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    realized_pl: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    execution_timestamp: Mapped[datetime] = mapped_column(TS)
    source: Mapped[str] = mapped_column(String(24))
    __table_args__ = (UniqueConstraint("account_id", "external_id", name="uq_invtx_ext"),)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 12))
    provider: Mapped[str] = mapped_column(String(32))
    effective_timestamp: Mapped[datetime] = mapped_column(TS)
    __table_args__ = (
        UniqueConstraint("base_currency", "quote_currency", "provider", "effective_timestamp", name="uq_fx"),
        CheckConstraint("rate > 0", name="ck_fx_positive"),
    )


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    asset_name: Mapped[str] = mapped_column(String(120))
    asset_type: Mapped[str] = mapped_column(String(24))  # property | fixed_deposit | cash | vehicle | other
    currency: Mapped[str] = mapped_column(String(3))
    valuation_method: Mapped[str] = mapped_column(String(24), default="manual_estimate")
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class AssetValuation(Base):
    __tablename__ = "asset_valuations"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    valuation_amount: Mapped[Decimal] = mapped_column(Money)
    valuation_date: Mapped[date] = mapped_column(Date)
    valuation_source: Mapped[str] = mapped_column(String(64))


class Liability(Base):
    __tablename__ = "liabilities"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    liability_name: Mapped[str] = mapped_column(String(120))
    liability_type: Mapped[str] = mapped_column(String(24))  # personal_loan | education_loan | home_loan | credit_card | other
    currency: Mapped[str] = mapped_column(String(3))
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    payment_amount: Mapped[Decimal | None] = mapped_column(Money)
    payment_frequency: Mapped[str | None] = mapped_column(String(16))
    next_payment_date: Mapped[date | None] = mapped_column(Date)
    linked_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class LiabilitySnapshot(Base):
    __tablename__ = "liability_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    liability_id: Mapped[int] = mapped_column(ForeignKey("liabilities.id", ondelete="CASCADE"), index=True)
    outstanding_amount: Mapped[Decimal] = mapped_column(Money)
    snapshot_date: Mapped[date] = mapped_column(Date)


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    period: Mapped[str] = mapped_column(String(16), default="monthly")
    __table_args__ = (UniqueConstraint("user_id", "category_id", "period", name="uq_budget"),)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_name: Mapped[str] = mapped_column(String(120))
    goal_type: Mapped[str] = mapped_column(String(24), default="general")
    target_amount: Mapped[Decimal] = mapped_column(Money)
    target_currency: Mapped[str] = mapped_column(String(3))
    target_date: Mapped[date | None] = mapped_column(Date)
    monthly_contribution_plan: Mapped[Decimal | None] = mapped_column(Money)
    linked_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class GoalContribution(Base):
    __tablename__ = "goals_contributions"
    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    contribution_date: Mapped[date] = mapped_column(Date)


class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    snapshot_date: Mapped[date] = mapped_column(Date)
    total_assets: Mapped[Decimal] = mapped_column(Money)
    total_liabilities: Mapped[Decimal] = mapped_column(Money)
    net_worth: Mapped[Decimal] = mapped_column(Money)
    reporting_currency: Mapped[str] = mapped_column(String(3))
    __table_args__ = (UniqueConstraint("user_id", "snapshot_date", "reporting_currency", name="uq_fin_snapshot"),)


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))  # queued | running | succeeded | partial | failed
    trigger: Mapped[str] = mapped_column(String(16), default="manual")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TS)
    stats: Mapped[dict] = mapped_column(Json, default=dict)
    error_details: Mapped[str | None] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(48))
    timestamp: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column("metadata", Json, default=dict)
