from unittest.mock import patch
import pytest
import src.services.risk_service

@pytest.fixture
def mock_ollama_base_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

class TestRiskScoring:
    def test_get_risk_no_api_key(self, client, auth_headers, domain_payload, monkeypatch):
        # Ensure base URL is missing/empty
        monkeypatch.setenv("OLLAMA_BASE_URL", "")
        
        # Create an asset
        resp = client.post("/api/v1/assets/", json=domain_payload, headers=auth_headers)
        asset_id = resp.json()["asset"]["id"]
        
        # Request risk scoring
        resp = client.get(f"/api/v1/assets/{asset_id}/risk")
        assert resp.status_code == 503
        assert "disabled" in resp.json()["message"].lower()

    @patch("src.services.risk_service.RiskService.evaluate_asset_risk")
    def test_get_risk_success_mocked(self, mock_eval, client, auth_headers, domain_payload):
        # Create an asset
        resp = client.post("/api/v1/assets/", json=domain_payload, headers=auth_headers)
        asset_id = resp.json()["asset"]["id"]

        # Mock the service response to avoid hitting Ollama API
        mock_eval.return_value = {
            "score": 85,
            "summary": "High risk due to exposed ports."
        }
        
        # Request risk scoring
        resp = client.get(f"/api/v1/assets/{asset_id}/risk")
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 85
        assert "exposed ports" in data["summary"]

    def test_get_risk_asset_not_found(self, client, mock_ollama_base_url):
        resp = client.get("/api/v1/assets/00000000-0000-0000-0000-000000000000/risk")
        assert resp.status_code == 404
