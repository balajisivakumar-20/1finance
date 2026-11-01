"""Statement import pipeline: parse → validate → preview → (user confirms) → commit.

Nothing is written to the database by the parsers. Rows that fail validation are returned as errors and are
never imported silently.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.connectors.base import TransactionData

REVOLUT_TYPES = {
    "CARD_PAYMENT": "expense", "CARD_REFUND": "refund", "REFUND": "refund", "TOPUP": "transfer",
    "TRANSFER": "transfer", "EXCHANGE": "transfer", "FEE": "fee", "ATM": "expense", "CASHBACK": "refund",
    "INTEREST": "interest", "REWARD": "income", "TAX": "fee",
}
STATE = {"COMPLETED": "posted", "PENDING": "pending", "REVERTED": "reversed", "DECLINED": None, "FAILED": None}


@dataclass
class ParseResult:
    format: str
    rows: list[TransactionData] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    skipped: int = 0
    currencies: set[str] = field(default_factory=set)


def _parse_dt(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date '{s}'")


def _dec(s: str) -> Decimal:
    s = (s or "").strip().replace(",", "")
    if not s:
        raise ValueError("Empty amount")
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f"Invalid amount '{s}'") from e


def _row_id(*parts: str) -> str:
    return "csv:" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def detect_format(header: list[str]) -> str:
    h = {c.strip().lower() for c in header}
    if {"type", "started date", "description", "amount", "currency", "state"} <= h:
        return "revolut"
    if {"date", "description", "amount", "currency"} <= h:
        return "generic"
    return "unknown"


def parse_csv(content: bytes, account_ref: str) -> ParseResult:
    text = content.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(text))
    fmt = detect_format(reader.fieldnames or [])
    res = ParseResult(fmt)
    if fmt == "unknown":
        res.errors.append({"row": 0, "error": "Unsupported CSV layout. Expected Revolut export or columns: date, description, amount, currency[, type]"})
        return res
    for i, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        try:
            if fmt == "revolut":
                state = STATE.get(row.get("state", "").upper(), "posted")
                if state is None:
                    res.skipped += 1
                    continue
                amount = _dec(row["amount"]) - _dec(row.get("fee") or "0")
                started = _parse_dt(row["started date"])
                completed = _parse_dt(row["completed date"]) if row.get("completed date") else None
                typ = REVOLUT_TYPES.get(row["type"].upper(), "expense" if amount < 0 else "income")
                ext = _row_id(row["started date"], row["description"], row["amount"], row["currency"], row.get("balance", ""))
                t = TransactionData(account_ref, ext, started, row["description"], amount, row["currency"].upper(), typ,
                                    None, state, completed, {"format": "revolut_csv", "row": raw})
            else:
                amount = _dec(row["amount"])
                ext = row.get("id") or _row_id(row["date"], row["description"], row["amount"], row["currency"], str(i))
                typ = row.get("type") or ("expense" if amount < 0 else "income")
                t = TransactionData(account_ref, ext, _parse_dt(row["date"]), row["description"], amount,
                                    row["currency"].upper(), typ, row.get("merchant") or None, "posted", None,
                                    {"format": "generic_csv", "row": raw})
            if len(t.currency) != 3:
                raise ValueError(f"Invalid currency '{t.currency}'")
            res.rows.append(t)
            res.currencies.add(t.currency)
        except (KeyError, ValueError) as e:
            res.errors.append({"row": i, "error": str(e)})
    return res
