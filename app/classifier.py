"""Job classification: trade + urgency from a free-text customer message.

Two layers:
1. Keyword rules — free, instant, works offline. Always available.
2. Claude (optional) — if ANTHROPIC_API_KEY is set, low-confidence messages are
   escalated to the LLM for better classification.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import config

TRADES = [
    "plumbing", "electrical", "carpentry", "painting", "appliance_repair",
    "building", "roofing", "locksmith", "garden", "tiling",
]

TRADE_KEYWORDS: dict[str, list[str]] = {
    "plumbing": ["geyser", "leak", "pipe", "tap", "toilet", "drain", "burst",
                 "water", "plumber", "sink", "sewer", "blocked"],
    "electrical": ["electric", "plug", "light", "wiring", "db board", "trip",
                   "power", "socket", "switch", "electrician", "prepaid meter"],
    "carpentry": ["cupboard", "door", "wood", "shelf", "cabinet", "carpenter",
                  "hinge", "skirting", "deck"],
    "painting": ["paint", "wall", "ceiling", "damp proof", "varnish", "painter"],
    "appliance_repair": ["fridge", "washing machine", "dishwasher", "oven",
                         "stove", "microwave", "tumble dryer", "appliance"],
    "building": ["wall crack", "brick", "plaster", "renovation", "extension",
                 "foundation", "builder", "concrete", "paving"],
    "roofing": ["roof", "gutter", "tile roof", "waterproof", "flashing"],
    "locksmith": ["lock", "key", "locked out", "burglar bar", "security gate"],
    "garden": ["garden", "tree", "lawn", "irrigation", "hedge", "landscap"],
    "tiling": ["tile", "grout", "bathroom floor", "splashback", "tiler"],
}

URGENT_KEYWORDS = [
    "emergency", "urgent", "asap", "now", "burst", "flooding", "sparks",
    "no power", "no water", "locked out", "dangerous", "immediately", "today",
]


@dataclass
class JobClassification:
    trade: str | None       # one of TRADES, or None if unrecognised
    urgency: str            # "normal" | "urgent"
    confidence: float       # 0..1
    source: str             # "rules" | "claude"


def _classify_rules(text: str) -> JobClassification:
    lowered = text.lower()
    scores: dict[str, int] = {}
    for trade, keywords in TRADE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits:
            scores[trade] = hits
    urgency = "urgent" if any(kw in lowered for kw in URGENT_KEYWORDS) else "normal"
    if not scores:
        return JobClassification(None, urgency, 0.0, "rules")
    best = max(scores, key=scores.get)
    # Rough confidence: 1 hit -> 0.6, 2 -> 0.8, 3+ -> 0.95
    confidence = {1: 0.6, 2: 0.8}.get(scores[best], 0.95)
    return JobClassification(best, urgency, confidence, "rules")


def _classify_claude(text: str) -> JobClassification | None:
    """Ask Claude to classify. Returns None on any failure (caller falls back)."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        prompt = (
            "Classify this South African home-repair request.\n"
            f"Trades: {', '.join(TRADES)}\n"
            f'Message: "{text}"\n\n'
            'Reply with ONLY JSON: {"trade": "<trade or null>", '
            '"urgency": "normal|urgent", "confidence": 0.0-1.0}'
        )
        resp = client.messages.create(
            model=config.CLASSIFIER_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group())
        trade = data.get("trade")
        if trade not in TRADES:
            trade = None
        urgency = data.get("urgency", "normal")
        if urgency not in ("normal", "urgent"):
            urgency = "normal"
        return JobClassification(trade, urgency, float(data.get("confidence", 0.5)), "claude")
    except Exception:
        return None


def classify(text: str) -> JobClassification:
    result = _classify_rules(text)
    if result.confidence < 0.6 and config.ANTHROPIC_API_KEY:
        llm = _classify_claude(text)
        if llm and llm.trade:
            return llm
    return result
