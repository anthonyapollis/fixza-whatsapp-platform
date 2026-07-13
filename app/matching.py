"""Artisan matching engine: distance + rating + verification tier + experience."""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Artisan

MAX_RADIUS_KM = 30.0
TIER_SCORE = {"bronze": 0.4, "silver": 0.7, "gold": 1.0}

# Weights must sum to 1.0
W_DISTANCE = 0.40
W_RATING = 0.30
W_TIER = 0.20
W_EXPERIENCE = 0.10


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


def score_artisan(artisan: Artisan, distance_km: float) -> float:
    proximity = max(0.0, 1.0 - distance_km / MAX_RADIUS_KM)
    rating = (artisan.rating or 0.0) / 5.0
    tier = TIER_SCORE.get(artisan.verification_tier, 0.4)
    # 20 completed jobs ~= full experience credit
    experience = min((artisan.jobs_completed or 0) / 20.0, 1.0)
    return round(
        W_DISTANCE * proximity + W_RATING * rating + W_TIER * tier + W_EXPERIENCE * experience,
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
