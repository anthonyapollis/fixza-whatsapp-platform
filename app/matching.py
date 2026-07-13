"""Artisan matching engine: distance + rating + verification tier + experience."""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Artisan

MAX_RADIUS_KM = 30.0
TIER_SCORE = {"bronze": 0.4, "silver": 0.7, "gold": 1.0}

# Weights must sum to 1.0. Reliability was added after reviewing Angi/Thumbtack's
# biggest complaint pattern — pros who repeatedly decline or no-show still ranked
# highly because those platforms only scored rating/tier, not follow-through.
# See COMPETITIVE_ANALYSIS.md.
W_DISTANCE = 0.35
W_RATING = 0.25
W_TIER = 0.15
W_EXPERIENCE = 0.10
W_RELIABILITY = 0.15

# Typical Cape Town call-out ranges in ZAR, shown to the customer before they
# choose an artisan. Borrowed from Urban Company's fixed-pricing model to avoid
# the TaskRabbit/Airtasker bidding-war and price-surprise pattern.
PRICE_RANGES: dict[str, tuple[int, int]] = {
    "plumbing": (350, 650),
    "electrical": (400, 750),
    "carpentry": (300, 600),
    "painting": (250, 900),
    "appliance_repair": (350, 700),
    "building": (500, 1500),
    "roofing": (450, 1200),
    "locksmith": (300, 550),
    "garden": (250, 500),
    "tiling": (400, 900),
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class Match:
    artisan: Artisan
    distance_km: float
    score: float


def reliability_score(artisan: Artisan) -> float:
    """1.0 for a clean record; each decline/no-show pulls it down.

    No-shows hurt more than declines — declining upfront costs the customer
    nothing, a no-show costs them a wasted wait. Floor of 0.15 rather than 0
    so a struggling artisan can still recover by completing jobs, instead of
    being invisibly banned by the algorithm (the Urban Company complaint was
    exactly this opacity, not the existence of a penalty).
    """
    penalty = 0.08 * (artisan.declines or 0) + 0.20 * (artisan.no_shows or 0)
    return max(0.15, 1.0 - penalty)


def score_artisan(artisan: Artisan, distance_km: float) -> float:
    proximity = max(0.0, 1.0 - distance_km / MAX_RADIUS_KM)
    rating = (artisan.rating or 0.0) / 5.0
    tier = TIER_SCORE.get(artisan.verification_tier, 0.4)
    # 20 completed jobs ~= full experience credit
    experience = min((artisan.jobs_completed or 0) / 20.0, 1.0)
    reliability = reliability_score(artisan)
    return round(
        W_DISTANCE * proximity + W_RATING * rating + W_TIER * tier
        + W_EXPERIENCE * experience + W_RELIABILITY * reliability,
        4,
    )


def find_matches(
    db: Session, trade: str, lat: float, lng: float, limit: int = 3
) -> list[Match]:
    artisans = db.scalars(
        select(Artisan).where(Artisan.trade == trade, Artisan.active == 1)
    ).all()
    matches: list[Match] = []
    for artisan in artisans:
        dist = haversine_km(lat, lng, artisan.lat, artisan.lng)
        if dist > MAX_RADIUS_KM:
            continue
        matches.append(Match(artisan, round(dist, 1), score_artisan(artisan, dist)))
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:limit]
