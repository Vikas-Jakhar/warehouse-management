import socket
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://warehouse:warehouse@localhost:5432/warehouse_db"
    TEST_DATABASE_URL: str = "postgresql+psycopg2://warehouse:warehouse@localhost:5432/warehouse_test_db"

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if not isinstance(v, str):
            return v

        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+psycopg2://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
            v = v.replace("postgresql://", "postgresql+psycopg2://", 1)

        try:
            parsed = urlparse(v)
            host = parsed.hostname
            # If hostname is a Render internal host (starts with dpg- without domain),
            # check if it resolves internally. If not, fallback to external region FQDN.
            if host and host.startswith("dpg-") and "." not in host:
                can_resolve = False
                try:
                    socket.getaddrinfo(host, 5432)
                    can_resolve = True
                except Exception:
                    can_resolve = False

                if not can_resolve:
                    for reg in ["oregon", "frankfurt", "ohio", "singapore", "virginia"]:
                        candidate = f"{host}.{reg}-postgres.render.com"
                        try:
                            socket.getaddrinfo(candidate, 5432)
                            netloc = parsed.netloc.replace(host, candidate)
                            query = parsed.query
                            if "sslmode=" not in query:
                                query = (query + "&sslmode=require").lstrip("&")
                            v = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, query, parsed.fragment))
                            break
                        except Exception:
                            continue
        except Exception:
            pass

        return v

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    # When true, .delay() runs the task body synchronously in-process instead
    # of dispatching to a broker/worker. Used in tests so the real Celery
    # task code path is exercised without needing a running worker.
    CELERY_TASK_ALWAYS_EAGER: bool = False

    JWT_SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:5173"
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
