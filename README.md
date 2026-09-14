# Intelligent Warehouse Management & Demand-Driven Inventory Optimization Platform

All 7 phases are implemented. See `docs/ARCHITECTURE.md` for the full system design.

## What's implemented

**Phase 1 — Auth & workspaces**
- Register / login / refresh / forgot-password / reset-password, JWT access + refresh tokens, bcrypt hashing
- Multi-tenancy with strict isolation (cross-tenant reads return 404, never 403)
- RBAC: `owner`, `warehouse_manager`, `analyst`, `operator`, `viewer`
- Warehouse CRUD with duplicate-code protection and FIFO/FEFO/LIFO policy validation
- Audit logging on every write

**Phase 2 — Warehouse layout**
- Zones and storage locations: full CRUD, tenant- and warehouse-scoped
- Bulk layout upload (CSV / Excel / JSON) with row-level validation: missing required fields, invalid
  dimensions/capacities, missing receiving/dispatch points, duplicate location codes, overlapping
  locations, invalid zone references, unsupported storage/location types
- Upload never commits partial data — if any row fails validation, nothing is written, and a
  downloadable per-row error report (CSV) is returned
- Sample layout template endpoint
- Frontend: interactive SVG layout builder (click-to-place locations), drag-and-drop bulk upload with
  a live validation report, and a zones manager

**Phase 3 — SKU master, sales history, inventory**
- Customer-level SKU/product master: full CRUD + bulk upload, with fragility/hazard/rotation-policy
  validation (including a logical check that FEFO can't be required without expiry tracking)
- Per-warehouse historical sales upload: validates dates, unknown SKUs, negative quantities, and
  duplicate records (same SKU + date + order)
- Per-warehouse inventory & batch upload: validates unknown SKUs/locations, negative or inconsistent
  quantities, and invalid/contradictory dates (e.g. expiry before receiving)
- Uploaded inventory always lands as the *actual* location (or `awaiting_putaway` if unplaced) —
  this is the ground truth the slotting engine will generate recommendations against, never overwrite
- Frontend: SKU master page (list/create/upload), and a per-warehouse Sales & Inventory data page

**Phase 4 — Demand forecasting engine**
- Modular pipeline (`app/services/forecasting/`): builds a daily time series from raw sales rows
  (gap-filling missing dates with zero demand), detects outliers via IQR and winsorizes them, then
  profiles the series for trend/seasonality/intermittency
- Model selection is data-driven, not hardcoded: naive, seasonal naive, moving average, Croston's
  method (intermittent demand), exponential smoothing, Holt-Winters, SARIMA, and a lag-feature Random
  Forest are all candidates; the pipeline backtests whichever are applicable given the data and picks
  the winner by WAPE, then refits on the full series to produce the real forecast + confidence interval
- Runs as a genuine Celery background job per warehouse (all SKUs, or one), advancing the job's real
  `stage` (validating → preparing → training → evaluating → generating → saving) — no fake progress bar
- Forecast results and per-model backtest metrics (MAE, RMSE, MAPE, WAPE, bias) are persisted and
  retrievable per SKU
- Frontend: forecast dashboard — generate forecasts with a horizon control, live job-stage polling,
  a summary table (chosen model + WAPE per SKU), and a detail chart (historical vs. forecast with a
  confidence-interval band) plus a full model-comparison table

**Phase 5 — Slotting recommendation engine**
- Pure, unit-tested scoring pipeline (`app/services/slotting/`): hard constraints exclude any candidate
  location that violates capacity, temperature, hazard, fragility, or category rules; eligible candidates
  are scored on a weighted blend of demand velocity (from forecasts when available, else recent sales),
  travel distance to receiving/dispatch, capacity fit, accessibility, and rotation-policy compliance
- Every recommendation ships with plain-language reasons generated from the actual score components —
  never a bare number
- Recommendation stability (section 14): a fresh generation run never duplicates an unchanged
  recommendation, expires stale ones no longer applicable, and suppresses re-recommending inventory
  that was rejected within a cooldown window
- Runs as a genuine Celery background job per warehouse, advancing through real stages (validating →
  scoring → applying stability rules → saving)
- `requires_approval` is always `true` and nothing here ever touches `current_location` — recommendations
  are strictly advisory until Phase 6's approval workflow lands
- Frontend: recommendations page with job-stage polling and a card list per SKU showing the suggested
  move, confidence, demand classification, and the human-readable reasoning chips

**Phase 6 — Approval workflow, movement tasks, movement confirmation**
- Accept / reject / override actions on a pending recommendation, each recorded as a
  `RecommendationDecision` with who decided, when, and (for rejections) why
- Accepting or overriding creates a `MovementTask` — this step never touches the inventory record's
  actual location, confirmed live: after accepting, the inventory record was still `awaiting_putaway`
  with `current_location_id: null`
- The **only** code path that ever sets an inventory record's actual location outside of upload is
  `confirm_movement()` — verified live: confirming the movement task correctly updated
  `current_location_id` to the target bin and flipped status from `awaiting_putaway` to `in_stock`
- Movement tasks support `start` (pending → in_progress), `confirm` (→ confirmed, updates actual
  location), and `cancel` (→ cancelled, leaves actual location untouched) — all state transitions
  guarded against double-actions (e.g. accepting an already-decided recommendation returns 409)
- A rejected or overridden recommendation is fully recorded via the same audit log used everywhere else
- Frontend: recommendation cards now have Accept / Reject (with required reason) / Override (by location
  code) actions, and a new Movements page to start/confirm/cancel each task

Later phases (full dashboard/reports, onboarding wizard, user management UI) are designed in
`docs/ARCHITECTURE.md` and will be built on top of this foundation without breaking it.

**Phase 7 — Dashboard, reports, testing, deployment polish**
- Customer-wide dashboard (`GET /api/v1/dashboard`): warehouse/SKU/inventory totals, pending
  recommendations and movement tasks, and a recent-activity feed pulled from the audit log
- Per-warehouse reports (`GET /api/v1/warehouses/{id}/reports/overview`) covering every chart in
  section 17: storage utilization, demand trend, inventory by category, SKU velocity (fast/slow
  movers), stockout/overstock risk, inventory aging, expiring inventory, recommendation status
  breakdown, movement activity, and forecast coverage
- Frontend: an upgraded Dashboard page and a new Reports page with real charts (line, bar, pie) built
  on the actual aggregation data — no placeholder numbers
- Frontend test suite (Vitest + React Testing Library): login form behavior (including a real loading
  state, not a fake delay), protected-route redirect/loading/authenticated states, and the shared
  bulk-upload component's validating/error-report/success states
- Docker Compose reviewed end-to-end; two real bugs caught in that review are described below

**Honest limitations, stated plainly:**
- I do not have Docker available in the sandbox this was built in, so `docker compose up` has never
  actually been run. I reviewed every service definition and Dockerfile by hand and validated the
  compose YAML parses correctly, and I found and fixed two real bugs this way: the frontend service had
  **no Dockerfile at all** (now added, running the Vite dev server), and the proxy target environment
  variable name didn't match what `vite.config.ts` actually reads (was `VITE_API_BASE_URL`, code reads
  `VITE_API_PROXY_TARGET`) - fixed, and pointed at the Docker network hostname (`http://api:8000`)
  instead of `localhost`, which would have been wrong inside a container. You should still be the first
  to actually run it end-to-end.
- Storage utilization on the Reports page is intentionally labeled as "% of storage locations
  occupied," not weight/volume utilization - `used_capacity` isn't wired up to real quantities anywhere
  in the codebase, and I'd rather report an honest coarser number than a precise-looking fake one.
- No onboarding wizard (section 5) - registration lands straight in an empty workspace with contextual
  empty states on every page instead.
- No user-management UI - the API and RBAC support inviting/managing other users' roles, but there's no
  page for it yet.
- The Celery worker's `command:` override in `docker-compose.yml` bypasses the migration-wait logic in
  `docker-entrypoint.sh`, so on a completely fresh `docker compose up` the worker could briefly fail
  tasks before the `api` container finishes migrating. It doesn't retry (`max_retries=0`), so a job
  submitted in that exact window would need to be regenerated by the user.

## Running locally with Docker Compose (recommended)

```bash
cp backend/.env.example backend/.env
# edit backend/.env if needed (JWT_SECRET_KEY especially, for anything beyond local dev)

docker compose up --build
```

- API: http://localhost:8000 (docs at http://localhost:8000/docs)
- Frontend: http://localhost:5173
- Postgres: localhost:5432 (user/pass/db: `warehouse` / `warehouse` / `warehouse_db`)
- Redis: localhost:6379

The API container runs Alembic migrations automatically on startup before serving traffic.

## Running locally without Docker

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then point DATABASE_URL at a Postgres instance you control

alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The Vite dev server proxies `/api/*` to `http://localhost:8000` by default (configurable via
`VITE_API_PROXY_TARGET`).

## Testing

```bash
cd backend
# requires a running Postgres and a warehouse_test_db database
CELERY_TASK_ALWAYS_EAGER=true python -m pytest tests/ -v
```

`CELERY_TASK_ALWAYS_EAGER=true` makes `.delay()` run the Celery task body synchronously in-process, so
the forecasting job tests exercise the real task code without needing a live Redis broker or worker.

43 tests currently cover auth flows, warehouse CRUD, zone/location CRUD, layout upload validation,
SKU CRUD and bulk upload, sales upload validation, inventory/batch upload validation, and — importantly
— dedicated cross-tenant isolation tests and audit-log verification throughout.

54 tests total as of Phase 4, adding: forecasting pipeline unit tests (gap-filling, outlier detection,
series profiling, model selection for steady vs. intermittent demand, confidence-interval sanity), and
full API flow tests (generate → poll job → summary → detail) with Celery running in eager mode so the
real task code executes without needing a live broker.

76 tests total as of Phase 5, adding: hard-constraint unit tests (temperature/hazard/fragility/category/
capacity exclusions), scoring unit tests, engine-level tests (put-away, no-op on already-optimal
placement, relocation when justified, suppression, confidence gating), and full API flow tests including
a duplicate-prevention test that regenerates recommendations twice and confirms no duplicate is created.

85 tests total as of Phase 6, adding: accept/reject/override workflow tests, a test proving accepting a
recommendation does NOT change the actual inventory location, a test proving confirming the resulting
movement DOES change it, double-action rejection (409), reject-without-reason validation (422),
override-onto-a-blocked-location rejection, start→confirm and cancel state transitions, and tenant
isolation on both the recommendation-decision and movement endpoints.

94 tests total as of Phase 7, adding: customer and warehouse dashboard/reports aggregation tests
(storage utilization, stockout/overstock risk, expiring inventory, demand trend, category breakdown,
recommendation/movement counts) and a regression test proving inventory uploaded without a
`batch_number` still shows up in the aging report (a real bug this phase's own test suite caught and a
migration fixed - see "Honest limitations" above for the two Docker bugs caught the same way).

### Frontend tests

```bash
cd frontend
npm run test        # vitest run
```

11 tests cover: the login form (field rendering, a genuine loading state during sign-in, error display
on failure), protected-route behavior (loading/redirect/authenticated states), and the shared bulk
upload component (drop-zone rendering, in-flight validating state, validation-error report display,
success state, and request-failure handling).

For the frontend:

```bash
cd frontend
npx tsc --noEmit -p tsconfig.app.json   # type-check
npm run build                            # production build
```

## Project layout

```
backend/
  app/
    api/v1/        # routers: auth, users, warehouses, layout, skus, sales, inventory,
                    # forecasts, recommendations, movements, reports, audit-logs
    core/          # config, security (JWT/hashing), permissions
    db/            # SQLAlchemy session/base
    models/        # SQLAlchemy models
    schemas/       # Pydantic request/response schemas
    services/
      forecasting/       # time-series prep, models, metrics, pipeline (Phase 4)
      slotting/          # constraints, scoring, engine (Phase 5)
      reports.py         # dashboard/reports aggregation (Phase 7)
      recommendation_workflow.py, movement_workflow.py   # approval workflow (Phase 6)
      forecast_job_runner.py, recommendation_job_runner.py   # Celery job runners
      *_validation.py, file_parsing.py, validation_report.py   # bulk upload validation
      audit.py, tenancy.py
    tasks/         # Celery task wrappers (forecasting_tasks, slotting_tasks)
    celery_app.py  # Celery app
    main.py        # FastAPI app entrypoint
  alembic/         # migrations
  tests/           # pytest suite (94 tests)
frontend/
  src/
    components/    # AppShell, RequireAuth, form primitives, BulkUploadPanel
    hooks/         # useAuth
    lib/           # typed API client with auto token refresh
    pages/         # Login, Register, Dashboard, Warehouses, SKUs, per-warehouse
                    # Layout/Data/Forecasting/Recommendations/Movements/Reports, AuditLogs
    **/__tests__/  # Vitest + React Testing Library suite (11 tests)
docs/
  ARCHITECTURE.md  # full system design for all phases
```
