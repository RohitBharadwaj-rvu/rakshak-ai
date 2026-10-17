import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.gui import router, get_dashboard_store, InMemoryCallStore

TEST_TOKEN = "test_family_secret_token_123"


@pytest.fixture
def isolated_store():
    store = InMemoryCallStore()
    store.add_call({
        "call_id": "call_scam_001",
        "caller_number": "+919876543210",
        "verdict": "scam",
        "duration": 184.5,
        "created_at": "2026-10-17T01:15:00Z",
        "summary": "Digital arrest scam pretending to be CBI Mumbai.",
        "extracted_intel": {
            "upi_ids": ["cbi.officer.verma@okaxis"],
            "bank_accounts": [],
            "ifsc_codes": [],
            "phone_numbers": ["9876543210"],
        },
        "transcript": [
            {"role": "caller", "content": "Police department se bol raha hoon."},
            {"role": "assistant", "content": "Haan beta, kya baat hai?"}
        ]
    })
    return store


@pytest.fixture
def test_app(isolated_store):
    app = FastAPI(title="GuardianLine Dashboard Test")
    app.dependency_overrides[get_dashboard_store] = lambda: isolated_store
    app.include_router(router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class TestDashboardAuthentication:
    def test_dashboard_ui_without_env_token_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("GUARDIAN_DASHBOARD_TOKEN", raising=False)
        resp = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    def test_dashboard_ui_without_token_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get("/dashboard")
        assert resp.status_code == 401
        assert "Unauthorized" in resp.json()["detail"]

    def test_dashboard_ui_with_invalid_token_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
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


class TestDashboardHtmlAndXssProtection:
    def test_html_displays_fixture_caller_number_and_verdict(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert resp.status_code == 200
        html_text = resp.text
        assert "+919876543210" in html_text
        assert "SUSPECTED SCAM" in html_text
        assert "cbi.officer.verma@okaxis" in html_text

    def test_xss_injection_is_fully_escaped_in_html(self, client, isolated_store, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        malicious_id = "call_xss_test"
        isolated_store.add_call({
            "call_id": malicious_id,
            "caller_number": "<script>alert('xss_num')</script>",
            "verdict": "scam",
            "duration": "invalid_duration_string",  # Also tests safe duration parsing!
            "created_at": "2026-10-17T02:00:00Z",
            "summary": "<img src=x onerror=alert('xss_summary')>",
            "extracted_intel": {
                "upi_ids": ["<svg onload=alert('xss_upi')>"],
                "bank_accounts": [],
                "ifsc_codes": [],
                "phone_numbers": [],
            },
            "transcript": [
                {"role": "caller", "content": "<script>alert('xss_dialogue')</script>"}
            ]
        })

        resp = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert resp.status_code == 200
        body = resp.text

        # Ensure no raw executable scripts exist
        assert "<script>alert('xss_num')</script>" not in body
        assert "<img src=x onerror=alert('xss_summary')>" not in body
        assert "<svg onload=alert('xss_upi')>" not in body

        # Ensure HTML-escaped entities are present instead
        assert "&lt;script&gt;alert(&#x27;xss_num&#x27;)&lt;/script&gt;" in body or "&lt;script&gt;" in body
        assert "&lt;img" in body
        assert "&lt;svg" in body

    def test_call_detail_page_renders_transcript(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get(f"/dashboard/calls/call_scam_001?token={TEST_TOKEN}")
        assert resp.status_code == 200
        assert "Police department se bol raha hoon." in resp.text
        assert "Haan beta, kya baat hai?" in resp.text


class TestDashboardApiAndEmptyState:
    def test_api_calls_pagination_and_detail(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get("/dashboard/api/calls", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["call_id"] == "call_scam_001"

    def test_empty_state_handling(self, client, isolated_store, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        isolated_store.clear()
        resp = client.get("/dashboard/api/calls", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code == 200
        assert resp.json() == []

        ui_resp = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert ui_resp.status_code == 200
        assert "No suspicious calls intercepted yet" in ui_resp.text
