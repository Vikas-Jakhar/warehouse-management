"""Hard constraints a candidate storage location must satisfy for a given
SKU before it's even scored. Violating any of these excludes the candidate
outright - per section 13, "Avoid producing recommendations that violate
physical or operational constraints."
"""

from dataclasses import dataclass

# Ordinal fragility scale: a location's fragility_restriction is the *maximum*
# fragility level it's rated to safely hold. None means unrestricted (treated
# as able to hold anything, since no restriction was configured).
FRAGILITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


@dataclass
class SkuLike:
    weight: float | None
    volume: float | None
    category: str | None
    temperature_requirement: str | None
    fragility: str
    hazard_class: str


@dataclass
class LocationLike:
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


def check_eligibility(sku: SkuLike, location: LocationLike, quantity: float) -> tuple[bool, str | None]:
    """Returns (is_eligible, exclusion_reason). exclusion_reason is None when eligible."""

    if not location.is_active:
        return False, "Location is inactive"
    if location.is_blocked:
        return False, "Location is blocked"
    if not location.is_available:
        return False, "Location is not available for storage"
    if location.location_type != "storage":
        return False, f"Location type '{location.location_type}' is not a general storage slot"

    if sku.temperature_requirement and sku.temperature_requirement != "ambient":
        if location.temperature_restriction != sku.temperature_requirement:
            return False, f"Requires '{sku.temperature_requirement}' storage, location doesn't provide it"

    if sku.hazard_class and sku.hazard_class != "none":
        if location.hazard_restriction != sku.hazard_class:
            return False, f"Requires '{sku.hazard_class}' hazard rating, location isn't rated for it"

    sku_fragility_rank = FRAGILITY_RANK.get(sku.fragility, 0)
    if location.fragility_restriction is not None:
        location_rank = FRAGILITY_RANK.get(location.fragility_restriction, 3)
        if sku_fragility_rank > location_rank:
            return False, f"Too fragile ('{sku.fragility}') for this location's rating ('{location.fragility_restriction}')"

    if location.allowed_categories and sku.category:
        allowed_lower = {str(c).lower() for c in location.allowed_categories}
        if sku.category.lower() not in allowed_lower:
            return False, f"Category '{sku.category}' not in location's allowed categories"

    if location.max_weight is not None and sku.weight is not None:
        needed = sku.weight * quantity
        if location.used_capacity + needed > location.max_weight:
            return False, "Would exceed location's weight capacity"

    if location.max_volume is not None and sku.volume is not None:
        needed = sku.volume * quantity
        if needed > location.max_volume:
            return False, "Would exceed location's volume capacity"

    return True, None
