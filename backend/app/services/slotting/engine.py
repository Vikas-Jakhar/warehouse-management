"""Pure orchestration layer: given inventory, SKU, and location data (already
loaded from the DB by the caller), produces recommendation candidates. No DB
access here - this is unit-testable in isolation, mirroring the forecasting
pipeline's pure/persist split.
"""

import uuid
from dataclasses import dataclass, field

from app.services.slotting.constraints import LocationLike, SkuLike, check_eligibility
from app.services.slotting.scoring import ScoreBreakdown, euclidean_distance, score_candidate

# Stability rules (section 14): don't recommend a relocation for marginal
# gain, and don't re-surface a recommendation the manager already rejected
# without a material change or explicit re-review request.
DEFAULT_MIN_CONFIDENCE = 0.4
DEFAULT_MIN_EXPECTED_BENEFIT = 0.05


@dataclass
class InventoryRecordInput:
    id: uuid.UUID
    sku_id: uuid.UUID
    current_location_id: uuid.UUID | None
    quantity: float
    status: str


@dataclass
class SkuInput:
    id: uuid.UUID
    sku_code: str
    weight: float | None
    volume: float | None
    category: str | None
    temperature_requirement: str | None
    fragility: str
    hazard_class: str
    picking_priority: int


@dataclass
class LocationInput:
    id: uuid.UUID
    location_code: str
    x: float
    y: float
    max_weight: float | None
    max_volume: float | None
    used_capacity: float
    allowed_categories: list
    temperature_restriction: str | None
    hazard_restriction: str | None
    fragility_restriction: str | None
    is_active: bool
    is_blocked: bool
    is_available: bool
    location_type: str
    accessibility_level: int


@dataclass
class RecommendationCandidate:
    inventory_record_id: uuid.UUID
    sku_id: uuid.UUID
    current_location_id: uuid.UUID | None
    recommended_location_id: uuid.UUID
    expected_benefit: float
    distance_reduction: float | None
    confidence_score: float
    demand_classification: str
    score_breakdown: ScoreBreakdown
    reasons: list[str] = field(default_factory=list)


def _classify_demand(demand_score: float) -> str:
    if demand_score >= 0.7:
        return "fast_mover"
    if demand_score <= 0.3:
        return "slow_mover"
    return "medium_mover"


def generate_recommendations(
    *,
    inventory_records: list[InventoryRecordInput],
    skus_by_id: dict[uuid.UUID, SkuInput],
    locations: list[LocationInput],
    demand_velocity_by_sku: dict[uuid.UUID, float],
    confidence_by_sku: dict[uuid.UUID, float],
    receiving_point: tuple[float, float] | None,
    dispatch_point: tuple[float, float] | None,
    suppressed_inventory_record_ids: set[uuid.UUID],
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_expected_benefit: float = DEFAULT_MIN_EXPECTED_BENEFIT,
) -> list[RecommendationCandidate]:
    max_demand_velocity = max(demand_velocity_by_sku.values(), default=0.0) or 1.0
    location_by_id = {loc.id: loc for loc in locations}

    def total_distance(loc: LocationInput) -> float:
        dist = 0.0
        if receiving_point is not None:
            dist += euclidean_distance(loc.x, loc.y, *receiving_point)
        if dispatch_point is not None:
            dist += euclidean_distance(loc.x, loc.y, *dispatch_point)
        return dist

    candidates: list[RecommendationCandidate] = []

    for record in inventory_records:
        if record.id in suppressed_inventory_record_ids:
            continue

        sku = skus_by_id.get(record.sku_id)
        if sku is None:
            continue

        needed_volume = sku.volume * record.quantity if sku.volume is not None else None
        demand_velocity = demand_velocity_by_sku.get(sku.id, 0.0)

        eligible: list[tuple[LocationInput, float]] = []
        for loc in locations:
            elig, _reason = check_eligibility(
                SkuLike(
                    weight=sku.weight,
                    volume=sku.volume,
                    category=sku.category,
                    temperature_requirement=sku.temperature_requirement,
                    fragility=sku.fragility,
                    hazard_class=sku.hazard_class,
                ),
                LocationLike(
                    max_weight=loc.max_weight,
                    max_volume=loc.max_volume,
                    used_capacity=loc.used_capacity,
                    allowed_categories=loc.allowed_categories,
                    temperature_restriction=loc.temperature_restriction,
                    hazard_restriction=loc.hazard_restriction,
                    fragility_restriction=loc.fragility_restriction,
                    is_active=loc.is_active,
                    is_blocked=loc.is_blocked,
                    is_available=loc.is_available,
                    location_type=loc.location_type,
                ),
                record.quantity,
            )
            if elig:
                eligible.append((loc, total_distance(loc)))

        if not eligible:
            continue

        max_distance = max(d for _, d in eligible) or 1.0

        best_loc: LocationInput | None = None
        best_breakdown: ScoreBreakdown | None = None
        best_dist = 0.0
        for loc, dist in eligible:
            breakdown = score_candidate(
                demand_velocity=demand_velocity,
                max_demand_velocity=max_demand_velocity,
                total_distance=dist,
                max_distance=max_distance,
                needed_volume=needed_volume,
                available_volume=loc.max_volume,
                accessibility_level=loc.accessibility_level,
                picking_priority=sku.picking_priority,
            )
            if best_breakdown is None or breakdown.total_score > best_breakdown.total_score:
                best_loc, best_breakdown, best_dist = loc, breakdown, dist

        assert best_loc is not None and best_breakdown is not None

        current_score = 0.0
        distance_reduction: float | None = None
        if record.current_location_id is not None:
            current_loc = location_by_id.get(record.current_location_id)
            if current_loc is not None:
                cur_dist = total_distance(current_loc)
                current_breakdown = score_candidate(
                    demand_velocity=demand_velocity,
                    max_demand_velocity=max_demand_velocity,
                    total_distance=cur_dist,
                    max_distance=max_distance,
                    needed_volume=needed_volume,
                    available_volume=current_loc.max_volume,
                    accessibility_level=current_loc.accessibility_level,
                    picking_priority=sku.picking_priority,
                )
                current_score = current_breakdown.total_score
                distance_reduction = cur_dist - best_dist

        # Already in the best available slot - nothing to recommend.
        if record.current_location_id == best_loc.id:
            continue

        expected_benefit = best_breakdown.total_score - current_score

        # Put-away (no current location) always gets a recommendation since
        # stock has to go somewhere; relocating already-placed stock requires
        # a meaningful improvement to justify the disruption.
        if record.current_location_id is not None and expected_benefit < min_expected_benefit:
            continue

        confidence = confidence_by_sku.get(sku.id, 0.5)
        if confidence < min_confidence:
            continue

        reasons = list(best_breakdown.reasons)
        if distance_reduction is not None and distance_reduction > 0:
            reasons.append(f"Reduces travel distance by {distance_reduction:.1f} units versus current location")
        if record.current_location_id is None:
            reasons.append("New stock awaiting put-away")

        candidates.append(
            RecommendationCandidate(
                inventory_record_id=record.id,
                sku_id=sku.id,
                current_location_id=record.current_location_id,
                recommended_location_id=best_loc.id,
                expected_benefit=expected_benefit,
                distance_reduction=distance_reduction,
                confidence_score=confidence,
                demand_classification=_classify_demand(best_breakdown.demand_score),
                score_breakdown=best_breakdown,
                reasons=reasons,
            )
        )

    return candidates
