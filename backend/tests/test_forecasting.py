import io
from datetime import date, timedelta

from tests.conftest import register_and_login

from app.services.forecasting.pipeline import run_forecast_for_sku
from app.services.forecasting.timeseries import build_daily_series, detect_outliers, profile_series


def _create_warehouse(client, headers, code="FWH1"):
    return client.post("/api/v1/warehouses", headers=headers, json={"name": "Forecast WH", "code": code}).json()


def _create_sku(client, headers, sku_code="FSKU-1"):
    return client.post("/api/v1/skus", headers=headers, json={"sku_code": sku_code, "name": "Widget"}).json()


def _upload_sales_csv(client, headers, warehouse_id, rows: list[tuple[str, str, float]]):
    lines = ["date,sku_id,quantity_sold"] + [f"{d},{s},{q}" for d, s, q in rows]
    csv_content = "\n".join(lines) + "\n"
    files = {"file": ("sales.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    return client.post(f"/api/v1/warehouses/{warehouse_id}/sales/upload", headers=headers, files=files)


# ---------------------------------------------------------------------------
# Pure pipeline unit tests (no DB, no API)
# ---------------------------------------------------------------------------


def test_build_daily_series_fills_gaps_with_zero():
    rows = [(date(2026, 1, 1), 5.0), (date(2026, 1, 3), 7.0)]
    series = build_daily_series(rows)
    assert len(series) == 3
    assert series.iloc[1] == 0.0


def test_detect_outliers_flags_extreme_spike():
    import random

    random.seed(42)
    values = [(date(2026, 1, i + 1), 5.0 + random.uniform(-1, 1)) for i in range(20)]
    values[10] = (date(2026, 1, 11), 500.0)
    series = build_daily_series(values)
    outliers = detect_outliers(series)
    assert bool(outliers.iloc[10]) is True


def test_profile_series_detects_intermittent_demand():
    rows = [(date(2026, 1, i + 1), 0.0 if i % 3 else 4.0) for i in range(20)]
    series = build_daily_series(rows)
    profile = profile_series(series)
    assert profile.is_intermittent is True


def test_pipeline_skips_when_too_little_history():
    outcome = run_forecast_for_sku("sku-x", [(date(2026, 1, 1), 3.0)], horizon_days=7)
    assert outcome.skipped_reason is not None
    assert outcome.chosen_model is None


def test_pipeline_produces_forecast_for_steady_demand():
    rows = [(date(2026, 1, 1) + timedelta(days=i), 10.0) for i in range(30)]
    outcome = run_forecast_for_sku("sku-steady", rows, horizon_days=7)
    assert outcome.skipped_reason is None
    assert outcome.chosen_model is not None
    assert len(outcome.forecast_values) == 7
    # Steady demand of 10/day should forecast close to 10, not wildly off.
    assert all(abs(v - 10.0) < 5.0 for v in outcome.forecast_values)
    assert len(outcome.evaluations) >= 1


def test_pipeline_confidence_interval_brackets_forecast():
    rows = [(date(2026, 1, 1) + timedelta(days=i), 10.0 + (i % 3)) for i in range(25)]
    outcome = run_forecast_for_sku("sku-ci", rows, horizon_days=5)
    for f, lo, hi in zip(outcome.forecast_values, outcome.lower_ci, outcome.upper_ci):
        assert lo <= f <= hi


def test_pipeline_intermittent_demand_uses_croston_or_naive():
    rows = [(date(2026, 1, 1) + timedelta(days=i), 20.0 if i % 5 == 0 else 0.0) for i in range(25)]
    outcome = run_forecast_for_sku("sku-intermittent", rows, horizon_days=7)
    assert outcome.skipped_reason is None
    assert outcome.profile.is_intermittent is True
    assert outcome.chosen_model in {"croston", "naive"}


# ---------------------------------------------------------------------------
# Full API flow (Celery runs eagerly in tests - see conftest)
# ---------------------------------------------------------------------------


def test_generate_forecast_end_to_end(client):
    headers = register_and_login(client, "Forecast Co A", "a@forecast.example.com")
    wh = _create_warehouse(client, headers, "F1")
    sku = _create_sku(client, headers, "FSKU-A1")

    rows = [
        ((date(2026, 1, 1) + timedelta(days=i)).isoformat(), "FSKU-A1", 10 + (i % 4))
        for i in range(30)
    ]
    upload_resp = _upload_sales_csv(client, headers, wh["id"], rows)
    assert upload_resp.json()["committed"] is True

    gen_resp = client.post(f"/api/v1/warehouses/{wh['id']}/forecasts/generate", headers=headers, json={"horizon_days": 7})
    assert gen_resp.status_code == 202, gen_resp.text
    job = gen_resp.json()
    assert job["status"] in {"queued", "running", "succeeded"}

    job_status = client.get(f"/api/v1/warehouses/{wh['id']}/forecasts/jobs/{job['id']}", headers=headers).json()
    assert job_status["status"] == "succeeded"
    assert job_status["skus_processed"] == 1
    assert job_status["skus_skipped"] == 0

    summary = client.get(f"/api/v1/warehouses/{wh['id']}/forecasts", headers=headers).json()
    assert summary["total"] == 1
    assert summary["items"][0]["sku_code"] == "FSKU-A1"
    assert summary["items"][0]["chosen_model"] is not None

    detail = client.get(f"/api/v1/warehouses/{wh['id']}/forecasts/{sku['id']}", headers=headers).json()
    assert len(detail["forecast"]) == 7
    assert len(detail["historical_demand"]) == 30
    assert detail["chosen_model"] is not None
    assert len(detail["metrics"]) >= 1


def test_generate_forecast_fails_gracefully_with_no_sales_history(client):
    headers = register_and_login(client, "Forecast Co B", "b@forecast.example.com")
    wh = _create_warehouse(client, headers, "F2")
    _create_sku(client, headers, "FSKU-B1")

    gen_resp = client.post(f"/api/v1/warehouses/{wh['id']}/forecasts/generate", headers=headers, json={"horizon_days": 7})
    job = gen_resp.json()

    job_status = client.get(f"/api/v1/warehouses/{wh['id']}/forecasts/jobs/{job['id']}", headers=headers).json()
    assert job_status["status"] == "failed"
    assert "sales history" in job_status["error"]


def test_forecast_for_single_sku_only(client):
    headers = register_and_login(client, "Forecast Co C", "c@forecast.example.com")
    wh = _create_warehouse(client, headers, "F3")
    sku1 = _create_sku(client, headers, "FSKU-C1")
    sku2 = _create_sku(client, headers, "FSKU-C2")

    rows = [((date(2026, 1, 1) + timedelta(days=i)).isoformat(), "FSKU-C1", 5) for i in range(20)]
    rows += [((date(2026, 1, 1) + timedelta(days=i)).isoformat(), "FSKU-C2", 8) for i in range(20)]
    _upload_sales_csv(client, headers, wh["id"], rows)

    gen_resp = client.post(
        f"/api/v1/warehouses/{wh['id']}/forecasts/generate",
        headers=headers,
        json={"horizon_days": 5, "sku_id": sku1["id"]},
    )
    job = gen_resp.json()
    job_status = client.get(f"/api/v1/warehouses/{wh['id']}/forecasts/jobs/{job['id']}", headers=headers).json()
    assert job_status["status"] == "succeeded"
    assert job_status["skus_processed"] == 1

    summary = client.get(f"/api/v1/warehouses/{wh['id']}/forecasts", headers=headers).json()
    assert summary["total"] == 1
    assert summary["items"][0]["sku_code"] == "FSKU-C1"


def test_forecast_job_tenant_isolation(client):
    headers_a = register_and_login(client, "Forecast Tenant A", "usera@forecasttenant.example.com")
    headers_b = register_and_login(client, "Forecast Tenant B", "userb@forecasttenant.example.com")
    wh = _create_warehouse(client, headers_a, "FT1")

    resp = client.post(f"/api/v1/warehouses/{wh['id']}/forecasts/generate", headers=headers_b, json={"horizon_days": 7})
    assert resp.status_code == 404
