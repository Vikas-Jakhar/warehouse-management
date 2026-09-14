import io
from datetime import date, timedelta

from tests.conftest import register_and_login


def _create_warehouse(client, headers, code="RPT1"):
    return client.post("/api/v1/warehouses", headers=headers, json={"name": "Reports WH", "code": code}).json()


def _create_sku(client, headers, sku_code, **overrides):
    body = {"sku_code": sku_code, "name": f"Widget {sku_code}", **overrides}
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
    lines = ["sku_id,location_id,quantity,batch_number,receiving_date,expiry_date"] + [
        f"{sku},{loc or ''},{qty},{batch or ''},{recv},{exp or ''}" for sku, loc, qty, batch, recv, exp in rows
    ]
    csv_content = "\n".join(lines) + "\n"
    files = {"file": ("inv.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    return client.post(f"/api/v1/warehouses/{warehouse_id}/inventory/upload", headers=headers, files=files)


def _upload_sales_csv(client, headers, warehouse_id, rows):
    lines = ["date,sku_id,quantity_sold"] + [f"{d},{s},{q}" for d, s, q in rows]
    csv_content = "\n".join(lines) + "\n"
    files = {"file": ("sales.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    return client.post(f"/api/v1/warehouses/{warehouse_id}/sales/upload", headers=headers, files=files)


def test_customer_dashboard_reflects_created_resources(client):
    headers = register_and_login(client, "Reports Co A", "a@reports.example.com")
    _create_warehouse(client, headers, "RA1")
    _create_sku(client, headers, "RASKU-1")

    dash = client.get("/api/v1/dashboard", headers=headers)
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["total_warehouses"] == 1
    assert body["total_skus"] == 1
    assert len(body["recent_activity"]) >= 1


def test_dashboard_is_isolated_per_tenant(client):
    headers_a = register_and_login(client, "Reports Tenant A", "usera@reportstenant.example.com")
    headers_b = register_and_login(client, "Reports Tenant B", "userb@reportstenant.example.com")
    _create_warehouse(client, headers_a, "RTA1")

    dash_b = client.get("/api/v1/dashboard", headers=headers_b).json()
    assert dash_b["total_warehouses"] == 0


def test_warehouse_overview_storage_utilization(client):
    headers = register_and_login(client, "Reports Co B", "b@reports.example.com")
    wh = _create_warehouse(client, headers, "RB1")
    _create_sku(client, headers, "RBSKU-1")
    _create_location(client, headers, wh["id"], location_code="BIN-1")
    _create_location(client, headers, wh["id"], location_code="BIN-2")  # left empty

    _upload_inventory_csv(client, headers, wh["id"], [("RBSKU-1", "BIN-1", 10, None, "2026-01-01", None)])

    overview = client.get(f"/api/v1/warehouses/{wh['id']}/reports/overview", headers=headers).json()
    assert overview["total_storage_locations"] == 2
    assert overview["occupied_storage_locations"] == 1
    assert overview["storage_utilization_pct"] == 50.0


def test_warehouse_overview_stockout_and_overstock_risk(client):
    headers = register_and_login(client, "Reports Co C", "c@reports.example.com")
    wh = _create_warehouse(client, headers, "RC1")
    _create_sku(client, headers, "RCSKU-LOW", reorder_point=50, max_qty=1000)
    _create_sku(client, headers, "RCSKU-HIGH", reorder_point=1, max_qty=20)

    _upload_inventory_csv(
        client,
        headers,
        wh["id"],
        [
            ("RCSKU-LOW", None, 5, None, "2026-01-01", None),  # below reorder_point -> stockout risk
            ("RCSKU-HIGH", None, 500, None, "2026-01-01", None),  # above max_qty -> overstock risk
        ],
    )

    overview = client.get(f"/api/v1/warehouses/{wh['id']}/reports/overview", headers=headers).json()
    stockout_codes = {e["sku_code"] for e in overview["stockout_risk_skus"]}
    overstock_codes = {e["sku_code"] for e in overview["overstock_risk_skus"]}
    assert "RCSKU-LOW" in stockout_codes
    assert "RCSKU-HIGH" in overstock_codes


def test_warehouse_overview_expiring_inventory(client):
    headers = register_and_login(client, "Reports Co D", "d@reports.example.com")
    wh = _create_warehouse(client, headers, "RD1")
    _create_sku(client, headers, "RDSKU-1", requires_expiry=True, fefo_required=True)

    soon = (date.today() + timedelta(days=5)).isoformat()
    far = (date.today() + timedelta(days=200)).isoformat()
    _upload_inventory_csv(
        client,
        headers,
        wh["id"],
        [
            ("RDSKU-1", None, 10, "BATCH-SOON", "2026-01-01", soon),
            ("RDSKU-1", None, 10, "BATCH-FAR", "2026-01-01", far),
        ],
    )

    overview = client.get(f"/api/v1/warehouses/{wh['id']}/reports/overview", headers=headers).json()
    expiring_batches = {e["quantity"] for e in overview["expiring_inventory"]}
    assert 10.0 in expiring_batches
    assert len(overview["expiring_inventory"]) == 1  # only the soon-to-expire batch


def test_warehouse_overview_demand_trend_and_category(client):
    headers = register_and_login(client, "Reports Co E", "e@reports.example.com")
    wh = _create_warehouse(client, headers, "RE1")
    _create_sku(client, headers, "RESKU-1", category="Electronics")
    _upload_inventory_csv(client, headers, wh["id"], [("RESKU-1", None, 10, None, "2026-01-01", None)])

    today = date.today().isoformat()
    _upload_sales_csv(client, headers, wh["id"], [(today, "RESKU-1", 7)])

    overview = client.get(f"/api/v1/warehouses/{wh['id']}/reports/overview", headers=headers).json()
    assert any(p["quantity_sold"] == 7.0 for p in overview["demand_trend"])
    assert any(c["category"] == "Electronics" and c["quantity"] == 10.0 for c in overview["inventory_by_category"])


def test_warehouse_overview_recommendation_and_movement_counts(client):
    headers = register_and_login(client, "Reports Co F", "f@reports.example.com")
    wh = _create_warehouse(client, headers, "RF1")
    _create_sku(client, headers, "RFSKU-1")
    _create_location(client, headers, wh["id"], location_code="RCV-1", location_type="receiving", x=0, y=0)
    _create_location(client, headers, wh["id"], location_code="DSP-1", location_type="dispatch", x=100, y=0)
    _create_location(client, headers, wh["id"], location_code="BIN-1", x=5, y=5)

    _upload_inventory_csv(client, headers, wh["id"], [("RFSKU-1", None, 10, None, "2026-01-01", None)])
    job = client.post(f"/api/v1/warehouses/{wh['id']}/recommendations/generate", headers=headers).json()
    client.get(f"/api/v1/warehouses/{wh['id']}/recommendations/jobs/{job['id']}", headers=headers)

    overview = client.get(f"/api/v1/warehouses/{wh['id']}/reports/overview", headers=headers).json()
    assert overview["recommendation_status_counts"].get("pending_review") == 1


def test_warehouse_overview_aging_works_without_batch_number(client):
    """Regression test: inventory uploaded without a batch_number must still
    carry its receiving_date into the aging report, not vanish silently."""
    headers = register_and_login(client, "Reports Co G", "g@reports.example.com")
    wh = _create_warehouse(client, headers, "RG1")
    _create_sku(client, headers, "RGSKU-1")

    csv_content = "sku_id,location_id,quantity,receiving_date\nRGSKU-1,,15,2026-01-01\n"
    files = {"file": ("inv.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/inventory/upload", headers=headers, files=files)
    assert resp.json()["committed"] is True

    overview = client.get(f"/api/v1/warehouses/{wh['id']}/reports/overview", headers=headers).json()
    total_aged_quantity = sum(b["quantity"] for b in overview["inventory_aging"])
    assert total_aged_quantity == 15.0
    assert any(b["bucket"] == "91+" for b in overview["inventory_aging"])


def test_warehouse_overview_tenant_isolation(client):
    headers_a = register_and_login(client, "Reports Tenant C", "usera@reportstenantc.example.com")
    headers_b = register_and_login(client, "Reports Tenant D", "userb@reportstenantc.example.com")
    wh = _create_warehouse(client, headers_a, "RTC1")

    resp = client.get(f"/api/v1/warehouses/{wh['id']}/reports/overview", headers=headers_b)
    assert resp.status_code == 404
