"""
Shared pytest fixtures for all tests.

A fresh test engine is created once per session (scope="session").
After every individual test, all table rows are deleted so tests stay isolated
without the overhead of recreating the schema each time.

Set TEST_DATABASE_URL in your environment (or .env) to point at a dedicated
test database. Defaults to the same DB as the app (safe because rows are
cleaned up after every test).
"""

import os
import pytest
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


# ── engine (one per test session) ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_engine():
    """Create the test engine and ensure all tables exist."""
    url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://darkatlas:darkatlas@localhost:5433/darkatlas_test",
    )
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


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
