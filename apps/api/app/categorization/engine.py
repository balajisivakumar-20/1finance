"""Hybrid, deterministic-first categorization.

Order of precedence:
  1. User-defined rules (highest priority first)         → source "rule"
  2. Learned merchant corrections (from user edits)      → source "learned"
  3. Built-in merchant / keyword dictionary              → source "dictionary"
  4. Optional AI fallback (only with explicit consent)   → source "ai"  (not called unless enabled)
  5. Otherwise "uncategorized"

No external service is needed for 1–3. Descriptions are never sent anywhere unless `ai_consent` is True.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.finance.reconcile import normalize_description

# keyword → (category slug, transaction type hint)
DICTIONARY: list[tuple[str, str]] = [
    (r"\b(tesco|lidl|aldi|dunnes|supervalu|spar|carrefour|bigbasket|blinkit|zepto|sainsbury)\b", "groceries"),
    (r"\b(deliveroo|just eat|uber eats|swiggy|zomato)\b", "food_delivery"),
    (r"\b(starbucks|costa|insomnia|butlers|cafe|coffee)\b", "coffee"),
    (r"\b(restaurant|bistro|pizza|sushi|burger|nando|mcdonald|kfc|domino)", "restaurants"),
    (r"\b(leap card|luas|dart|irish rail|bus eireann|dublin bus|tfl|metro|irctc)\b", "public_transport"),
    (r"\b(uber|bolt|freenow|lyft|ola)\b", "taxi"),
    (r"\b(circle k|applegreen|shell|maxol|texaco|fuel|petrol)\b", "fuel"),
    (r"\b(parking|apcoa|q park)\b", "parking"),
    (r"\b(netflix|spotify|disney|prime video|youtube premium|apple tv|hotstar)\b", "streaming"),
    (r"\b(github|openai|anthropic|notion|figma|jetbrains|adobe|microsoft 365|icloud|google one|dropbox)\b", "software"),
    (r"\b(gym|flyefit|ben dunne|perpetua|cult fit)\b", "fitness"),
    (r"\b(pharmacy|boots|lloyds pharmacy|apollo pharmacy)\b", "pharmacy"),
    (r"\b(electric ireland|bord gais|sse airtricity|energia|electricity)\b", "electricity"),
    (r"\b(eir|virgin media|sky broadband|vodafone broadband|jio fiber)\b", "internet"),
    (r"\b(vodafone|three|48|gomo|airtel|jio)\b", "mobile"),
    (r"\b(irish water|uisce)\b", "water"),
    (r"\b(ryanair|aer lingus|indigo|air india|emirates|lufthansa)\b", "flights"),
    (r"\b(booking com|airbnb|hotel|marriott|hilton)\b", "hotels"),
    (r"\b(zara|h&m|penneys|primark|uniqlo|myntra)\b", "clothing"),
    (r"\b(amazon|ikea|argos|flipkart)\b", "household"),
    (r"\b(apple store|currys|harvey norman|croma)\b", "electronics"),
    (r"\b(cinema|odeon|cineworld|imc|pvr)\b", "movies"),
    (r"\b(ticketmaster|eventbrite)\b", "events"),
    (r"\b(rent|landlord|rtb)\b", "rent"),
    (r"\b(mortgage)\b", "mortgage"),
    (r"\b(salary|payroll|wages)\b", "salary"),
    (r"\b(interest earned|interest paid to you|savings interest)\b", "interest_income"),
    (r"\b(fee|charge|commission)\b", "bank_fees"),
]
_COMPILED = [(re.compile(p), c) for p, c in DICTIONARY]


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    pattern: str  # case-insensitive substring, or regex if wrapped in /…/
    category: str
    priority: int = 100
    field: str = "description"  # description | merchant

    def matches(self, description: str, merchant: str | None) -> bool:
        target = (merchant or "") if self.field == "merchant" else description
        target = target.lower()
        if len(self.pattern) > 2 and self.pattern.startswith("/") and self.pattern.endswith("/"):
            try:
                return re.search(self.pattern[1:-1], target, re.I) is not None
            except re.error:
                return False
        return self.pattern.lower() in target


@dataclass(frozen=True, slots=True)
class Categorization:
    category: str
    source: str  # rule | learned | dictionary | ai | none
    rule_id: str | None = None
    confidence: float = 1.0


def merchant_key(description: str, merchant: str | None = None) -> str:
    """Stable key used to learn corrections: normalized merchant name, else first 3 words of description."""
    base = normalize_description(merchant or description)
    return " ".join(base.split()[:3])


class Categorizer:
    def __init__(
        self,
        rules: list[Rule] | None = None,
        learned: dict[str, str] | None = None,
        ai: Callable[[str], str | None] | None = None,
        ai_consent: bool = False,
    ) -> None:
        self.rules = sorted(rules or [], key=lambda r: -r.priority)
        self.learned = learned or {}
        self.ai = ai
        self.ai_consent = ai_consent

    def categorize(self, description: str, merchant: str | None = None) -> Categorization:
        for r in self.rules:
            if r.matches(description, merchant):
                return Categorization(r.category, "rule", r.id)
        key = merchant_key(description, merchant)
        if key in self.learned:
            return Categorization(self.learned[key], "learned", confidence=0.95)
        text = normalize_description(f"{merchant or ''} {description}")
        for rx, cat in _COMPILED:
            if rx.search(text):
                return Categorization(cat, "dictionary", confidence=0.8)
        if self.ai and self.ai_consent:
            cat = self.ai(description)
            if cat:
                return Categorization(cat, "ai", confidence=0.6)
        return Categorization("uncategorized", "none", confidence=0.0)

    def learn(self, description: str, merchant: str | None, category: str) -> str:
        key = merchant_key(description, merchant)
        self.learned[key] = category
        return key
