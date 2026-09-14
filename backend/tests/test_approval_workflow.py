import io

from tests.conftest import register_and_login


def _create_warehouse(client, headers, code="AWH1"):
    return client.post("/api/v1/warehouses", headers=headers, json={"name": "Approval WH", "code": code}).json()


def _create_sku(client, headers, sku_code="ASKU-1"):
    return client.post("/api/v1/skus", headers=headers, json={"sku_code": sku_code, "name": "Widget"}).json()


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


def _setup_warehouse_with_one_recommendation(client, headers, code):
    wh = _create_warehouse(client, headers, code)
    sku = _create_sku(client, headers, f"{code}-SKU")
    _create_location(client, headers, wh["id"], location_code="RCV-1", location_type="receiving", x=0, y=0)
    _create_location(client, headers, wh["id"], location_code="DSP-1", location_type="dispatch", x=100, y=0)
    _create_location(client, headers, wh["id"], location_code="BIN-1", location_type="storage", x=5, y=5)
    _upload_inventory_csv(client, headers, wh["id"], [(f"{code}-SKU", None, 10)])

    job = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/generate", headers=headers).json()
    client.get(f"/api/v1/warehouses/{wh['id']}/recommendations/jobs/{job['id']}", headers=headers)
    recs = client.get(f"/api/v1/warehouses/{wh['id']}/recommendations", headers=headers).json()
    assert recs["total"] == 1
    return wh, sku, recs["items"][0]


# ---------------------------------------------------------------------------
# Accept -> movement created -> confirm -> actual location changes
# ---------------------------------------------------------------------------


def test_accept_creates_movement_task_without_changing_location(client):
    headers = register_and_login(client, "Approval Co A", "a@approval.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers, "AA1")

    before = client.get(f"/api/v1/warehouses/{wh['id']}/inventory", headers=headers).json()["items"][0]
    assert before["current_location_id"] is None  # was awaiting_putaway

    accept_resp = client.post(
        f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/accept", headers=headers, json={}
    )
    assert accept_resp.status_code == 201, accept_resp.text
    movement = accept_resp.json()
    assert movement["status"] == "pending"
    assert movement["to_location_code"] == "BIN-1"

    # Accepting must NOT have changed the actual inventory location yet.
    after_accept = client.get(f"/api/v1/warehouses/{wh['id']}/inventory", headers=headers).json()["items"][0]
    assert after_accept["current_location_id"] is None


def test_confirm_movement_updates_actual_location(client):
    headers = register_and_login(client, "Approval Co B", "b@approval.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers, "AB1")

    movement = client.post(
        f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/accept", headers=headers, json={}
    ).json()

    confirm_resp = client.post(
        f"/api/v1/warehouses/{wh['id']}/movements/{movement['id']}/confirm", headers=headers, json={"notes": "placed on shelf"}
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["status"] == "confirmed"

    inventory = client.get(f"/api/v1/warehouses/{wh['id']}/inventory", headers=headers).json()["items"][0]
    assert inventory["current_location_id"] is not None
    assert inventory["status"] == "in_stock"


def test_cannot_double_accept_same_recommendation(client):
    headers = register_and_login(client, "Approval Co C", "c@approval.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers, "AC1")

    first = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/accept", headers=headers, json={})
    assert first.status_code == 201
    second = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/accept", headers=headers, json={})
    assert second.status_code == 409


def test_reject_requires_reason_and_does_not_create_movement(client):
    headers = register_and_login(client, "Approval Co D", "d@approval.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers, "AD1")

    missing_reason = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/reject", headers=headers, json={})
    assert missing_reason.status_code == 422

    reject_resp = client.post(
        f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/reject",
        headers=headers,
        json={"rejection_reason": "Not worth the disruption right now"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    movements = client.get(f"/api/v1/warehouses/{wh['id']}/movements", headers=headers).json()
    assert movements["total"] == 0


def test_override_uses_manager_chosen_location(client):
    headers = register_and_login(client, "Approval Co E", "e@approval.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers, "AE1")

    alt_loc = _create_location(client, headers, wh["id"], location_code="BIN-ALT", x=50, y=50)

    override_resp = client.post(
        f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/override",
        headers=headers,
        json={"override_location_id": alt_loc["id"], "comment": "Manager prefers this bin"},
    )
    assert override_resp.status_code == 201, override_resp.text
    movement = override_resp.json()
    assert movement["to_location_code"] == "BIN-ALT"


def test_override_rejects_blocked_location(client):
    headers = register_and_login(client, "Approval Co F", "f@approval.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers, "AF1")

    blocked_loc = _create_location(client, headers, wh["id"], location_code="BIN-BLOCKED", x=60, y=60)
    client.patch(f"/api/v1/warehouses/{wh['id']}/locations/{blocked_loc['id']}", headers=headers, json={"is_blocked": True})

    override_resp = client.post(
        f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/override",
        headers=headers,
        json={"override_location_id": blocked_loc["id"]},
    )
    assert override_resp.status_code == 422


def test_movement_start_then_confirm(client):
    headers = register_and_login(client, "Approval Co G", "g@approval.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers, "AG1")

    movement = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/accept", headers=headers, json={}).json()

    start_resp = client.post(f"/api/v1/warehouses/{wh['id']}/movements/{movement['id']}/start", headers=headers)
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "in_progress"

    confirm_resp = client.post(f"/api/v1/warehouses/{wh['id']}/movements/{movement['id']}/confirm", headers=headers, json={})
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "confirmed"


def test_cancel_movement(client):
    headers = register_and_login(client, "Approval Co H", "h@approval.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers, "AH1")

    movement = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/accept", headers=headers, json={}).json()
    cancel_resp = client.post(
        f"/api/v1/warehouses/{wh['id']}/movements/{movement['id']}/cancel", headers=headers, json={"reason": "changed plans"}
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Cancelled movement cannot then be confirmed.
    confirm_resp = client.post(f"/api/v1/warehouses/{wh['id']}/movements/{movement['id']}/confirm", headers=headers, json={})
    assert confirm_resp.status_code == 409

    # Actual location must remain unchanged after a cancellation.
    inventory = client.get(f"/api/v1/warehouses/{wh['id']}/inventory", headers=headers).json()["items"][0]
    assert inventory["current_location_id"] is None


def test_movement_and_recommendation_endpoints_respect_tenant_isolation(client):
    headers_a = register_and_login(client, "Approval Tenant A", "usera@approvaltenant.example.com")
    headers_b = register_and_login(client, "Approval Tenant B", "userb@approvaltenant.example.com")
    wh, sku, rec = _setup_warehouse_with_one_recommendation(client, headers_a, "AT1")

    accept_cross = client.post(
        f"/api/v1/warehouses/{wh['id']}/recommendations/{rec['id']}/accept", headers=headers_b, json={}
    )
    assert accept_cross.status_code == 404

    movements_cross = client.get(f"/api/v1/warehouses/{wh['id']}/movements", headers=headers_b)
    assert movements_cross.status_code == 404
