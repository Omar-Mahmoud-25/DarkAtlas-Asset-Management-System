"""
Tests for deduplication behaviour.

The spec requires:
- Importing the same asset twice must NOT create a duplicate — it should
  update last_seen and merge metadata/tags.
- first_seen must be set on creation and never overwritten.
- A stale/archived asset that re-appears must return to active.
"""

import time
import pytest


def create_asset(client, auth_headers, payload):
    resp = client.post("/api/v1/assets/", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["asset"]


def get_asset(client, asset_id):
    resp = client.get(f"/api/v1/assets/{asset_id}")
    assert resp.status_code == 200
    return resp.json()


class TestDeduplication:
    """Creating an asset with the same (type, value) must upsert, not insert."""

    def test_same_asset_twice_no_duplicate(self, client, auth_headers, domain_payload):
        create_asset(client, auth_headers, domain_payload)
        create_asset(client, auth_headers, domain_payload)

        resp = client.get("/api/v1/assets/", params={"type": "domain"})
        assert resp.json()["total_count"] == 1

    def test_second_import_returns_updated_message(self, client, auth_headers, domain_payload):
        create_asset(client, auth_headers, domain_payload)
        resp = client.post("/api/v1/assets/", json=domain_payload, headers=auth_headers)
        assert resp.status_code == 201
        assert "updated" in resp.json()["message"].lower()

    def test_first_import_returns_created_message(self, client, auth_headers, domain_payload):
        resp = client.post("/api/v1/assets/", json=domain_payload, headers=auth_headers)
        assert "created" in resp.json()["message"].lower()

    def test_tags_are_merged_on_dedup(self, client, auth_headers):
        create_asset(client, auth_headers, {"type": "domain", "value": "merge.com", "tags": ["a"]})
        second = create_asset(client, auth_headers, {"type": "domain", "value": "merge.com", "tags": ["b"]})

        assert set(second["tags"]) == {"a", "b"}

    def test_tags_are_not_duplicated(self, client, auth_headers):
        create_asset(client, auth_headers, {"type": "domain", "value": "merge.com", "tags": ["a"]})
        second = create_asset(client, auth_headers, {"type": "domain", "value": "merge.com", "tags": ["a"]})

        assert second["tags"].count("a") == 1

    def test_metadata_is_merged_on_dedup(self, client, auth_headers):
        create_asset(client, auth_headers, {
            "type": "certificate", "value": "CN=test.com",
            "metadata": {"issuer": "Let's Encrypt"},
        })
        second = create_asset(client, auth_headers, {
            "type": "certificate", "value": "CN=test.com",
            "metadata": {"expires": "2026-01-01"},
        })
        # Both keys should be present after merge
        assert second["metadata"]["issuer"] == "Let's Encrypt"
        assert second["metadata"]["expires"] == "2026-01-01"

    def test_metadata_newer_value_wins_on_conflict(self, client, auth_headers):
        """When the same metadata key appears in both, the newer import wins."""
        create_asset(client, auth_headers, {
            "type": "certificate", "value": "CN=test.com",
            "metadata": {"expires": "2024-01-01"},
        })
        second = create_asset(client, auth_headers, {
            "type": "certificate", "value": "CN=test.com",
            "metadata": {"expires": "2026-01-01"},
        })
        assert second["metadata"]["expires"] == "2026-01-01"

    def test_different_type_same_value_is_not_a_duplicate(self, client, auth_headers):
        """(type, value) is the dedup key — different type = different asset."""
        create_asset(client, auth_headers, {"type": "domain", "value": "example.com"})
        create_asset(client, auth_headers, {"type": "subdomain", "value": "example.com"})

        resp = client.get("/api/v1/assets/")
        assert resp.json()["total_count"] == 2


class TestLifecycleDates:
    """first_seen is set once; last_seen is bumped on every re-sighting."""

    def test_first_seen_set_on_creation(self, client, auth_headers, domain_payload):
        asset = create_asset(client, auth_headers, domain_payload)
        assert asset["first_seen"] is not None

    def test_first_seen_preserved_on_reimport(self, client, auth_headers, domain_payload):
        first = create_asset(client, auth_headers, domain_payload)
        first_seen_original = first["first_seen"]

        time.sleep(0.05)  # ensure clock ticks
        second = create_asset(client, auth_headers, domain_payload)

        assert second["first_seen"] == first_seen_original

    def test_last_seen_updated_on_reimport(self, client, auth_headers, domain_payload):
        first = create_asset(client, auth_headers, domain_payload)
        last_seen_original = first["last_seen"]

        time.sleep(0.05)
        second = create_asset(client, auth_headers, domain_payload)

        assert second["last_seen"] >= last_seen_original


class TestReappearingAsset:
    """A stale or archived asset that is re-imported must return to active."""

    def _mark_status(self, client, auth_headers, asset_id, status):
        resp = client.patch(
            f"/api/v1/assets/{asset_id}/status",
            params={"status": status},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_stale_asset_becomes_active_on_reimport(self, client, auth_headers, domain_payload):
        asset = create_asset(client, auth_headers, domain_payload)
        self._mark_status(client, auth_headers, asset["id"], "stale")

        # Verify it is stale
        assert get_asset(client, asset["id"])["status"] == "stale"

        # Re-import the same asset
        create_asset(client, auth_headers, domain_payload)

        # Must be active again
        assert get_asset(client, asset["id"])["status"] == "active"

    def test_archived_asset_becomes_active_on_reimport(self, client, auth_headers, domain_payload):
        asset = create_asset(client, auth_headers, domain_payload)
        self._mark_status(client, auth_headers, asset["id"], "archived")

        assert get_asset(client, asset["id"])["status"] == "archived"

        create_asset(client, auth_headers, domain_payload)

        assert get_asset(client, asset["id"])["status"] == "active"
