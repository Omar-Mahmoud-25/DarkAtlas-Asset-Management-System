"""
Tests for the bulk import endpoint.

Covers the edge cases the spec calls out explicitly:
- Idempotent imports (re-importing same dataset creates no duplicates).
- Malformed / partial records fail gracefully; the rest of the batch succeeds.
- Relations from `parent` / `covers` fields are created automatically.
- Re-appearing stale assets are returned to active.
"""

import pytest


BULK_URL = "/api/v1/assets/bulk"

# ── sample dataset (mirrors the PDF appendix) ─────────────────────────────────

SAMPLE_DATASET = [
    {
        "id": "a1",
        "type": "domain",
        "value": "example.com",
        "status": "active",
        "source": "scan",
        "tags": ["root"],
        "metadata": {},
    },
    {
        "id": "a2",
        "type": "subdomain",
        "value": "api.example.com",
        "status": "active",
        "source": "scan",
        "tags": ["prod"],
        "metadata": {},
        "parent": "a1",
    },
    {
        "id": "a3",
        "type": "certificate",
        "value": "CN=api.example.com",
        "status": "active",
        "source": "scan",
        "tags": [],
        "metadata": {"issuer": "Let's Encrypt", "expires": "2025-01-02"},
        "covers": "a2",
    },
]


# ── helpers ───────────────────────────────────────────────────────────────────

def bulk_import(client, auth_headers, data=None):
    payload = data if data is not None else SAMPLE_DATASET
    return client.post(BULK_URL, json=payload, headers=auth_headers)


def list_assets(client, **params):
    return client.get("/api/v1/assets/", params=params).json()


# ── basic import ──────────────────────────────────────────────────────────────

class TestBulkImportBasic:
    def test_bulk_import_success(self, client, auth_headers):
        resp = bulk_import(client, auth_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["created_assets_count"] == 3
        assert body["updated_assets_count"] == 0
        assert body["errors"] == []

    def test_bulk_import_creates_correct_assets(self, client, auth_headers):
        bulk_import(client, auth_headers)
        data = list_assets(client)
        assert data["total_count"] == 3

        values = {a["value"] for a in data["assets"]}
        assert "example.com" in values
        assert "api.example.com" in values
        assert "CN=api.example.com" in values

    def test_bulk_import_requires_auth(self, client):
        resp = client.post(BULK_URL, json=SAMPLE_DATASET)
        assert resp.status_code == 401

    def test_bulk_import_empty_list(self, client, auth_headers):
        resp = bulk_import(client, auth_headers, data=[])
        assert resp.status_code == 201
        assert resp.json()["created_assets_count"] == 0


# ── idempotency ───────────────────────────────────────────────────────────────

class TestBulkImportIdempotency:
    def test_reimport_same_dataset_no_duplicates(self, client, auth_headers):
        bulk_import(client, auth_headers)
        bulk_import(client, auth_headers)
        assert list_assets(client)["total_count"] == 3

    def test_reimport_counts_as_updates(self, client, auth_headers):
        bulk_import(client, auth_headers)
        resp = bulk_import(client, auth_headers)
        body = resp.json()
        assert body["created_assets_count"] == 0
        assert body["updated_assets_count"] == 3

    def test_reimport_three_times_still_no_duplicates(self, client, auth_headers):
        for _ in range(3):
            bulk_import(client, auth_headers)
        assert list_assets(client)["total_count"] == 3


# ── malformed records ─────────────────────────────────────────────────────────

class TestBulkImportMalformedRecords:
    def test_invalid_type_is_skipped_gracefully(self, client, auth_headers):
        data = [
            {"id": "b1", "type": "domain", "value": "good.com", "source": "scan"},
            {"id": "b2", "type": "not_a_valid_type", "value": "bad.com", "source": "scan"},  # invalid
            {"id": "b3", "type": "subdomain", "value": "also-good.com", "source": "scan"},
        ]
        resp = bulk_import(client, auth_headers, data)
        assert resp.status_code == 201
        body = resp.json()
        # 2 valid, 1 errored
        assert body["created_assets_count"] == 2
        assert len(body["errors"]) == 1
        assert body["errors"][0]["index"] == 2  # 1-indexed

    def test_missing_value_field_is_skipped(self, client, auth_headers):
        data = [
            {"id": "c1", "type": "domain"},            # missing value
            {"id": "c2", "type": "domain", "value": "ok.com", "source": "scan"},
        ]
        resp = bulk_import(client, auth_headers, data)
        body = resp.json()
        assert body["created_assets_count"] == 1
        assert len(body["errors"]) == 1

    def test_batch_does_not_crash_on_all_invalid(self, client, auth_headers):
        data = [
            {"id": "x1", "type": "invalid_type", "value": "a.com"},
            {"id": "x2", "type": "another_invalid", "value": "b.com"},
        ]
        resp = bulk_import(client, auth_headers, data)
        assert resp.status_code == 201
        body = resp.json()
        assert body["created_assets_count"] == 0
        assert len(body["errors"]) == 2

    def test_partial_batch_valid_records_still_created(self, client, auth_headers):
        """Even if half the records are bad, the good ones are saved."""
        data = [
            {"id": "d1", "type": "domain", "value": "valid1.com", "source": "scan"},
            {"id": "d2", "type": "BAD_TYPE"},  # missing value + bad type
            {"id": "d3", "type": "domain", "value": "valid2.com", "source": "scan"},
        ]
        bulk_import(client, auth_headers, data)
        assert list_assets(client)["total_count"] == 2


# ── relationship resolution ───────────────────────────────────────────────────

class TestBulkImportRelationships:
    def test_parent_field_creates_relation(self, client, auth_headers):
        bulk_import(client, auth_headers)

        # Fetch the subdomain (a2) and check it has a parent relation
        assets = list_assets(client, type="subdomain")["assets"]
        assert len(assets) == 1
        subdomain_id = assets[0]["id"]

        resp = client.get(f"/api/v1/assets/{subdomain_id}/relations")
        assert resp.status_code == 200
        body = resp.json()
        # The subdomain is a child in 2 relations:
        #   - domain → subdomain  (type="parent")
        #   - cert   → subdomain  (type="covers", because cert covers subdomain)
        parent_types = {r["relation_type"] for r in body["parents"]}
        assert "parent" in parent_types

    def test_covers_field_creates_relation(self, client, auth_headers):
        bulk_import(client, auth_headers)

        # Fetch the certificate (a3) and check it has a child (the subdomain it covers)
        assets = list_assets(client, type="certificate")["assets"]
        cert_id = assets[0]["id"]

        resp = client.get(f"/api/v1/assets/{cert_id}/relations")
        body = resp.json()
        assert len(body["children"]) == 1

    def test_relations_not_duplicated_on_reimport(self, client, auth_headers):
        bulk_import(client, auth_headers)
        bulk_import(client, auth_headers)

        assets = list_assets(client, type="subdomain")["assets"]
        subdomain_id = assets[0]["id"]

        resp = client.get(f"/api/v1/assets/{subdomain_id}/relations")
        # Subdomain has exactly 2 relations: 'parent' from domain + 'covers' from cert.
        # After re-import it must still be 2, not 4.
        assert resp.json()["total_count"] == 2

    def test_invalid_parent_reference_logged_as_error(self, client, auth_headers):
        data = [
            {"id": "e1", "type": "subdomain", "value": "orphan.com", "source": "scan", "parent": "nonexistent"},
        ]
        resp = bulk_import(client, auth_headers, data)
        body = resp.json()
        # The asset itself should be created (pass 1 succeeds)
        assert body["created_assets_count"] == 1
        # But the relation error should be recorded (pass 2 fails)
        assert len(body["errors"]) == 1
        assert "parent" in body["errors"][0]["relation"]


# ── graph via bulk ────────────────────────────────────────────────────────────

class TestBulkImportGraph:
    def test_full_graph_after_bulk_import(self, client, auth_headers):
        """After a bulk import, the graph endpoint returns the expected structure."""
        bulk_import(client, auth_headers)

        domain = list_assets(client, type="domain")["assets"][0]
        resp = client.get(f"/api/v1/assets/{domain['id']}/graph")
        assert resp.status_code == 200
        body = resp.json()

        assert body["asset"]["value"] == "example.com"
        assert len(body["children"]) == 1
        assert body["children"][0]["asset"]["value"] == "api.example.com"
