import io

from tests.conftest import register_and_login


def _create_warehouse(client, headers, code="PWH1"):
    return client.post("/api/v1/warehouses", headers=headers, json={"name": "P3 WH", "code": code}).json()


def _create_sku(client, headers, sku_code="SKU-001", **overrides):
    body = {"sku_code": sku_code, "name": "Widget", **overrides}
    return client.post("/api/v1/skus", headers=headers, json=body)


# ---------------------------------------------------------------------------
# SKU CRUD
# ---------------------------------------------------------------------------


def test_create_and_list_sku(client):
    headers = register_and_login(client, "SKU Co A", "a@sku.example.com")
    resp = _create_sku(client, headers)
    assert resp.status_code == 201, resp.text

    listing = client.get("/api/v1/skus", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


def test_duplicate_sku_code_rejected(client):
    headers = register_and_login(client, "SKU Co B", "b@sku.example.com")
    assert _create_sku(client, headers, "DUP1").status_code == 201
    assert _create_sku(client, headers, "DUP1").status_code == 409


def test_invalid_fragility_rejected(client):
    headers = register_and_login(client, "SKU Co C", "c@sku.example.com")
    resp = _create_sku(client, headers, "F1", fragility="ultra-fragile")
    assert resp.status_code == 422


def test_fefo_requires_expiry_tracking(client):
    headers = register_and_login(client, "SKU Co D", "d@sku.example.com")
    resp = _create_sku(client, headers, "FEFO1", fefo_required=True, requires_expiry=False)
    assert resp.status_code == 422


def test_update_and_deactivate_sku(client):
    headers = register_and_login(client, "SKU Co E", "e@sku.example.com")
    created = _create_sku(client, headers, "U1").json()
    updated = client.patch(f"/api/v1/skus/{created['id']}", headers=headers, json={"reorder_point": 25})
    assert updated.status_code == 200
    assert updated.json()["reorder_point"] == 25

    deactivated = client.delete(f"/api/v1/skus/{created['id']}", headers=headers)
    assert deactivated.status_code == 204
    fetched = client.get(f"/api/v1/skus/{created['id']}", headers=headers)
    assert fetched.json()["is_active"] is False


def test_sku_tenant_isolation(client):
    headers_a = register_and_login(client, "SKU Tenant A", "usera@skutenant.example.com")
    headers_b = register_and_login(client, "SKU Tenant B", "userb@skutenant.example.com")
    created = _create_sku(client, headers_a, "ISO1").json()

    fetch_b = client.get(f"/api/v1/skus/{created['id']}", headers=headers_b)
    assert fetch_b.status_code == 404


# ---------------------------------------------------------------------------
# SKU bulk upload
# ---------------------------------------------------------------------------


def test_sku_upload_valid_csv_commits(client):
    headers = register_and_login(client, "SKU Co F", "f@sku.example.com")
    csv_content = "sku_code,name,fifo_required,fefo_required,requires_expiry\nBULK-1,Bulk Widget,true,false,false\nBULK-2,Bulk Gadget,true,false,false\n"
    files = {"file": ("skus.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post("/api/v1/skus/upload", headers=headers, files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["committed"] is True
    assert body["records_created"] == 2


def test_sku_upload_missing_name_fails_and_does_not_commit(client):
    headers = register_and_login(client, "SKU Co G", "g@sku.example.com")
    csv_content = "sku_code,name\nBULK-1,\n"
    files = {"file": ("skus.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post("/api/v1/skus/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert body["committed"] is False
    listing = client.get("/api/v1/skus", headers=headers)
    assert listing.json()["total"] == 0


def test_sku_template_download(client):
    headers = register_and_login(client, "SKU Co H", "h@sku.example.com")
    resp = client.get("/api/v1/skus/upload/template", headers=headers)
    assert resp.status_code == 200
    assert "sku_code" in resp.text


# ---------------------------------------------------------------------------
# Sales upload
# ---------------------------------------------------------------------------


def test_sales_upload_valid_commits_and_resolves_sku(client):
    headers = register_and_login(client, "Sales Co A", "a@sales.example.com")
    wh = _create_warehouse(client, headers, "S1")
    _create_sku(client, headers, "SALESKU-1")

    csv_content = "date,sku_id,quantity_sold\n2026-01-05,SALESKU-1,10\n2026-01-06,SALESKU-1,5\n"
    files = {"file": ("sales.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/sales/upload", headers=headers, files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["committed"] is True
    assert body["records_created"] == 2

    listing = client.get(f"/api/v1/warehouses/{wh['id']}/sales", headers=headers)
    assert listing.json()["total"] == 2


def test_sales_upload_unknown_sku_fails(client):
    headers = register_and_login(client, "Sales Co B", "b@sales.example.com")
    wh = _create_warehouse(client, headers, "S2")

    csv_content = "date,sku_id,quantity_sold\n2026-01-05,GHOST-SKU,10\n"
    files = {"file": ("sales.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/sales/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert any("Unknown SKU" in e["message"] for e in body["errors"])


def test_sales_upload_negative_quantity_fails(client):
    headers = register_and_login(client, "Sales Co C", "c@sales.example.com")
    wh = _create_warehouse(client, headers, "S3")
    _create_sku(client, headers, "NEGSKU")

    csv_content = "date,sku_id,quantity_sold\n2026-01-05,NEGSKU,-3\n"
    files = {"file": ("sales.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/sales/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False


def test_sales_upload_duplicate_record_fails(client):
    headers = register_and_login(client, "Sales Co D", "d@sales.example.com")
    wh = _create_warehouse(client, headers, "S4")
    _create_sku(client, headers, "DUPSALE")

    csv_content = "date,sku_id,quantity_sold,order_id\n2026-01-05,DUPSALE,10,ORD-1\n2026-01-05,DUPSALE,20,ORD-1\n"
    files = {"file": ("sales.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/sales/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert any("Duplicate" in e["message"] for e in body["errors"])


# ---------------------------------------------------------------------------
# Inventory upload
# ---------------------------------------------------------------------------


def test_inventory_upload_valid_commits_and_creates_batch(client):
    headers = register_and_login(client, "Inv Co A", "a@inv.example.com")
    wh = _create_warehouse(client, headers, "I1")
    _create_sku(client, headers, "INVSKU-1")
    client.post(
        f"/api/v1/warehouses/{wh['id']}/locations",
        headers=headers,
        json={"location_code": "LOC-1", "location_type": "storage", "storage_type": "bin", "x": 0, "y": 0, "width": 1, "height": 1},
    )

    csv_content = (
        "sku_id,location_id,quantity,batch_number,receiving_date\n"
        "INVSKU-1,LOC-1,100,BATCH-1,2026-01-01\n"
    )
    files = {"file": ("inventory.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/inventory/upload", headers=headers, files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["committed"] is True
    assert body["records_created"] == 1

    listing = client.get(f"/api/v1/warehouses/{wh['id']}/inventory", headers=headers).json()
    assert listing["total"] == 1
    assert listing["items"][0]["quantity"] == 100
    assert listing["items"][0]["status"] == "in_stock"
    assert listing["items"][0]["available_quantity"] == 100


def test_inventory_upload_without_location_is_awaiting_putaway(client):
    headers = register_and_login(client, "Inv Co B", "b@inv.example.com")
    wh = _create_warehouse(client, headers, "I2")
    _create_sku(client, headers, "INVSKU-2")

    csv_content = "sku_id,location_id,quantity,receiving_date\nINVSKU-2,,50,2026-01-01\n"
    files = {"file": ("inventory.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/inventory/upload", headers=headers, files=files)
    body = resp.json()
    assert body["committed"] is True

    listing = client.get(f"/api/v1/warehouses/{wh['id']}/inventory", headers=headers).json()
    assert listing["items"][0]["status"] == "awaiting_putaway"
    assert listing["items"][0]["current_location_id"] is None


def test_inventory_upload_unknown_location_fails(client):
    headers = register_and_login(client, "Inv Co C", "c@inv.example.com")
    wh = _create_warehouse(client, headers, "I3")
    _create_sku(client, headers, "INVSKU-3")

    csv_content = "sku_id,location_id,quantity,receiving_date\nINVSKU-3,GHOST-LOC,50,2026-01-01\n"
    files = {"file": ("inventory.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/inventory/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert any("Unknown storage location" in e["message"] for e in body["errors"])


def test_inventory_upload_reserved_exceeds_quantity_fails(client):
    headers = register_and_login(client, "Inv Co D", "d@inv.example.com")
    wh = _create_warehouse(client, headers, "I4")
    _create_sku(client, headers, "INVSKU-4")

    csv_content = "sku_id,location_id,quantity,reserved_quantity,receiving_date\nINVSKU-4,,10,20,2026-01-01\n"
    files = {"file": ("inventory.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/inventory/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert any("cannot exceed quantity" in e["message"] for e in body["errors"])


def test_inventory_upload_invalid_expiry_before_receiving_fails(client):
    headers = register_and_login(client, "Inv Co E", "e@inv.example.com")
    wh = _create_warehouse(client, headers, "I5")
    _create_sku(client, headers, "INVSKU-5")

    csv_content = (
        "sku_id,location_id,quantity,receiving_date,expiry_date\n"
        "INVSKU-5,,10,2026-05-01,2026-01-01\n"
    )
    files = {"file": ("inventory.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/inventory/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert any("before receiving_date" in e["message"] for e in body["errors"])


def test_inventory_template_download(client):
    headers = register_and_login(client, "Inv Co F", "f@inv.example.com")
    wh = _create_warehouse(client, headers, "I6")
    resp = client.get(f"/api/v1/warehouses/{wh['id']}/inventory/upload/template", headers=headers)
    assert resp.status_code == 200
    assert "sku_id" in resp.text
