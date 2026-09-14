from tests.conftest import register_and_login


def test_create_and_list_warehouse(client):
    headers = register_and_login(client, "Acme A", "a@acme.example.com")
    resp = client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"name": "Main DC", "code": "DC1", "default_inventory_policy": "FEFO"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Main DC"
    assert body["default_inventory_policy"] == "FEFO"

    listing = client.get("/api/v1/warehouses", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


def test_duplicate_warehouse_code_rejected(client):
    headers = register_and_login(client, "Acme B", "b@acme.example.com")
    client.post("/api/v1/warehouses", headers=headers, json={"name": "DC", "code": "X1"})
    dup = client.post("/api/v1/warehouses", headers=headers, json={"name": "DC2", "code": "X1"})
    assert dup.status_code == 409


def test_invalid_policy_rejected(client):
    headers = register_and_login(client, "Acme C", "c@acme.example.com")
    resp = client.post(
        "/api/v1/warehouses", headers=headers, json={"name": "DC", "code": "Y1", "default_inventory_policy": "BOGUS"}
    )
    assert resp.status_code == 422


def test_update_and_deactivate_warehouse(client):
    headers = register_and_login(client, "Acme D", "d@acme.example.com")
    created = client.post("/api/v1/warehouses", headers=headers, json={"name": "DC", "code": "Z1"}).json()

    updated = client.patch(f"/api/v1/warehouses/{created['id']}", headers=headers, json={"name": "DC Renamed"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "DC Renamed"

    deactivated = client.delete(f"/api/v1/warehouses/{created['id']}", headers=headers)
    assert deactivated.status_code == 204

    fetched = client.get(f"/api/v1/warehouses/{created['id']}", headers=headers)
    assert fetched.json()["is_active"] is False


def test_tenant_isolation_warehouses(client):
    headers_a = register_and_login(client, "Tenant A", "usera@tenant.example.com")
    headers_b = register_and_login(client, "Tenant B", "userb@tenant.example.com")

    created = client.post("/api/v1/warehouses", headers=headers_a, json={"name": "A-DC", "code": "A1"}).json()

    # Tenant B must not be able to see or fetch Tenant A's warehouse.
    listing_b = client.get("/api/v1/warehouses", headers=headers_b)
    assert listing_b.json()["total"] == 0

    fetch_b = client.get(f"/api/v1/warehouses/{created['id']}", headers=headers_b)
    assert fetch_b.status_code == 404  # not 403 - existence is not revealed


def test_warehouse_creation_writes_audit_log(client):
    headers = register_and_login(client, "Acme E", "e@acme.example.com")
    client.post("/api/v1/warehouses", headers=headers, json={"name": "DC", "code": "AUD1"})
    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json()["items"]]
    assert "create" in actions
    assert "register" in actions
