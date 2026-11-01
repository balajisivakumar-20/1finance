"""Connector registry with capability discovery. Adding an institution = adding an adapter here."""
from __future__ import annotations

from app.core.config import get_settings

from .base import Capability, ConnectorInfo, FinancialConnector
from .groww import GrowwConnector
from .ibkr_flex import IBKRFlexConnector
from .mock import MockGroww, MockIBKR, MockRevolut


class AggregatorConnector(FinancialConnector):
    """Placeholder for a licensed open-banking aggregator (GoCardless BAD, TrueLayer, Tink…).

    Reports `not_configured` — it never pretends to connect.
    """

    info = ConnectorInfo(
        key="aggregator_revolut",
        institution_slug="revolut",
        display_name="Revolut — Open Banking (via licensed aggregator)",
        auth_method="oauth",
        capabilities=frozenset({Capability.ACCOUNTS, Capability.BALANCES, Capability.TRANSACTIONS}),
        notes="Requires a regulated AISP / aggregator account. Not configured in this installation.",
    )

    def validate_connection(self):
        from .base import ConnectorError

        raise ConnectorError("Open banking aggregator is not configured. Use statement import instead.")


class ImportConnector(FinancialConnector):
    info = ConnectorInfo("csv_import", "statement-import", "Statement import (CSV)", "file_import",
                         frozenset({Capability.TRANSACTIONS, Capability.HISTORICAL_BACKFILL}))

    def validate_connection(self):
        return None


class ManualConnector(FinancialConnector):
    info = ConnectorInfo("manual", "manual", "Manual account", "manual", frozenset({Capability.BALANCES}))

    def validate_connection(self):
        return None


PRODUCTION = [IBKRFlexConnector, GrowwConnector, AggregatorConnector, ImportConnector, ManualConnector]
MOCKS = [MockIBKR, MockGroww, MockRevolut]


def available() -> dict[str, type[FinancialConnector]]:
    classes = list(PRODUCTION)
    if get_settings().allow_mock_connectors:
        classes += MOCKS
    return {c.info.key: c for c in classes}


def get(key: str) -> type[FinancialConnector]:
    reg = available()
    if key not in reg:
        raise KeyError(f"Unknown or disabled connector: {key}")
    return reg[key]


def describe() -> list[dict]:
    return [
        {
            "key": c.info.key,
            "institution": c.info.institution_slug,
            "display_name": c.info.display_name,
            "auth_method": c.info.auth_method,
            "capabilities": sorted(x.value for x in c.info.capabilities),
            "is_mock": c.info.is_mock,
            "credential_fields": list(c.info.credential_fields),
            "notes": c.info.notes,
        }
        for c in available().values()
    ]
