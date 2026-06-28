"""
Tests for asset relationships (create / read / delete) and the graph endpoint.
"""

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def create_asset(client, auth_headers, payload):
    resp = client.post("/api/v1/assets/", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["asset"]


def create_relation(client, auth_headers, parent_id, child_id, relation_type="parent"):
    resp = client.post(
        f"/api/v1/assets/{parent_id}/relations",
        json={"child_id": child_id, "relation_type": relation_type},
        headers=auth_headers,
    )
    return resp


# ── CREATE ────────────────────────────────────────────────────────────────────

class TestCreateRelation:
    def test_create_relation_success(self, client, auth_headers, domain_payload, subdomain_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)

        resp = create_relation(client, auth_headers, parent["id"], child["id"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["relation"]["parent_id"] == parent["id"]
        assert body["relation"]["child_id"] == child["id"]
        assert body["relation"]["relation_type"] == "parent"

    def test_create_relation_parent_not_found(self, client, auth_headers, subdomain_payload):
        child = create_asset(client, auth_headers, subdomain_payload)
        resp = create_relation(
            client, auth_headers,
            "00000000-0000-0000-0000-000000000000",
            child["id"],
        )
        assert resp.status_code == 404
        assert "parent" in resp.json()["message"].lower()

    def test_create_relation_child_not_found(self, client, auth_headers, domain_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        resp = create_relation(
            client, auth_headers,
            parent["id"],
            "00000000-0000-0000-0000-000000000000",
        )
        assert resp.status_code == 404
        assert "child" in resp.json()["message"].lower()

    def test_create_relation_requires_auth(self, client, auth_headers, domain_payload, subdomain_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)
        resp = client.post(
            f"/api/v1/assets/{parent['id']}/relations",
            json={"child_id": child["id"], "relation_type": "parent"},
        )
        assert resp.status_code == 401

    def test_create_relation_custom_type(self, client, auth_headers, domain_payload, cert_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        cert = create_asset(client, auth_headers, cert_payload)

        resp = create_relation(client, auth_headers, cert["id"], parent["id"], "covers")
        assert resp.status_code == 201
        assert resp.json()["relation"]["relation_type"] == "covers"


# ── READ ──────────────────────────────────────────────────────────────────────

class TestGetRelations:
    def test_get_relations_for_parent(self, client, auth_headers, domain_payload, subdomain_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)
        create_relation(client, auth_headers, parent["id"], child["id"])

        resp = client.get(f"/api/v1/assets/{parent['id']}/relations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 1
        assert len(body["children"]) == 1
        assert len(body["parents"]) == 0

    def test_get_relations_for_child(self, client, auth_headers, domain_payload, subdomain_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)
        create_relation(client, auth_headers, parent["id"], child["id"])

        resp = client.get(f"/api/v1/assets/{child['id']}/relations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 1
        assert len(body["parents"]) == 1
        assert len(body["children"]) == 0

    def test_get_relations_asset_not_found(self, client):
        resp = client.get("/api/v1/assets/00000000-0000-0000-0000-000000000000/relations")
        assert resp.status_code == 404

    def test_get_relations_no_relations(self, client, auth_headers, domain_payload):
        asset = create_asset(client, auth_headers, domain_payload)
        resp = client.get(f"/api/v1/assets/{asset['id']}/relations")
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0

    def test_get_relation_by_id(self, client, auth_headers, domain_payload, subdomain_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)
        rel = create_relation(client, auth_headers, parent["id"], child["id"]).json()["relation"]

        resp = client.get(f"/api/v1/assets/{parent['id']}/relations/{rel['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == rel["id"]

    def test_get_relation_by_id_not_found(self, client, auth_headers, domain_payload):
        asset = create_asset(client, auth_headers, domain_payload)
        resp = client.get(
            f"/api/v1/assets/{asset['id']}/relations/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404


# ── GRAPH ─────────────────────────────────────────────────────────────────────

class TestAssetGraph:
    def test_graph_returns_asset_with_children(
        self, client, auth_headers, domain_payload, subdomain_payload
    ):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)
        create_relation(client, auth_headers, parent["id"], child["id"])

        resp = client.get(f"/api/v1/assets/{parent['id']}/graph")
        assert resp.status_code == 200
        body = resp.json()

        assert body["asset"]["id"] == parent["id"]
        assert len(body["children"]) == 1
        assert len(body["parents"]) == 0

        child_in_graph = body["children"][0]
        # Full asset object — not just a UUID
        assert child_in_graph["asset"]["id"] == child["id"]
        assert child_in_graph["asset"]["value"] == "api.example.com"
        assert child_in_graph["relation_type"] == "parent"

    def test_graph_returns_asset_with_parents(
        self, client, auth_headers, domain_payload, subdomain_payload
    ):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)
        create_relation(client, auth_headers, parent["id"], child["id"])

        resp = client.get(f"/api/v1/assets/{child['id']}/graph")
        assert resp.status_code == 200
        body = resp.json()

        assert body["asset"]["id"] == child["id"]
        assert len(body["parents"]) == 1
        assert len(body["children"]) == 0
        assert body["parents"][0]["asset"]["id"] == parent["id"]

    def test_graph_no_relations(self, client, auth_headers, domain_payload):
        asset = create_asset(client, auth_headers, domain_payload)
        resp = client.get(f"/api/v1/assets/{asset['id']}/graph")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asset"]["id"] == asset["id"]
        assert body["parents"] == []
        assert body["children"] == []

    def test_graph_asset_not_found(self, client):
        resp = client.get("/api/v1/assets/00000000-0000-0000-0000-000000000000/graph")
        assert resp.status_code == 404

    def test_graph_multiple_children(
        self, client, auth_headers, domain_payload, subdomain_payload, cert_payload
    ):
        parent = create_asset(client, auth_headers, domain_payload)
        child1 = create_asset(client, auth_headers, subdomain_payload)
        child2 = create_asset(client, auth_headers, cert_payload)
        create_relation(client, auth_headers, parent["id"], child1["id"])
        create_relation(client, auth_headers, parent["id"], child2["id"], "covers")

        resp = client.get(f"/api/v1/assets/{parent['id']}/graph")
        assert resp.status_code == 200
        assert len(resp.json()["children"]) == 2


# ── DELETE ────────────────────────────────────────────────────────────────────

class TestDeleteRelation:
    def test_delete_relation(self, client, auth_headers, domain_payload, subdomain_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)
        rel = create_relation(client, auth_headers, parent["id"], child["id"]).json()["relation"]

        resp = client.delete(
            f"/api/v1/assets/{parent['id']}/relations/{rel['id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # Verify it's gone
        after = client.get(f"/api/v1/assets/{parent['id']}/relations").json()
        assert after["total_count"] == 0

    def test_delete_relation_not_found(self, client, auth_headers, domain_payload):
        asset = create_asset(client, auth_headers, domain_payload)
        resp = client.delete(
            f"/api/v1/assets/{asset['id']}/relations/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_delete_relation_requires_auth(self, client, auth_headers, domain_payload, subdomain_payload):
        parent = create_asset(client, auth_headers, domain_payload)
        child = create_asset(client, auth_headers, subdomain_payload)
        rel = create_relation(client, auth_headers, parent["id"], child["id"]).json()["relation"]

        resp = client.delete(f"/api/v1/assets/{parent['id']}/relations/{rel['id']}")
        assert resp.status_code == 401
