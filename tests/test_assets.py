"""
Tests for asset CRUD, filtering, sorting, and pagination.
"""

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def create_asset(client, auth_headers, payload):
    """POST /assets and assert 201."""
    resp = client.post("/api/v1/assets/", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["asset"]


# ── CREATE ────────────────────────────────────────────────────────────────────

class TestCreateAsset:
    def test_create_asset_success(self, client, auth_headers, domain_payload):
        resp = client.post("/api/v1/assets/", json=domain_payload, headers=auth_headers)
        assert resp.status_code == 201
        asset = resp.json()["asset"]
        assert asset["type"] == "domain"
        assert asset["value"] == "example.com"
        assert asset["status"] == "active"
        assert "id" in asset
        assert asset["first_seen"] is not None
        assert asset["last_seen"] is not None

    def test_create_asset_requires_api_key(self, client, domain_payload):
        resp = client.post("/api/v1/assets/", json=domain_payload)
        assert resp.status_code == 401

    def test_create_asset_wrong_api_key(self, client, domain_payload):
        resp = client.post("/api/v1/assets/", json=domain_payload, headers={"X-API-Key": "wrong"})
        assert resp.status_code == 403

    def test_create_asset_invalid_type(self, client, auth_headers):
        resp = client.post(
            "/api/v1/assets/",
            json={"type": "not_a_type", "value": "x.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_asset_missing_required_fields(self, client, auth_headers):
        resp = client.post("/api/v1/assets/", json={"type": "domain"}, headers=auth_headers)
        assert resp.status_code == 422

    def test_create_asset_default_status_is_active(self, client, auth_headers):
        resp = client.post(
            "/api/v1/assets/",
            json={"type": "domain", "value": "test.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["asset"]["status"] == "active"


# ── READ ──────────────────────────────────────────────────────────────────────

class TestGetAsset:
    def test_get_asset_by_id(self, client, auth_headers, domain_payload):
        created = create_asset(client, auth_headers, domain_payload)
        resp = client.get(f"/api/v1/assets/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["value"] == "example.com"

    def test_get_asset_not_found(self, client):
        resp = client.get("/api/v1/assets/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_list_assets_empty(self, client):
        resp = client.get("/api/v1/assets/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0
        assert data["assets"] == []

    def test_list_assets_returns_created(self, client, auth_headers, domain_payload):
        create_asset(client, auth_headers, domain_payload)
        resp = client.get("/api/v1/assets/")
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 1


# ── FILTERING ─────────────────────────────────────────────────────────────────

class TestFiltering:
    def _seed(self, client, auth_headers):
        """Create domain + subdomain + certificate for filter tests."""
        create_asset(client, auth_headers, {"type": "domain", "value": "example.com", "tags": ["root"], "source": "scan"})
        create_asset(client, auth_headers, {"type": "subdomain", "value": "api.example.com", "tags": ["prod"], "source": "scan"})
        create_asset(client, auth_headers, {"type": "certificate", "value": "CN=api.example.com", "tags": [], "source": "ct-log"})

    def test_filter_by_type(self, client, auth_headers):
        self._seed(client, auth_headers)
        resp = client.get("/api/v1/assets/", params={"type": "domain"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["assets"][0]["type"] == "domain"

    def test_filter_by_status(self, client, auth_headers):
        self._seed(client, auth_headers)
        resp = client.get("/api/v1/assets/", params={"status": "active"})
        assert resp.json()["total_count"] == 3

        resp = client.get("/api/v1/assets/", params={"status": "stale"})
        assert resp.json()["total_count"] == 0

    def test_filter_by_tag(self, client, auth_headers):
        self._seed(client, auth_headers)
        resp = client.get("/api/v1/assets/", params={"tag": "prod"})
        assert resp.status_code == 200
        assets = resp.json()["assets"]
        assert len(assets) == 1
        assert "prod" in assets[0]["tags"]

    def test_filter_by_value_contains(self, client, auth_headers):
        self._seed(client, auth_headers)
        resp = client.get("/api/v1/assets/", params={"value_contains": "api."})
        assert resp.status_code == 200
        # subdomain and certificate both contain "api."
        assert resp.json()["total_count"] == 2

    def test_filter_by_source(self, client, auth_headers):
        self._seed(client, auth_headers)
        resp = client.get("/api/v1/assets/", params={"source": "ct-log"})
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 1
        assert resp.json()["assets"][0]["type"] == "certificate"

    def test_filter_combined(self, client, auth_headers):
        self._seed(client, auth_headers)
        resp = client.get("/api/v1/assets/", params={"type": "subdomain", "tag": "prod"})
        assert resp.json()["total_count"] == 1


# ── SORTING ───────────────────────────────────────────────────────────────────

class TestSorting:
    def _seed(self, client, auth_headers):
        create_asset(client, auth_headers, {"type": "domain", "value": "aaa.com"})
        create_asset(client, auth_headers, {"type": "domain", "value": "zzz.com"})

    def test_sort_by_value_asc(self, client, auth_headers):
        self._seed(client, auth_headers)
        resp = client.get("/api/v1/assets/", params={"sort_by": "value", "sort_order": "asc"})
        values = [a["value"] for a in resp.json()["assets"]]
        assert values == sorted(values)

    def test_sort_by_value_desc(self, client, auth_headers):
        self._seed(client, auth_headers)
        resp = client.get("/api/v1/assets/", params={"sort_by": "value", "sort_order": "desc"})
        values = [a["value"] for a in resp.json()["assets"]]
        assert values == sorted(values, reverse=True)


# ── PAGINATION ────────────────────────────────────────────────────────────────

class TestPagination:
    def _seed(self, client, auth_headers, n=5):
        for i in range(n):
            create_asset(client, auth_headers, {"type": "domain", "value": f"domain{i}.com"})

    def test_pagination_page_size(self, client, auth_headers):
        self._seed(client, auth_headers, n=5)
        resp = client.get("/api/v1/assets/", params={"page": 1, "page_size": 2})
        data = resp.json()
        assert data["total_count"] == 5
        assert data["assets_count"] == 2

    def test_pagination_last_page(self, client, auth_headers):
        self._seed(client, auth_headers, n=5)
        resp = client.get("/api/v1/assets/", params={"page": 3, "page_size": 2})
        data = resp.json()
        assert data["total_count"] == 5
        assert data["assets_count"] == 1  # only 1 left on last page

    def test_pagination_beyond_last_page(self, client, auth_headers):
        self._seed(client, auth_headers, n=3)
        resp = client.get("/api/v1/assets/", params={"page": 99, "page_size": 10})
        data = resp.json()
        assert data["total_count"] == 3
        assert data["assets_count"] == 0
        assert data["assets"] == []

    def test_pagination_invalid_page(self, client):
        resp = client.get("/api/v1/assets/", params={"page": 0})
        assert resp.status_code == 422


# ── UPDATE ────────────────────────────────────────────────────────────────────

class TestUpdateAsset:
    def test_update_asset(self, client, auth_headers, domain_payload):
        created = create_asset(client, auth_headers, domain_payload)
        resp = client.put(
            f"/api/v1/assets/{created['id']}",
            json={"type": "domain", "value": "updated.com", "tags": ["updated"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["asset"]["value"] == "updated.com"

    def test_update_asset_not_found(self, client, auth_headers):
        resp = client.put(
            "/api/v1/assets/00000000-0000-0000-0000-000000000000",
            json={"type": "domain", "value": "x.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_update_requires_auth(self, client, domain_payload, auth_headers):
        created = create_asset(client, auth_headers, domain_payload)
        resp = client.put(
            f"/api/v1/assets/{created['id']}",
            json={"type": "domain", "value": "x.com"},
        )
        assert resp.status_code == 401

    def test_update_preserves_first_seen(self, client, auth_headers, domain_payload):
        created = create_asset(client, auth_headers, domain_payload)
        first_seen_before = created["first_seen"]

        client.put(
            f"/api/v1/assets/{created['id']}",
            json={"type": "domain", "value": "example.com", "tags": ["changed"]},
            headers=auth_headers,
        )
        resp = client.get(f"/api/v1/assets/{created['id']}")
        assert resp.json()["first_seen"] == first_seen_before


# ── DELETE ────────────────────────────────────────────────────────────────────

class TestDeleteAsset:
    def test_delete_asset(self, client, auth_headers, domain_payload):
        created = create_asset(client, auth_headers, domain_payload)
        resp = client.delete(f"/api/v1/assets/{created['id']}", headers=auth_headers)
        assert resp.status_code == 200
        # Verify it's gone
        assert client.get(f"/api/v1/assets/{created['id']}").status_code == 404

    def test_delete_asset_not_found(self, client, auth_headers):
        resp = client.delete(
            "/api/v1/assets/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_delete_requires_auth(self, client, auth_headers, domain_payload):
        created = create_asset(client, auth_headers, domain_payload)
        resp = client.delete(f"/api/v1/assets/{created['id']}")
        assert resp.status_code == 401
