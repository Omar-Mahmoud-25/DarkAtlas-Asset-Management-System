# DarkAtlas Asset Management System

A RESTful Attack Surface Management (ASM) API built with **FastAPI + PostgreSQL**.  
Tracks digital assets (domains, subdomains, IPs, certificates, services, technologies),
manages their lifecycle, models relationships between them, and enforces deduplication on every import.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Environment Variables](#2-environment-variables)
3. [How to Run](#3-how-to-run)
4. [Database Migrations](#4-database-migrations)
5. [API Overview](#5-api-overview)
6. [Authentication](#6-authentication)
7. [Running the Tests](#7-running-the-tests)
8. [Design Decisions & Assumptions](#8-design-decisions--assumptions)
9. [Edge Cases Handled](#9-edge-cases-handled)
10. [Project Structure](#10-project-structure)

---

## 1. Quick Start

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd darkatlas-asset-management

# 2. Copy and fill in the environment file
cp .env.example .env
# Edit .env — at minimum set API_KEY to a random secret string

# 3. Start the API + PostgreSQL with a single command
docker compose up --build
```

The API will be available at **http://localhost:8000**.  
Interactive API docs (Swagger UI): **http://localhost:8000/docs**  
Alternative docs (ReDoc): **http://localhost:8000/redoc**

---

## 2. Environment Variables

Copy `.env.example` to `.env` and set the values below.

| Variable | Required | Default | Description |
|---|---|---|---|
| `API_KEY` | ✅ Yes | — | Secret key sent in the `X-API-Key` header for write operations |
| `POSTGRES_USER` | No | `darkatlas` | PostgreSQL username |
| `POSTGRES_PASSWORD` | No | `darkatlas` | PostgreSQL password |
| `POSTGRES_DB` | No | `darkatlas` | PostgreSQL database name |
| `POSTGRES_PORT` | No | `5433` | PostgreSQL port |
| `DATABASE_URL` | No | auto-built | Full SQLAlchemy URL — overrides the individual PG vars if set |
| `STALE_ASSET_DAYS_INTERVAL` | No | `30.0` | Days of inactivity before an asset is auto-marked stale. Accepts floats (e.g. `0.01` for testing) |
| `STALE_JOB_INTERVAL_HOURS` | No | `24.0` | How often the background staleness job runs (hours) |
| `TEST_DATABASE_URL` | No | same as `DATABASE_URL` | Database used by the test suite. Rows are cleaned after every test, so sharing the main DB is safe locally |

> **Security note**: Never commit `.env` to version control. Use `.env.example` as the template.

---

## 3. How to Run
### With Docker (recommended)
```bash
docker compose up --build
```

### Without Docker
```bash
# Install dependencies (Python 3.10+)
pip install -r requirements.txt

# Make sure PostgreSQL is running and .env is configured, then:
uvicorn main:app --reload
```

---

## 4. Database Migrations

Migrations are managed with **Alembic**.

```bash
# Apply all migrations (run this after docker compose up if not using entrypoint.sh)
alembic upgrade head

# Create a new migration after changing models
alembic revision --autogenerate -m "describe your change"
```

The `entrypoint.sh` in the Docker image runs `alembic upgrade head` automatically before starting the server.

---

## 5. API Documentation

Once the server is running, the full interactive API docs are available at:

| URL | Interface |
|---|---|
| **http://localhost:8000/docs** | Swagger UI — try endpoints directly in the browser |
| **http://localhost:8000/redoc** | ReDoc — clean read-only reference |
| **http://localhost:8000/openapi.json** | Raw OpenAPI 3.x schema |

All endpoints, request bodies, query parameters, response schemas, and error codes are documented there automatically by FastAPI.

---

## 6. Authentication


Write operations (`POST`, `PUT`, `PATCH`, `DELETE`) require an API key passed in the request header:

```
X-API-Key: <your-api-key>
```

Read operations (`GET`) are public and require no authentication.

Generate a secure key with:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 7. Running the Tests

The test suite uses **pytest** + **Starlette TestClient** against a real PostgreSQL database.  
Tables are created once per session and rows are cleaned up after every individual test.

```bash
# Make sure PostgreSQL is running (docker compose up -d db)

# Run all tests
pytest

# Run a specific file
pytest tests/test_deduplication.py

# Run a specific test class
pytest tests/test_bulk_import.py::TestBulkImportIdempotency

# Run with output for failing tests
pytest -v --tb=long
```

The test suite covers:

| File | What is tested |
|---|---|
| `test_assets.py` | CRUD, filtering (type / status / tag / value / source / combined), sorting, pagination, auth |
| `test_deduplication.py` | No duplicate on re-import, tag merge, metadata merge, `first_seen` preserved, `last_seen` bumped, stale/archived asset returns to active |
| `test_relationships.py` | Create / list / delete relations, graph endpoint with full asset hydration, error cases, auth |
| `test_bulk_import.py` | Basic import, idempotency (re-import 3×), malformed records skipped gracefully, relation creation from `parent`/`covers` fields, post-import graph |

**Total: 77 tests.**

---

## 8. Design Decisions & Assumptions

### Deduplication key
`(type, value)` is the unique key for an asset. Two assets with the same value but different types (e.g. `domain: example.com` vs `subdomain: example.com`) are treated as distinct assets.

### Merge strategy on re-import
When an asset is re-imported:
- `status` is forced to `active` (re-appearing asset returns to active regardless of incoming payload).
- `tags` are merged with set-union (no duplicates).
- `metadata` is shallow-merged; the newer import's values win on key conflicts.
- `first_seen` is **never** overwritten.
- `last_seen` is always updated to `now()`.
- `source` is **not** overwritten on re-import — the original (first-seen) source is preserved. Assumption: the first source that discovered the asset is the authoritative one.

### Status lifecycle
```
(creation / re-import) → active
active → stale    (via PATCH /status or background job)
stale  → active   (via re-import or PATCH /status)
any    → archived  (via PATCH /status — permanent soft-delete)
```

### Background staleness job
On startup, a background scheduler (APScheduler) runs every `STALE_JOB_INTERVAL_HOURS` hours and marks any `active` asset whose `last_seen` is older than `STALE_ASSET_DAYS_INTERVAL` days as `stale`. The threshold accepts floats for easy testing (e.g. `STALE_ASSET_DAYS_INTERVAL=0.001`).

### Bulk import — two-pass strategy
**Pass 1**: Validate and upsert every asset record. Invalid records are collected as errors and skipped without halting the batch.  
**Pass 2**: Resolve `parent` and `covers` fields into actual DB relations, using the batch-local `id` → DB UUID map built in Pass 1. Relations that already exist are skipped (idempotent).

### Relationship model
Relationships are stored as directed edges: `(parent_id, child_id, relation_type)`. The `relation_type` is a free-form string to accommodate domain-specific semantics (`parent`, `covers`, etc.). There is no uniqueness constraint on the edge itself beyond an application-level check in `relation_exists()`. Assumption: duplicate relations are prevented at the service layer, not the DB layer, to keep the schema simple.

### `/bulk` route ordering
`POST /api/v1/assets/bulk` is declared **before** `/{asset_id}` parameterised routes to prevent FastAPI from matching the literal string `"bulk"` as an asset ID.

### API key authentication
A single shared API key protects all write endpoints. This is intentional per the spec ("Lightweight authentication — API key or JWT on write operations"). The key is read from the `API_KEY` environment variable on every request (no caching) so it can be rotated without a restart.

### Soft vs hard delete
`DELETE /assets/{id}` is a hard delete. For audit-trail preservation, mark assets `archived` via `PATCH /assets/{id}/status` instead.

### Pagination defaults
Default page size is 20, maximum is 200. All list endpoints are paginated — there is no "return everything" shortcut to prevent accidental large payloads on big inventories.

---

## 9. Edge Cases Handled

| Edge case | Handling |
|---|---|
| Importing the same dataset twice | Idempotent — assets are upserted, relations are skipped if they already exist |
| Conflicting metadata from two sources | Shallow merge; newer import's values win |
| Stale asset re-imported | Forced back to `active` regardless of incoming `status` field |
| Malformed / missing fields in bulk import | Record is skipped and error logged; rest of batch continues |
| `parent` / `covers` referring to a batch ID that failed validation | Error logged in pass 2; successfully imported assets are unaffected |
| Large inventories | Pagination with sane defaults (20 / max 200) on all list endpoints |
| Expired vs expiring-soon certificates | `metadata.expires` is stored as-is; downstream filtering by date can be done via `value_contains` or the LangChain risk scoring feature (bonus) |
| Re-appearing archived assets | Same logic as stale — forced to `active` on re-import |

---

## 10. Project Structure

```
.
├── main.py                      # FastAPI app entry point, router registration, lifespan
├── alembic/                     # Database migrations
│   └── versions/
├── src/
│   ├── core/
│   │   ├── auth.py              # API key authentication dependency
│   │   ├── config.py            # Pydantic-settings configuration
│   │   └── database.py          # SQLModel engine & session factory
│   ├── models/
│   │   ├── assets.py            # Asset & AssetRelation SQLModel table models
│   │   ├── enums.py             # AssetType & AssetStatus enums
│   │   └── schema.py            # Pydantic request/response schemas
│   ├── repositories/
│   │   ├── assets_repository.py       # DB queries for assets
│   │   └── relationships_repository.py # DB queries for relations
│   ├── routes/
│   │   ├── asset_router.py            # Asset CRUD + bulk + status endpoints
│   │   └── relationships_router.py    # Relation CRUD + graph endpoint
│   └── services/
│       ├── assets_service.py          # Asset business logic (dedup, merge, lifecycle)
│       └── relationships_service.py   # Relationship business logic + graph resolution
├── tests/
│   ├── conftest.py              # Shared fixtures: engine, TestClient, cleanup
│   ├── test_assets.py           # CRUD, filtering, sorting, pagination tests
│   ├── test_deduplication.py    # Dedup, merge, lifecycle date tests
│   ├── test_relationships.py    # Relation and graph endpoint tests
│   └── test_bulk_import.py      # Bulk import edge case tests
├── docker-compose.yml
├── Dockerfile
├── pytest.ini
├── requirements.txt
└── .env.example
```
