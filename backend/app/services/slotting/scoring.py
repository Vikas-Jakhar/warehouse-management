"""Combines demand, physical, operational, and rotation factors (section 13)
into one score per candidate location, plus a plain-language explanation of
why it scored the way it did. Weights are named constants so the tradeoffs
are visible and tunable, not buried in a formula.
"""

import math
from dataclasses import dataclass, field

# Demand carries the most weight (a fast mover badly placed costs the most
# picking effort over time); distance next (the direct travel-time driver);
# capacity fit and accessibility are smaller refinements; rotation is a flat
# compliance acknowledgment since FIFO/FEFO/LIFO correctness is already
# enforced as a hard constraint upstream, not a location trait to optimize.
WEIGHT_DEMAND = 0.35
WEIGHT_DISTANCE = 0.30
WEIGHT_CAPACITY_FIT = 0.15
WEIGHT_ACCESSIBILITY = 0.10
WEIGHT_ROTATION = 0.10


@dataclass
class ScoreBreakdown:
    demand_score: float
    distance_score: float
    capacity_fit_score: float
    accessibility_score: float
    rotation_score: float
    total_score: float
    reasons: list[str] = field(default_factory=list)


def euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def normalize(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.5
    return max(0.0, min(1.0, value / max_value))


def score_candidate(
    *,
    demand_velocity: float,
    max_demand_velocity: float,
    total_distance: float,
    max_distance: float,
    needed_volume: float | None,
    available_volume: float | None,
    accessibility_level: int,
    picking_priority: int,
) -> ScoreBreakdown:
    reasons: list[str] = []

    demand_score = normalize(demand_velocity, max_demand_velocity)
    if demand_score >= 0.7:
        reasons.append("High demand velocity for this SKU in this warehouse")

    distance_score = 1.0 - normalize(total_distance, max_distance) if max_distance > 0 else 0.5
    if distance_score >= 0.7:
        reasons.append("Short combined travel distance to receiving and dispatch")

    if needed_volume is not None and available_volume is not None and available_volume > 0:
        fit_ratio = needed_volume / available_volume
        capacity_fit_score = max(0.0, 1.0 - abs(1.0 - fit_ratio))
        if capacity_fit_score >= 0.7:
            reasons.append("Good capacity fit - not oversized or undersized for the quantity")
    else:
        capacity_fit_score = 0.5

    accessibility_score = accessibility_level / 5.0
    # High-priority SKUs (low picking_priority number = more urgent) benefit
    # more from an accessible slot, so weight the reason threshold by that.
    if accessibility_score >= 0.8 and picking_priority <= 2:
        reasons.append("Highly accessible location, matching this SKU's picking priority")

    rotation_score = 1.0  # rotation-policy compatibility is a hard constraint upstream, not scored here
    reasons.append("Meets the SKU's storage, temperature, hazard, and fragility requirements")

    total = (
        WEIGHT_DEMAND * demand_score
        + WEIGHT_DISTANCE * distance_score
        + WEIGHT_CAPACITY_FIT * capacity_fit_score
        + WEIGHT_ACCESSIBILITY * accessibility_score
        + WEIGHT_ROTATION * rotation_score
    )

    return ScoreBreakdown(
        demand_score=demand_score,
        distance_score=distance_score,
        capacity_fit_score=capacity_fit_score,
        accessibility_score=accessibility_score,
        rotation_score=rotation_score,
        total_score=total,
        reasons=reasons,
    )
