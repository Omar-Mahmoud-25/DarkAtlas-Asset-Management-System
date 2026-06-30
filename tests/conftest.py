"""
Shared pytest fixtures for all tests.

A fresh test engine is created once per session (scope="session").
After every individual test, all table rows are deleted so tests stay isolated
without the overhead of recreating the schema each time.

The test database is created automatically if it does not exist, and Alembic
migrations are applied so the schema always matches the real application.
No manual setup is required — just run ``pytest``.

Set TEST_DATABASE_URL in your environment (or .env) to point at a dedicated
test database.
"""

import os
import pytest
from urllib.parse import urlparse, urlunparse
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session
from starlette.testclient import TestClient

# ── env / config ──────────────────────────────────────────────────────────────
# Must be set BEFORE importing the app so that pydantic-settings picks up the
# test API key when Config() is first instantiated.
TEST_API_KEY = os.environ.get("API_KEY", "test-super-secret-key")
os.environ["API_KEY"] = TEST_API_KEY

from main import app  # noqa: E402  (import after env is set)
from src.core.database import get_db_session  # noqa: E402
from src.models.assets import Asset, AssetRelation  # noqa: E402  (registers metadata)


# ── helpers: auto-create test DB & run migrations ─────────────────────────────

def _ensure_test_db_exists(test_db_url: str) -> None:
    """Connect to the default 'postgres' database and CREATE the test DB if it
    does not already exist."""
    parsed = urlparse(test_db_url)
    test_db_name = parsed.path.lstrip("/")

    # Connect to the maintenance database (always exists in PostgreSQL)
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :db"),
            {"db": test_db_name},
        ).fetchone()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))

    admin_engine.dispose()


def _run_migrations(test_db_url: str) -> None:
    """Run ``alembic upgrade head`` against the test database."""
    from alembic.config import Config as AlembicConfig
    from alembic import command

    alembic_cfg = AlembicConfig("alembic.ini")

    # Temporarily override DATABASE_URL so that alembic/env.py (which calls
    # get_config()) picks up the test URL instead of the production one.
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_db_url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if original_db_url is not None:
            os.environ["DATABASE_URL"] = original_db_url
        else:
            os.environ.pop("DATABASE_URL", None)


# ── engine (one per test session) ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_engine():
    """Auto-create the test database, apply migrations, and yield the engine."""
    url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://darkatlas:darkatlas@localhost:5433/darkatlas_test",
    )
    _ensure_test_db_exists(url)
    _run_migrations(url)

    engine = create_engine(url)
    yield engine
    engine.dispose()


# ── per-test table cleanup ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_tables(test_engine):
    """Delete all rows from every table after each test (fast isolation)."""
    yield
    with Session(test_engine) as session:
        # Delete in dependency order so FK constraints are not violated.
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()


# ── TestClient (re-created per test so dependency overrides are fresh) ─────────

@pytest.fixture()
def client(test_engine):
    """FastAPI TestClient that uses the test database session."""
    def override_get_db():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── convenience helpers ────────────────────────────────────────────────────────

@pytest.fixture()
def auth_headers():
    """Headers required for write-protected endpoints."""
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def domain_payload():
    return {
        "type": "domain",
        "value": "example.com",
        "source": "scan",
        "tags": ["root"],
        "metadata": {},
    }


@pytest.fixture()
def subdomain_payload():
    return {
        "type": "subdomain",
        "value": "api.example.com",
        "source": "scan",
        "tags": ["prod"],
        "metadata": {},
    }


@pytest.fixture()
def cert_payload():
    return {
        "type": "certificate",
        "value": "CN=api.example.com",
        "source": "scan",
        "tags": [],
        "metadata": {"issuer": "Let's Encrypt", "expires": "2025-01-02"},
    }
