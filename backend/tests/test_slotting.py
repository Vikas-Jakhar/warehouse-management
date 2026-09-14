import io
import uuid
from datetime import date, timedelta

from tests.conftest import register_and_login

from app.services.slotting.constraints import LocationLike, SkuLike, check_eligibility
from app.services.slotting.engine import (
    InventoryRecordInput,
    LocationInput,
    SkuInput,
    generate_recommendations,
)
from app.services.slotting.scoring import normalize, score_candidate


def _create_warehouse(client, headers, code="RWH1"):
    return client.post("/api/v1/warehouses", headers=headers, json={"name": "Rec WH", "code": code}).json()


def _create_sku(client, headers, sku_code="RSKU-1", **overrides):
    body = {"sku_code": sku_code, "name": "Widget", **overrides}
    return client.post("/api/v1/skus", headers=headers, json=body).json()


def _create_location(client, headers, warehouse_id, **overrides):
    body = {
        "location_code": overrides.pop("location_code", "LOC-1"),
        "location_type": overrides.pop("location_type", "storage"),
        "storage_type": overrides.pop("storage_type", "bin"),
        "x": overrides.pop("x", 10),
        "y": overrides.pop("y", 10),
        "width": overrides.pop("width", 2),
        "height": overrides.pop("height", 2),
        **overrides,
    }
    resp = client.post(f"/api/v1/warehouses/{warehouse_id}/locations", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_inventory_csv(client, headers, warehouse_id, rows):
    lines = ["sku_id,location_id,quantity,receiving_date"] + [
        f"{sku},{loc or ''},{qty},2026-01-01" for sku, loc, qty in rows
    ]
    csv_content = "\n".join(lines) + "\n"
    files = {"file": ("inv.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    return client.post(f"/api/v1/warehouses/{warehouse_id}/inventory/upload", headers=headers, files=files)


# ---------------------------------------------------------------------------
# Constraint checks (pure unit tests)
# ---------------------------------------------------------------------------


def _sku(**overrides):
    defaults = dict(weight=1.0, volume=1.0, category=None, temperature_requirement=None, fragility="none", hazard_class="none")
    defaults.update(overrides)
    return SkuLike(**defaults)


def _location(**overrides):
    defaults = dict(
        max_weight=100.0,
        max_volume=100.0,
        used_capacity=0.0,
        allowed_categories=[],
        temperature_restriction=None,
        hazard_restriction=None,
        fragility_restriction=None,
        is_active=True,
        is_blocked=False,
        is_available=True,
        location_type="storage",
    )
    defaults.update(overrides)
    return LocationLike(**defaults)


def test_blocked_location_is_ineligible():
    ok, reason = check_eligibility(_sku(), _location(is_blocked=True), quantity=1)
    assert ok is False
    assert "blocked" in reason.lower()


def test_temperature_mismatch_is_ineligible():
    ok, reason = check_eligibility(_sku(temperature_requirement="frozen"), _location(temperature_restriction=None), quantity=1)
    assert ok is False
    assert "frozen" in reason.lower()


def test_temperature_match_is_eligible():
    ok, _ = check_eligibility(_sku(temperature_requirement="frozen"), _location(temperature_restriction="frozen"), quantity=1)
    assert ok is True


def test_hazard_mismatch_is_ineligible():
    ok, reason = check_eligibility(_sku(hazard_class="flammable"), _location(hazard_restriction=None), quantity=1)
    assert ok is False
    assert "flammable" in reason.lower()


def test_fragility_exceeds_location_rating_is_ineligible():
    ok, reason = check_eligibility(_sku(fragility="high"), _location(fragility_restriction="low"), quantity=1)
    assert ok is False
    assert "fragile" in reason.lower()


def test_fragility_within_rating_is_eligible():
    ok, _ = check_eligibility(_sku(fragility="low"), _location(fragility_restriction="medium"), quantity=1)
    assert ok is True


def test_category_restriction_excludes_mismatch():
    ok, reason = check_eligibility(_sku(category="Electronics"), _location(allowed_categories=["Grocery"]), quantity=1)
    assert ok is False
    assert "category" in reason.lower()


def test_weight_capacity_exceeded_is_ineligible():
    ok, reason = check_eligibility(_sku(weight=50.0), _location(max_weight=40.0), quantity=1)
    assert ok is False
    assert "weight" in reason.lower()


def test_volume_capacity_exceeded_is_ineligible():
    ok, reason = check_eligibility(_sku(volume=50.0), _location(max_volume=40.0), quantity=1)
    assert ok is False
    assert "volume" in reason.lower()


def test_fully_compatible_sku_and_location_is_eligible():
    ok, reason = check_eligibility(_sku(), _location(), quantity=1)
    assert ok is True
    assert reason is None


# ---------------------------------------------------------------------------
# Scoring (pure unit tests)
# ---------------------------------------------------------------------------


def test_normalize_clips_to_zero_one():
    assert normalize(5, 10) == 0.5
    assert normalize(-5, 10) == 0.0
    assert normalize(50, 10) == 1.0
    assert normalize(5, 0) == 0.5  # no denominator -> neutral


def test_score_candidate_rewards_high_demand_and_short_distance():
    high = score_candidate(
        demand_velocity=90, max_demand_velocity=100, total_distance=1, max_distance=100,
        needed_volume=5, available_volume=10, accessibility_level=5, picking_priority=1,
    )
    low = score_candidate(
        demand_velocity=5, max_demand_velocity=100, total_distance=95, max_distance=100,
        needed_volume=5, available_volume=10, accessibility_level=1, picking_priority=5,
    )
    assert high.total_score > low.total_score
    assert any("demand" in r.lower() for r in high.reasons)


# ---------------------------------------------------------------------------
# Engine (pure unit tests)
# ---------------------------------------------------------------------------


def _engine_sku(sku_id, **overrides):
    defaults = dict(
        sku_code="SKU", weight=1.0, volume=1.0, category=None,
        temperature_requirement=None, fragility="none", hazard_class="none", picking_priority=3,
    )
    defaults.update(overrides)
    return SkuInput(id=sku_id, **defaults)


def _engine_location(loc_id, **overrides):
    defaults = dict(
        location_code="LOC", x=0.0, y=0.0, max_weight=1000.0, max_volume=1000.0, used_capacity=0.0,
        allowed_categories=[], temperature_restriction=None, hazard_restriction=None, fragility_restriction=None,
        is_active=True, is_blocked=False, is_available=True, location_type="storage", accessibility_level=3,
    )
    defaults.update(overrides)
    return LocationInput(id=loc_id, **defaults)


def test_engine_recommends_putaway_for_unplaced_stock():
    sku_id, loc_id, rec_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    candidates = generate_recommendations(
        inventory_records=[InventoryRecordInput(id=rec_id, sku_id=sku_id, current_location_id=None, quantity=10, status="awaiting_putaway")],
        skus_by_id={sku_id: _engine_sku(sku_id)},
        locations=[_engine_location(loc_id)],
        demand_velocity_by_sku={sku_id: 5.0},
        confidence_by_sku={sku_id: 0.8},
        receiving_point=(0, 0),
        dispatch_point=(100, 0),
        suppressed_inventory_record_ids=set(),
    )
    assert len(candidates) == 1
    assert candidates[0].recommended_location_id == loc_id
    assert candidates[0].current_location_id is None


def test_engine_does_not_recommend_moving_already_optimal_stock():
    sku_id, loc_id, rec_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    candidates = generate_recommendations(
        inventory_records=[InventoryRecordInput(id=rec_id, sku_id=sku_id, current_location_id=loc_id, quantity=10, status="in_stock")],
        skus_by_id={sku_id: _engine_sku(sku_id)},
        locations=[_engine_location(loc_id)],  # only one eligible location = the current one
        demand_velocity_by_sku={sku_id: 5.0},
        confidence_by_sku={sku_id: 0.8},
        receiving_point=(0, 0),
        dispatch_point=(100, 0),
        suppressed_inventory_record_ids=set(),
    )
    assert candidates == []


def test_engine_recommends_relocation_when_much_better_location_exists():
    sku_id = uuid.uuid4()
    rec_id = uuid.uuid4()
    far_loc, close_loc = uuid.uuid4(), uuid.uuid4()
    candidates = generate_recommendations(
        inventory_records=[InventoryRecordInput(id=rec_id, sku_id=sku_id, current_location_id=far_loc, quantity=10, status="in_stock")],
        skus_by_id={sku_id: _engine_sku(sku_id, picking_priority=1)},
        locations=[
            _engine_location(far_loc, x=1000, y=1000, accessibility_level=1),
            _engine_location(close_loc, x=1, y=1, accessibility_level=5),
        ],
        demand_velocity_by_sku={sku_id: 100.0},  # fast mover - benefits a lot from a better slot
        confidence_by_sku={sku_id: 0.9},
        receiving_point=(0, 0),
        dispatch_point=(0, 0),
        suppressed_inventory_record_ids=set(),
        min_expected_benefit=0.01,
    )
    assert len(candidates) == 1
    assert candidates[0].recommended_location_id == close_loc
    assert candidates[0].expected_benefit > 0


def test_engine_excludes_ineligible_locations():
    sku_id, rec_id = uuid.uuid4(), uuid.uuid4()
    frozen_loc, ambient_loc = uuid.uuid4(), uuid.uuid4()
    candidates = generate_recommendations(
        inventory_records=[InventoryRecordInput(id=rec_id, sku_id=sku_id, current_location_id=None, quantity=5, status="awaiting_putaway")],
        skus_by_id={sku_id: _engine_sku(sku_id, temperature_requirement="frozen")},
        locations=[
            _engine_location(ambient_loc, temperature_restriction=None),
            _engine_location(frozen_loc, temperature_restriction="frozen"),
        ],
        demand_velocity_by_sku={sku_id: 5.0},
        confidence_by_sku={sku_id: 0.8},
        receiving_point=None,
        dispatch_point=None,
        suppressed_inventory_record_ids=set(),
    )
    assert len(candidates) == 1
    assert candidates[0].recommended_location_id == frozen_loc


def test_engine_suppresses_explicitly_suppressed_records():
    sku_id, loc_id, rec_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    candidates = generate_recommendations(
        inventory_records=[InventoryRecordInput(id=rec_id, sku_id=sku_id, current_location_id=None, quantity=5, status="awaiting_putaway")],
        skus_by_id={sku_id: _engine_sku(sku_id)},
        locations=[_engine_location(loc_id)],
        demand_velocity_by_sku={sku_id: 5.0},
        confidence_by_sku={sku_id: 0.8},
        receiving_point=None,
        dispatch_point=None,
        suppressed_inventory_record_ids={rec_id},
    )
    assert candidates == []


def test_engine_respects_min_confidence_threshold():
    sku_id, loc_id, rec_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    candidates = generate_recommendations(
        inventory_records=[InventoryRecordInput(id=rec_id, sku_id=sku_id, current_location_id=None, quantity=5, status="awaiting_putaway")],
        skus_by_id={sku_id: _engine_sku(sku_id)},
        locations=[_engine_location(loc_id)],
        demand_velocity_by_sku={sku_id: 5.0},
        confidence_by_sku={sku_id: 0.1},  # below default 0.4 threshold
        receiving_point=None,
        dispatch_point=None,
        suppressed_inventory_record_ids=set(),
    )
    assert candidates == []


# ---------------------------------------------------------------------------
# Full API flow
# ---------------------------------------------------------------------------


def test_generate_recommendations_end_to_end(client):
    headers = register_and_login(client, "Rec Co A", "a@rec.example.com")
    wh = _create_warehouse(client, headers, "R1")
    sku = _create_sku(client, headers, "RSKU-A1")

    _create_location(client, headers, wh["id"], location_code="RCV-1", location_type="receiving", x=0, y=0)
    _create_location(client, headers, wh["id"], location_code="DSP-1", location_type="dispatch", x=100, y=0)
    _create_location(client, headers, wh["id"], location_code="BIN-CLOSE", location_type="storage", x=5, y=5, width=2, height=2)
    _create_location(client, headers, wh["id"], location_code="BIN-FAR", location_type="storage", x=90, y=90, width=2, height=2)

    upload = _upload_inventory_csv(client, headers, wh["id"], [("RSKU-A1", None, 10)])
    assert upload.json()["committed"] is True

    gen_resp = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/generate", headers=headers)
    assert gen_resp.status_code == 202, gen_resp.text
    job = gen_resp.json()

    job_status = client.get(f"/api/v1/warehouses/{wh['id']}/recommendations/jobs/{job['id']}", headers=headers).json()
    assert job_status["status"] == "succeeded"
    assert job_status["recommendations_created"] == 1

    listing = client.get(f"/api/v1/warehouses/{wh['id']}/recommendations", headers=headers).json()
    assert listing["total"] == 1
    rec = listing["items"][0]
    assert rec["sku_code"] == "RSKU-A1"
    assert rec["status"] == "pending_review"
    assert rec["requires_approval"] is True
    assert len(rec["reason"]) > 0


def test_generate_recommendations_fails_gracefully_with_no_inventory(client):
    headers = register_and_login(client, "Rec Co B", "b@rec.example.com")
    wh = _create_warehouse(client, headers, "R2")

    gen_resp = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/generate", headers=headers)
    job = gen_resp.json()
    job_status = client.get(f"/api/v1/warehouses/{wh['id']}/recommendations/jobs/{job['id']}", headers=headers).json()
    assert job_status["status"] == "failed"
    assert "inventory" in job_status["error"].lower()


def test_recommendation_job_tenant_isolation(client):
    headers_a = register_and_login(client, "Rec Tenant A", "usera@rectenant.example.com")
    headers_b = register_and_login(client, "Rec Tenant B", "userb@rectenant.example.com")
    wh = _create_warehouse(client, headers_a, "RT1")

    resp = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/generate", headers=headers_b)
    assert resp.status_code == 404


def test_rerunning_generation_does_not_duplicate_unchanged_recommendations(client):
    headers = register_and_login(client, "Rec Co C", "c@rec.example.com")
    wh = _create_warehouse(client, headers, "R3")
    _create_sku(client, headers, "RSKU-C1")

    _create_location(client, headers, wh["id"], location_code="RCV-1", location_type="receiving", x=0, y=0)
    _create_location(client, headers, wh["id"], location_code="DSP-1", location_type="dispatch", x=100, y=0)
    _create_location(client, headers, wh["id"], location_code="BIN-1", location_type="storage", x=5, y=5, width=2, height=2)

    _upload_inventory_csv(client, headers, wh["id"], [("RSKU-C1", None, 10)])

    job1 = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/generate", headers=headers).json()
    client.get(f"/api/v1/warehouses/{wh['id']}/recommendations/jobs/{job1['id']}", headers=headers)

    job2 = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/generate", headers=headers).json()
    job2_status = client.get(f"/api/v1/warehouses/{wh['id']}/recommendations/jobs/{job2['id']}", headers=headers).json()
    assert job2_status["status"] == "succeeded"

    listing = client.get(f"/api/v1/warehouses/{wh['id']}/recommendations", headers=headers).json()
    # Still just one open recommendation for this inventory record - no duplicate spam.
    assert listing["total"] == 1
