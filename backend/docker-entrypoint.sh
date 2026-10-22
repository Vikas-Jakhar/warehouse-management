#!/usr/bin/env bash
set -e

echo "Waiting for database..."
python - <<'PYEOF'
import time
import sqlalchemy
from app.core.config import get_settings

settings = get_settings()
max_attempts = 60  # 60 * 5s = 5 minutes
for attempt in range(1, max_attempts + 1):
    engine = None
    try:
        engine = sqlalchemy.create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with engine.connect():
            print(f"Database connection verified successfully on attempt {attempt}.")
            break
    except Exception as exc:  # noqa: BLE001
        print(f"Waiting for database to become available [attempt {attempt}/{max_attempts}]: {exc}; retrying in 5s...")
        time.sleep(5)
    finally:
        if engine is not None:
            engine.dispose()
else:
    raise SystemExit("Database never became available within 5 minutes")
PYEOF

echo "Running migrations..."
alembic upgrade head

PORT="${PORT:-8000}"

echo "Starting Celery worker..."
celery -A app.celery_app.celery_app worker --loglevel=info --concurrency=1 &
CELERY_PID=$!

echo "Starting API server on port $PORT..."
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &
API_PID=$!

cleanup() {
    echo "Stopping services..."
    kill "$CELERY_PID" "$API_PID" 2>/dev/null || true
}

trap cleanup SIGTERM SIGINT

wait -n "$CELERY_PID" "$API_PID"