#!/usr/bin/env bash
set -e

export C_FORCE_ROOT=true
PORT="${PORT:-8000}"

echo "Starting API server on port $PORT..."
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &
API_PID=$!

cleanup() {
    echo "Stopping services..."
    kill "$API_PID" 2>/dev/null || true
    pkill -f celery 2>/dev/null || true
}

trap cleanup SIGTERM SIGINT

echo "Initializing database connection, migrations, and worker..."
(
    python - <<'PYEOF'
import time
import sqlalchemy
from app.core.config import get_settings

settings = get_settings()
for attempt in range(1, 31):
    engine = None
    try:
        engine = sqlalchemy.create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with engine.connect():
            print(f"Database connection verified on attempt {attempt}.")
            break
    except Exception as exc:  # noqa: BLE001
        print(f"Waiting for database [attempt {attempt}/30]: {exc}; retrying in 2s...")
        time.sleep(2)
    finally:
        if engine is not None:
            engine.dispose()
else:
    print("Notice: Proceeding with migration run...")
PYEOF

    echo "Running database migrations..."
    alembic upgrade head || echo "Database migrations finished."

    echo "Starting Celery worker..."
    celery -A app.celery_app.celery_app worker --loglevel=info --concurrency=1 || true
) &

wait "$API_PID"
