"""Common, read-only connector interface.

There are intentionally NO methods for orders, payments or transfers. Adapters must only call read endpoints.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Capability(str, Enum):
    ACCOUNTS = "accounts"
    BALANCES = "balances"
    BALANCE_HISTORY = "balance_history"
    TRANSACTIONS = "transactions"
    HOLDINGS = "holdings"
    INVESTMENT_ACTIVITY = "investment_activity"
    HISTORICAL_BACKFILL = "historical_backfill"


class ConnectorError(Exception):
    """Generic provider failure (safe message, never contains secrets)."""


class ReauthRequired(ConnectorError):
    pass


class RateLimited(ConnectorError):
    def __init__(self, msg: str, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class NotSupported(ConnectorError):
    pass


@dataclass(frozen=True)
class AccountData:
    external_ref: str
    name: str
    account_type: str
    currency: str


@dataclass(frozen=True)
class BalanceData:
    external_account_ref: str
    balance: Decimal
    currency: str
    as_of: datetime
    available: Decimal | None = None


@dataclass(frozen=True)
class TransactionData:
    external_account_ref: str
    external_id: str | None
    occurred_at: datetime
    description: str
    amount: Decimal
    currency: str
    type_hint: str | None = None  # connector's best guess: income | expense | transfer | refund | …
    merchant: str | None = None
    status: str = "posted"
    posted_at: datetime | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SecurityData:
    ticker: str
    name: str
    asset_class: str
    currency: str
    isin: str | None = None
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None


@dataclass(frozen=True)
class HoldingData:
    external_account_ref: str
    security: SecurityData
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal
    currency: str
    as_of: datetime
    price_type: str = "close"  # live | delayed | close | imported


@dataclass(frozen=True)
class InvestmentActivityData:
    external_account_ref: str
    external_id: str | None
    activity_type: str  # buy | sell | dividend | fee | deposit | withdrawal | interest
    amount: Decimal
    currency: str
    executed_at: datetime
    security: SecurityData | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fees: Decimal = Decimal(0)
    realized_pl: Decimal | None = None


@dataclass(frozen=True)
class ConnectorInfo:
    key: str
    institution_slug: str
    display_name: str
    auth_method: str  # api_token | oauth | file_import | manual | mock
    capabilities: frozenset[Capability]
    is_mock: bool = False
    credential_fields: tuple[str, ...] = ()
    notes: str = ""


class FinancialConnector(abc.ABC):
    info: ConnectorInfo

    def __init__(self, credentials: dict | None = None) -> None:
        self.credentials = credentials or {}

    def supports(self, cap: Capability) -> bool:
        return cap in self.info.capabilities

    # lifecycle
    @abc.abstractmethod
    def validate_connection(self) -> None:
        """Raise ReauthRequired/ConnectorError if the credentials do not work. Must perform a real call."""

    def connect(self) -> None:
        self.validate_connection()

    def disconnect(self) -> None:  # most providers: nothing to revoke server-side
        return None

    # data (default: not supported → empty)
    def list_accounts(self) -> list[AccountData]:
        raise NotSupported("accounts")

    def fetch_balances(self, since: datetime | None = None) -> list[BalanceData]:
        raise NotSupported("balances")

    def fetch_transactions(self, since: datetime | None = None) -> list[TransactionData]:
        raise NotSupported("transactions")

    def fetch_holdings(self) -> list[HoldingData]:
        raise NotSupported("holdings")

    def fetch_holdings_history(self, since: datetime | None = None) -> list[HoldingData]:
        return []

    def fetch_investment_activity(self, since: datetime | None = None) -> list[InvestmentActivityData]:
        raise NotSupported("investment_activity")
