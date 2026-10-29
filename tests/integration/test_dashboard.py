import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.gui import router, get_dashboard_store, InMemoryCallStore, set_report_renderer

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
    # Another test may have installed lane B's report renderer; these tests cover the local fallback
    set_report_renderer(None)
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

    def test_live_honeypot_banner_and_auto_refresh(self, client, isolated_store, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)

        # 1. Without pending scam call, banner is not present but refresh script is
        r1 = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert r1.status_code == 200
        assert 'id="live-honeypot-banner"' not in r1.text
        assert "window.location.reload()" in r1.text

        # 2. Add pending scam call
        isolated_store.add_call({
            "call_id": "call_pending_live_123",
            "status": "pending",
            "verdict": "scam",
            "caller_number": "+919876543210",
            "persona_name": "Ramesh Sharma",
            "extracted_intel": {
                "upi_ids": ["scammer@okaxis"],
                "bank_accounts": ["987654321001"],
                "ifsc_codes": ["SBIN0001234"],
                "phone_numbers": ["+919876543210"],
                "mid_call_logs": [],
            },
            "transcript": [
                {"role": "caller", "content": "Police calling, pay now."}
            ]
        })

        r2 = client.get(f"/dashboard?token={TEST_TOKEN}")
        assert r2.status_code == 200
        assert 'id="live-honeypot-banner"' in r2.text
        assert "LIVE HONEYPOT ACTIVE" in r2.text
        assert "Ramesh Sharma" in r2.text
        assert "call_pending_live_123" in r2.text
        assert "scammer@okaxis" in r2.text
        assert "987654321001" in r2.text
        assert "SBIN0001234" in r2.text

        # 3. Check detail page has isPending = true
        r3 = client.get(f"/dashboard/calls/call_pending_live_123?token={TEST_TOKEN}")
        assert r3.status_code == 200
        assert "isPending = true;" in r3.text


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
        assert "No calls handled yet" in ui_resp.text

    def test_per_call_signed_url_authorization(self, client, monkeypatch):
        import time
        from app.notify.alerts import generate_report_signature

        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        call_id = "call_scam_001"
        valid_exp = int(time.time()) + 3600
        valid_sig = generate_report_signature(call_id, valid_exp, TEST_TOKEN)

        # Access with valid per-call signature succeeds without master token
        resp = client.get(f"/dashboard/report/{call_id}?exp={valid_exp}&sig={valid_sig}")
        assert resp.status_code == 200
        assert "NATIONAL CYBERCRIME REPORTING PORTAL" in resp.text

        # Access with tampered signature is rejected
        bad_resp = client.get(f"/dashboard/report/{call_id}?exp={valid_exp}&sig=fake_signature_12")
        assert bad_resp.status_code == 401

        # Access with expired timestamp is rejected
        expired_exp = int(time.time()) - 3600
        expired_sig = generate_report_signature(call_id, expired_exp, TEST_TOKEN)
        exp_resp = client.get(f"/dashboard/report/{call_id}?exp={expired_exp}&sig={expired_sig}")
        assert exp_resp.status_code == 401

    def test_detail_page_renders_verdict_and_intel_tags(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get(f"/dashboard/calls/call_scam_001?token={TEST_TOKEN}")
        assert resp.status_code == 200
        html = resp.text
        assert "SUSPECTED SCAM" in html
        assert "UPI: cbi.officer.verma@okaxis" in html
        assert "Ph: 9876543210" in html

    def test_role_escaping_preserves_title_case_without_entity_corruption(self, client, isolated_store, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        isolated_store.add_call({
            "call_id": "call_entity_test",
            "caller_number": "+919876543210",
            "verdict": "scam",
            "duration": 60.0,
            "transcript": [
                {"role": "caller<admin>", "content": "Sample dialogue"}
            ]
        })
        resp = client.get(f"/dashboard/calls/call_entity_test?token={TEST_TOKEN}")
        assert resp.status_code == 200
        # Title of "caller<admin>" is "Caller<Admin>", which escaped should be "Caller&lt;Admin&gt;"
        # NOT "&Lt;"
        assert "&Lt;" not in resp.text
        assert "Caller&lt;Admin&gt;" in resp.text


class TestDashboardEvidenceSection:
    def test_call_detail_renders_evidence_packets_copy_buttons_and_portal_links(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        resp = client.get(f"/dashboard/calls/call_scam_001?token={TEST_TOKEN}")
        assert resp.status_code == 200
        body = resp.text

        # 1. Evidence section and packets (Chakshu + Report Suspect)
        assert "Evidence" in body
        assert "Chakshu" in body
        assert "Report Suspect" in body
        assert "Digital Arrest / Impersonation of Police or Law Enforcement" in body
        assert "cbi.officer.verma@okaxis" in body

        # 2. Copy buttons for packets/fields
        assert "btn-copy" in body
        assert "Copy" in body

        # 3. Portal links to Chakshu (sancharsaathi.gov.in) and cybercrime.gov.in
        assert "https://sancharsaathi.gov.in" in body
        assert "https://cybercrime.gov.in" in body

        # 4. Review and confirm step present on detail view
        assert "/dashboard/calls/call_scam_001/confirm" in body
        assert "Review" in body and "Confirm" in body

    def test_review_and_confirm_step_transitions_status_via_signed_link_and_session(self, client, monkeypatch):
        import time
        from app.notify.alerts import generate_report_signature

        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)
        call_id = "call_scam_001"

        # 1. Unauthenticated confirm is rejected with 401
        unauth = client.post(f"/dashboard/calls/{call_id}/confirm")
        assert unauth.status_code == 401

        # 2. Signed family link can confirm evidence and renders Confirmed by Family
        exp = int(time.time()) + 3600
        sig = generate_report_signature(call_id, exp, TEST_TOKEN)
        confirm_resp = client.post(
            f"/dashboard/calls/{call_id}/confirm?exp={exp}&sig={sig}",
            follow_redirects=True,
        )
        assert confirm_resp.status_code == 200
        assert "Confirmed by Family" in confirm_resp.text

        # 3. JSON API response on confirm verifies manual-only guarantee
        json_resp = client.post(
            f"/dashboard/calls/{call_id}/confirm?token={TEST_TOKEN}",
            headers={"Accept": "application/json"},
        )
        assert json_resp.status_code == 200
        payload = json_resp.json()
        assert payload["evidence_status"] == "confirmed_by_family"
        assert payload["confirmed_at"] is not None
        assert payload["auto_submitted"] is False


class TestScamIntelligenceView:
    def test_scam_intelligence_links_calls_sharing_same_upi_or_account(self, client, isolated_store, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TEST_TOKEN)

        # Add a second call sharing the same UPI ID (cbi.officer.verma@okaxis) and a mule bank account
        isolated_store.add_call({
            "call_id": "call_scam_002",
            "caller_number": "+919111222333",
            "verdict": "scam",
            "duration": 210.0,
            "created_at": "2026-10-18T03:00:00Z",
            "summary": "Customs parcel scam demanding deposit to same UPI handle and mule account.",
            "extracted_intel": {
                "upi_ids": ["cbi.officer.verma@okaxis"],
                "bank_accounts": ["987654321098"],
                "ifsc_codes": ["SBIN0001234"],
                "phone_numbers": [],
            },
            "transcript": [],
        })

        # Add a third call sharing the same bank account (987654321098)
        isolated_store.add_call({
            "call_id": "call_scam_003",
            "caller_number": "+919444666777",
            "verdict": "scam",
            "duration": 145.0,
            "created_at": "2026-10-19T04:00:00Z",
            "summary": "Bank KYC freeze scam using the same mule bank account.",
            "extracted_intel": {
                "upi_ids": [],
                "bank_accounts": ["987654321098"],
                "ifsc_codes": ["SBIN0001234"],
                "phone_numbers": [],
            },
            "transcript": [],
        })

        # 1. JSON API endpoint returns linked clusters for shared UPI and shared bank account
        api_resp = client.get(
            "/dashboard/api/intelligence",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert api_resp.status_code == 200
        intel_data = api_resp.json()
        clusters_by_key = {(c["kind"], c["identifier"]): c for c in intel_data["clusters"]}

        assert ("upi", "cbi.officer.verma@okaxis") in clusters_by_key
        upi_cluster = clusters_by_key[("upi", "cbi.officer.verma@okaxis")]
        assert upi_cluster["call_count"] == 2
        assert upi_cluster["linked_across_calls"] is True
        assert set(upi_cluster["call_ids"]) == {"call_scam_001", "call_scam_002"}

        assert ("account", "987654321098") in clusters_by_key
        acc_cluster = clusters_by_key[("account", "987654321098")]
        assert acc_cluster["call_count"] == 2
        assert acc_cluster["linked_across_calls"] is True
        assert set(acc_cluster["call_ids"]) == {"call_scam_002", "call_scam_003"}

        # 2. Dedicated Scam-Intelligence HTML view renders shared UPI/account clusters and links to calls
        html_resp = client.get(
            "/dashboard/intelligence",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert html_resp.status_code == 200
        page = html_resp.text
        assert "Scam Intelligence" in page
        assert "cbi.officer.verma@okaxis" in page
        assert "987654321098" in page
        assert "/dashboard/calls/call_scam_001" in page
        assert "/dashboard/calls/call_scam_002" in page
        assert "/dashboard/calls/call_scam_003" in page

        # 3. Main dashboard and call detail view surface cross-linked calls sharing the same UPI/account
        overview_resp = client.get(
            "/dashboard",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert overview_resp.status_code == 200
        assert "/dashboard/intelligence" in overview_resp.text
        assert "cbi.officer.verma@okaxis" in overview_resp.text

        detail_resp = client.get(
            "/dashboard/calls/call_scam_002",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert detail_resp.status_code == 200
        assert "/dashboard/calls/call_scam_001" in detail_resp.text
        assert "/dashboard/calls/call_scam_003" in detail_resp.text
