# Intelligent Warehouse Management & Demand-Driven Inventory Optimization Platform
## Architecture & Design Document

---

## 1. System Architecture

```
                         ┌─────────────────────┐
                         │   React SPA (Vite)  │
                         │  TS + Tailwind +     │
                         │  TanStack Query      │
                         └──────────┬───────────┘
                                    │ HTTPS / REST (JWT)
                         ┌──────────▼───────────┐
                         │   FastAPI (Uvicorn)  │
                         │  routers / services / │
                         │  schemas / deps       │
                         └───┬───────────┬──────┘
                             │           │
                 ┌───────────▼──┐   ┌────▼─────────┐
                 │ PostgreSQL   │   │ Redis         │
                 │ (SQLAlchemy, │   │ (Celery broker│
                 │  Alembic)    │   │  + cache +    │
                 │              │   │  job status)  │
                 └──────────────┘   └────┬─────────┘
                                          │
                                ┌─────────▼──────────┐
                                │  Celery Workers      │
                                │  - forecasting        │
                                │  - slotting/optimize  │
                                │  - file validation     │
                                └───────────────────────┘
```

Everything is stateless behind FastAPI so it can horizontally scale; long-running work (forecast training, slotting optimization, large file parsing) is offloaded to Celery workers polling Redis, with job status rows persisted in Postgres so status survives worker restarts and can be polled by the frontend (`/api/v1/jobs/{id}`), with a clean seam to swap polling for WebSockets later (job status changes are already published to a Redis pub/sub channel `jobs:{job_id}` for that purpose).

## 2. Multi-Tenancy Model

Row-level tenancy: every tenant-owned table carries `customer_id`. A SQLAlchemy session-scoped dependency (`get_current_customer`) injects the authenticated user's `customer_id`, and every repository/query method requires it explicitly — there is no "global" query path for tenant tables. This is enforced at three layers:
1. FK constraints (`customer_id` required, indexed, cascades scoped).
2. Service-layer helper `scoped(query, customer_id)` used by every read/write.
3. Integration tests assert cross-tenant access returns 404 (not 403 — to avoid leaking existence).

## 3. Database Schema (core tables)

```
customers(id, name, slug, plan, created_at, is_active)
roles(id, name, permissions_json)
users(id, customer_id, email, hashed_password, full_name, role_id, is_active, created_at)
warehouses(id, customer_id, name, code, address, type, total_area, operating_hours_json,
           storage_capacity, default_inventory_policy, default_picking_policy,
           default_replenishment_policy, created_at, is_active)
zones(id, warehouse_id, name, zone_type, temperature_range, hazard_class, is_active)
storage_locations(id, warehouse_id, zone_id, location_code, aisle, rack, shelf, bin,
                   x, y, width, height, depth, max_weight, max_volume, used_capacity,
                   storage_type, accessibility_level, dist_from_receiving, dist_from_dispatch,
                   allowed_categories_json, temp_restriction, hazard_restriction,
                   fragility_restriction, is_active, is_blocked, is_available)
skus(id, customer_id, sku_code, name, description, category, subcategory, brand, uom,
     length, width, height, weight, volume, storage_requirements_json, temp_requirement,
     fragility, hazard_class, min_qty, max_qty, reorder_point, safety_stock, lead_time_days,
     shelf_life_days, requires_expiry, preferred_zone_id, picking_priority,
     fifo_required, fefo_required, lifo_permitted, is_active)
sales_records(id, warehouse_id, sku_id, date, qty_sold, order_id, channel, region,
              promotion, price, discount, holiday_flag, returns, stockout_flag)
inventory_records(id, warehouse_id, sku_id, batch_id, current_location_id, quantity,
                  reserved_qty, available_qty, damaged_qty, status)
inventory_batches(id, sku_id, batch_number, lot_number, manufacturing_date,
                  receiving_date, expiry_date)
receiving_shipments(id, warehouse_id, sku_id, batch_id, quantity, status, received_at)
warehouse_policies(id, warehouse_id, level [warehouse/zone/sku/batch], ref_id,
                   policy [FIFO/FEFO/LIFO], set_by, set_at)
forecast_jobs(id, warehouse_id, sku_id nullable, status, stage, started_at, finished_at, error)
forecast_results(id, forecast_job_id, sku_id, horizon_date, forecast_qty, lower_ci, upper_ci)
forecast_model_metrics(id, forecast_job_id, sku_id, model_name, mae, rmse, mape, wape, bias)
recommendations(id, warehouse_id, sku_id, inventory_record_id, current_location_id,
                recommended_location_id, reason_json, expected_benefit, distance_reduction,
                confidence_score, requires_approval, status, created_at)
recommendation_decisions(id, recommendation_id, decision [accept/reject/override],
                         decided_by, decided_at, rejection_reason, override_location_id, comment)
movement_tasks(id, recommendation_id nullable, inventory_record_id, from_location_id,
               to_location_id, status, created_at, assigned_to)
movement_confirmations(id, movement_task_id, confirmed_by, confirmed_at, notes)
audit_logs(id, customer_id, user_id, entity_type, entity_id, action, before_json,
          after_json, created_at)
background_jobs(id, customer_id, job_type, status, stage, progress, started_at,
                finished_at, error, result_json)
```

All tables: `created_at`/`updated_at` timestamps, soft-delete via `is_active`/`deleted_at` where deletion is meaningful, and indexes on every FK plus `(customer_id, id)` composite where relevant.

## 4. API Design (representative)

```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
POST   /api/v1/auth/forgot-password
POST   /api/v1/auth/reset-password
GET    /api/v1/users/me
GET    /api/v1/customers/me
GET    /api/v1/warehouses
POST   /api/v1/warehouses
GET    /api/v1/warehouses/{id}
PATCH  /api/v1/warehouses/{id}
POST   /api/v1/layouts/{warehouse_id}/upload
GET    /api/v1/layouts/{warehouse_id}/locations
POST   /api/v1/skus/upload | POST /api/v1/skus
GET    /api/v1/sales?warehouse_id=&from=&to=
POST   /api/v1/sales/upload
GET    /api/v1/inventory?warehouse_id=
POST   /api/v1/inventory/upload
POST   /api/v1/receiving
POST   /api/v1/forecasts/generate      (async -> job id)
GET    /api/v1/forecasts/{sku_id}
POST   /api/v1/recommendations/generate (async -> job id)
GET    /api/v1/recommendations?status=
POST   /api/v1/recommendations/{id}/accept
POST   /api/v1/recommendations/{id}/reject
POST   /api/v1/recommendations/{id}/override
POST   /api/v1/movements/{id}/confirm
GET    /api/v1/reports/dashboard
GET    /api/v1/audit-logs
GET    /api/v1/jobs/{id}
```
All list endpoints support `page`, `page_size`, `sort`, `filter[...]`, `search`. Errors follow `{ "error": { "code", "message", "details" } }`.

## 5. Frontend Page Structure

`/`, `/login`, `/register`, `/forgot-password`, `/reset-password` (public) → `/app/*` (protected, wrapped in `<RequireAuth>` + `<CustomerWorkspaceProvider>`): `dashboard`, `onboarding`, `warehouses`, `warehouses/:id`, `warehouses/:id/layout-builder`, `warehouses/:id/layout-upload`, `skus`, `sales`, `inventory`, `receiving`, `putaway`, `forecasting`, `recommendations`, `recommendations/:id`, `movements`, `reports`, `audit-logs`, `users`, `settings`.

## 6. Forecasting Pipeline

`validate → prepare_timeseries (fill gaps, outlier flag) → feature_engineer → model_select (rules: <12 points→naive/moving-avg; seasonal & enough history→SARIMA/seasonal-decomp; intermittent demand→Croston-style; enough volume & features→GradientBoosting/RandomForest) → train+backtest (rolling-origin) → evaluate (MAE/RMSE/WAPE/bias) → pick best by WAPE → generate forecast + CI → persist`. Runs as a Celery task per SKU (or batched), status/stage rows update `forecast_jobs`.

## 7. Slotting Recommendation Algorithm

Score every (SKU × candidate eligible location) pair:
`score = w1*demand_velocity_norm + w2*(1/travel_distance_norm) + w3*capacity_fit + w4*policy_compliance − penalty(constraint_violations)`
Constraints (hard, exclude candidate if violated): capacity, weight/volume, temperature, hazard, fragility, blocked/inactive location, category restriction. Stability gate before emitting a recommendation: `expected_benefit >= min_benefit`, `confidence >= min_confidence`, `time_since_last_move >= cooldown`, else suppressed. Output always includes a human-readable `reason` built from the contributing factors (not just the score).

## 8. AuthN/AuthZ

JWT access (short-lived) + refresh token (httpOnly cookie or rotating refresh table), `bcrypt`/`argon2` password hashing, role→permission map checked via FastAPI dependency `require_permission("recommendations:approve")`. `customer_id` embedded in token claims, revalidated against DB on every request.

## 9. Background Jobs

Celery + Redis. Job row created synchronously (status=`queued`), task id linked, worker updates `stage`/`progress`/`status` as it runs; frontend polls `/jobs/{id}` every 2s while `status in (queued, running)`.

## 10. Validation Strategy

Every upload: schema check (pydantic) → type/range check → referential check (SKU/warehouse exist) → business rule check (no dup IDs, no overlapping locations, receiving/dispatch present) → report of valid/invalid rows with downloadable CSV of errors → nothing commits until validation passes.

## 11. Testing Strategy

pytest + httpx for API/integration (isolated test DB, transactional rollback per test), factory fixtures per tenant, dedicated cross-tenant-isolation test suite; Vitest + React Testing Library for frontend.

## 12. Deployment

Docker Compose services: `api`, `worker`, `beat` (optional), `db`, `redis`, `web`. `.env` per environment, Alembic migration run as an init container/entrypoint step, structured logging (JSON) to stdout for aggregation.

## 13. Phase Plan
See section 26 of the spec — implemented in this repo phase-by-phase, starting with Phase 1 below.
