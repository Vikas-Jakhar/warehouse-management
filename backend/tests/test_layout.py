import io

from tests.conftest import register_and_login


def _create_warehouse(client, headers, code="LWH1"):
    return client.post("/api/v1/warehouses", headers=headers, json={"name": "Layout WH", "code": code}).json()


def test_create_zone_and_list(client):
    headers = register_and_login(client, "Layout Co A", "a@layout.example.com")
    wh = _create_warehouse(client, headers, "L1")

    resp = client.post(
        f"/api/v1/warehouses/{wh['id']}/zones",
        headers=headers,
        json={"name": "Zone A", "zone_code": "ZA", "zone_type": "storage"},
    )
    assert resp.status_code == 201, resp.text

    listing = client.get(f"/api/v1/warehouses/{wh['id']}/zones", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_create_location_requires_valid_types(client):
    headers = register_and_login(client, "Layout Co B", "b@layout.example.com")
    wh = _create_warehouse(client, headers, "L2")

    bad = client.post(
        f"/api/v1/warehouses/{wh['id']}/locations",
        headers=headers,
        json={"location_code": "A1", "location_type": "bogus", "x": 0, "y": 0, "width": 1, "height": 1},
    )
    assert bad.status_code == 422

    good = client.post(
        f"/api/v1/warehouses/{wh['id']}/locations",
        headers=headers,
        json={"location_code": "A1", "location_type": "storage", "storage_type": "bin", "x": 0, "y": 0, "width": 1, "height": 1},
    )
    assert good.status_code == 201


def test_duplicate_location_code_rejected(client):
    headers = register_and_login(client, "Layout Co C", "c@layout.example.com")
    wh = _create_warehouse(client, headers, "L3")
    body = {"location_code": "DUP", "location_type": "storage", "storage_type": "bin", "x": 0, "y": 0, "width": 1, "height": 1}
    assert client.post(f"/api/v1/warehouses/{wh['id']}/locations", headers=headers, json=body).status_code == 201
    dup = client.post(f"/api/v1/warehouses/{wh['id']}/locations", headers=headers, json=body)
    assert dup.status_code == 409


def test_update_and_deactivate_location(client):
    headers = register_and_login(client, "Layout Co D", "d@layout.example.com")
    wh = _create_warehouse(client, headers, "L4")
    created = client.post(
        f"/api/v1/warehouses/{wh['id']}/locations",
        headers=headers,
        json={"location_code": "M1", "location_type": "storage", "storage_type": "bin", "x": 0, "y": 0, "width": 1, "height": 1},
    ).json()

    updated = client.patch(
        f"/api/v1/warehouses/{wh['id']}/locations/{created['id']}", headers=headers, json={"is_blocked": True}
    )
    assert updated.status_code == 200
    assert updated.json()["is_blocked"] is True

    deactivated = client.delete(f"/api/v1/warehouses/{wh['id']}/locations/{created['id']}", headers=headers)
    assert deactivated.status_code == 204


def test_layout_upload_valid_csv_commits(client):
    headers = register_and_login(client, "Layout Co E", "e@layout.example.com")
    wh = _create_warehouse(client, headers, "L5")

    csv_content = (
        "location_code,location_type,storage_type,zone_code,zone_type,zone_name,x,y,width,height\n"
        "RCV-01,receiving,floor,,,,0,0,10,10\n"
        "DSP-01,dispatch,floor,,,,90,0,10,10\n"
        "A-01-01,storage,bin,ZONE-A,storage,Zone A,10,10,2,2\n"
    )
    files = {"file": ("layout.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/layout/upload", headers=headers, files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_valid"] is True
    assert body["committed"] is True
    assert body["locations_created"] == 3
    assert body["zones_created"] == 1

    locations = client.get(f"/api/v1/warehouses/{wh['id']}/locations", headers=headers).json()
    assert len(locations) == 3
    zones = client.get(f"/api/v1/warehouses/{wh['id']}/zones", headers=headers).json()
    assert len(zones) == 1
    assert zones[0]["zone_code"] == "ZONE-A"


def test_layout_upload_missing_dispatch_point_fails_and_does_not_commit(client):
    headers = register_and_login(client, "Layout Co F", "f@layout.example.com")
    wh = _create_warehouse(client, headers, "L6")

    csv_content = (
        "location_code,location_type,storage_type,x,y,width,height\n"
        "RCV-01,receiving,floor,0,0,10,10\n"
    )
    files = {"file": ("layout.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/layout/upload", headers=headers, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_valid"] is False
    assert body["committed"] is False
    assert any("dispatch" in e["message"] for e in body["errors"])

    # Nothing should have been persisted since validation failed.
    locations = client.get(f"/api/v1/warehouses/{wh['id']}/locations", headers=headers).json()
    assert len(locations) == 0


def test_layout_upload_duplicate_location_codes_in_file_fails(client):
    headers = register_and_login(client, "Layout Co G", "g@layout.example.com")
    wh = _create_warehouse(client, headers, "L7")

    csv_content = (
        "location_code,location_type,storage_type,x,y,width,height\n"
        "RCV-01,receiving,floor,0,0,10,10\n"
        "DSP-01,dispatch,floor,90,0,10,10\n"
        "A-01,storage,bin,10,10,2,2\n"
        "A-01,storage,bin,20,20,2,2\n"
    )
    files = {"file": ("layout.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/layout/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert any("Duplicate location_code" in e["message"] for e in body["errors"])


def test_layout_upload_overlapping_locations_fails(client):
    headers = register_and_login(client, "Layout Co H", "h@layout.example.com")
    wh = _create_warehouse(client, headers, "L8")

    csv_content = (
        "location_code,location_type,storage_type,x,y,width,height\n"
        "RCV-01,receiving,floor,0,0,10,10\n"
        "DSP-01,dispatch,floor,90,0,10,10\n"
        "A-01,storage,bin,10,10,5,5\n"
        "A-02,storage,bin,12,12,5,5\n"
    )
    files = {"file": ("layout.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/layout/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert any("overlaps" in e["message"] for e in body["errors"])


def test_layout_upload_unsupported_storage_type_fails(client):
    headers = register_and_login(client, "Layout Co I", "i@layout.example.com")
    wh = _create_warehouse(client, headers, "L9")

    csv_content = (
        "location_code,location_type,storage_type,x,y,width,height\n"
        "RCV-01,receiving,floor,0,0,10,10\n"
        "DSP-01,dispatch,floor,90,0,10,10\n"
        "A-01,storage,not_a_real_type,10,10,2,2\n"
    )
    files = {"file": ("layout.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = client.post(f"/api/v1/warehouses/{wh['id']}/layout/upload", headers=headers, files=files)
    body = resp.json()
    assert body["is_valid"] is False
    assert any("storage_type" in e["field"] for e in body["errors"])


def test_layout_template_download(client):
    headers = register_and_login(client, "Layout Co J", "j@layout.example.com")
    wh = _create_warehouse(client, headers, "L10")
    resp = client.get(f"/api/v1/warehouses/{wh['id']}/layout/template", headers=headers)
    assert resp.status_code == 200
    assert "location_code" in resp.text


def test_layout_endpoints_respect_tenant_isolation(client):
    headers_a = register_and_login(client, "Layout Tenant A", "usera@layouttenant.example.com")
    headers_b = register_and_login(client, "Layout Tenant B", "userb@layouttenant.example.com")
    wh = _create_warehouse(client, headers_a, "LT1")

    resp = client.get(f"/api/v1/warehouses/{wh['id']}/locations", headers=headers_b)
    assert resp.status_code == 404
