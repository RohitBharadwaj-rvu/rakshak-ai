import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dashboard.router import router, get_dashboard_store, InMemoryCallStore

TEST_TOKEN = "test_family_secret_token_123"

@pytest.fixture
def test_app():
    app = FastAPI(title="GuardianLine Dashboard Test")
    app.include_router(router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


@pytest.fixture
def populated_store():
    store = get_dashboard_store()
    store.clear()
    store.add_call({
        "call_id": "call_scam_001",
        "caller_number": "+919876543210",
        "verdict": "scam",
        "duration": 184.5,
        "timestamp": "2026-10-17T01:15:00Z",
        "summary": "Digital arrest scam pretending to be CBI Mumbai.",
        "extracted_intel": {
            "upi_ids": ["cbi.officer.verma@okaxis"],
            "bank_accounts": [],
            "ifsc_codes": [],
            "phone_numbers": ["9876543210"],
        },
        "transcript": [
            {"role": "caller", "content": "Police department se बोल रहा हूँ।"},
            {"role": "assistant", "content": "हाँ बेटा, क्या बात है?"}
        ]
    })
    return store


class TestDashboardAuthentication:
    def test_dashboard_ui_without_token_returns_401(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 401
        assert "Unauthorized" in resp.json()["detail"]

    def test_dashboard_ui_with_invalid_token_returns_401(self, client):
        resp = client.get("/dashboard?token=wrong_token")
        assert resp.status_code == 401

    def test_dashboard_ui_with_valid_token_query_returns_200(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_ui_with_valid_bearer_header_returns_200(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get("/dashboard", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestDashboardApiAndListings:
    def test_api_calls_lists_fixture_by_caller_number_and_verdict(self, client, populated_store, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get("/dashboard/api/calls", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        record = data[0]
        assert record["caller_number"] == "+919876543210"
        assert record["verdict"] == "scam"
        assert "cbi.officer.verma@okaxis" in record["extracted_intel"]["upi_ids"]

    def test_api_call_detail_returns_transcript_and_intel(self, client, populated_store, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get("/dashboard/api/calls/call_scam_001", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["call_id"] == "call_scam_001"
        assert len(detail["transcript"]) == 2
        assert detail["extracted_intel"]["upi_ids"] == ["cbi.officer.verma@okaxis"]

    def test_unknown_call_id_returns_404(self, client, populated_store, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get("/dashboard/api/calls/call_nonexistent", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 404

    def test_empty_state_handling(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        store = get_dashboard_store()
        store.clear()  # Zero calls
        resp = client.get("/dashboard/api/calls", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 200
        assert resp.json() == []

        # HTML page also renders without crash in empty state
        ui_resp = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert ui_resp.status_code == 200
        assert "No suspicious calls intercepted yet" in ui_resp.text


class TestMobileResponsivenessConstraints:
    def test_html_includes_viewport_and_mobile_responsive_css(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert resp.status_code == 200
        html = resp.text
        # Responsive viewport meta tag
        assert '<meta name="viewport" content="width=device-width, initial-scale=1.0"' in html
        # No sideways scroll (overflow-x hidden and responsive max-width)
        assert "overflow-x: hidden" in html
        assert "max-width: 100%" in html
        assert "360px" in html or "@media" in html
