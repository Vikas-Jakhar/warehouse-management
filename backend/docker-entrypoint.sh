#!/usr/bin/env bash
set -e

echo "Waiting for database..."
python - <<'PYEOF'
import time
import sqlalchemy
from app.core.config import get_settings

settings = get_settings()
for attempt in range(30):
    try:
        engine = sqlalchemy.create_engine(settings.DATABASE_URL)
        with engine.connect():
            print("Database is ready.")
            break
    except Exception as exc:  # noqa: BLE001
        print(f"DB not ready yet ({exc}); retrying...")
        time.sleep(2)
else:
    raise SystemExit("Database never became available")
PYEOF

echo "Running migrations..."
alembic upgrade head

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
