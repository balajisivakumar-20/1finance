"""Transaction de-duplication and internal-transfer detection.

Dedup policy:
  1. Same account + same provider transaction id  → certain duplicate (skip).
  2. No id: same account, same amount & currency, dates within ±2 days, similar normalized description
     → *possible* duplicate: flagged for review, never auto-deleted.

Transfer detection: an outflow from account A and an inflow into account B (both owned by the user) with equal
absolute value (after FX if currencies differ, within tolerance) within a date window → transfer pair candidate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher

_NOISE = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")
_REFS = re.compile(r"\b(\w*\d{4,}\w*|ref\w*|txn\w*|card \d+)\b")


def normalize_description(s: str) -> str:
    s = _NOISE.sub(" ", s.lower())
    s = _REFS.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


@dataclass(frozen=True, slots=True)
class Candidate:
    account_id: str
    external_id: str | None
    occurred_at: datetime
    amount: Decimal
    currency: str
    description: str


@dataclass(frozen=True, slots=True)
class DedupDecision:
    status: str  # new | duplicate | possible_duplicate
    matched_index: int | None = None
    score: float = 0.0


def classify_duplicate(new: Candidate, existing: list[Candidate], window_days: int = 2) -> DedupDecision:
    if new.external_id:
        for i, e in enumerate(existing):
            if e.account_id == new.account_id and e.external_id == new.external_id:
                return DedupDecision("duplicate", i, 1.0)
    nd = normalize_description(new.description)
    best: DedupDecision = DedupDecision("new")
    for i, e in enumerate(existing):
        if e.account_id != new.account_id or e.currency != new.currency or e.amount != new.amount:
            continue
        if abs(e.occurred_at - new.occurred_at) > timedelta(days=window_days):
            continue
        if new.external_id and e.external_id and e.external_id != new.external_id:
            continue  # both have ids and they differ → genuinely different transactions
        score = SequenceMatcher(None, nd, normalize_description(e.description)).ratio()
        if score >= 0.8 and score > best.score:
            best = DedupDecision("possible_duplicate", i, round(score, 3))
    return best


@dataclass(frozen=True, slots=True)
class TransferLeg:
    id: str
    account_id: str
    occurred_at: datetime
    amount_base: Decimal  # converted to a common currency for matching
    type: str


def find_transfer_pairs(
    legs: list[TransferLeg], window_days: int = 3, tolerance_pct: Decimal = Decimal("1.5")
) -> list[tuple[str, str]]:
    """Greedy one-to-one matching of outflows to inflows across *different* user accounts.

    Tolerance allows for FX spread when the legs are in different currencies. Already-classified
    expenses/income are still eligible; the UI asks the user to confirm before reclassifying.
    """
    outs = sorted((l for l in legs if l.amount_base < 0), key=lambda l: l.occurred_at)
    ins = [l for l in legs if l.amount_base > 0]
    used: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for o in outs:
        target = -o.amount_base
        best, best_gap = None, None
        for i in ins:
            if i.id in used or i.account_id == o.account_id:
                continue
            if not (timedelta(0) <= i.occurred_at - o.occurred_at <= timedelta(days=window_days)):
                continue
            diff_pct = abs(i.amount_base - target) / target * 100
            if diff_pct > tolerance_pct:
                continue
            gap = (diff_pct, i.occurred_at - o.occurred_at)
            if best_gap is None or gap < best_gap:
                best, best_gap = i, gap
        if best:
            used.add(best.id)
            pairs.append((o.id, best.id))
    return pairs
