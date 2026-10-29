"""
tests/integration/test_family_verification_loop.py - Autonomous Anti-Kidnap Family Verification Loop Tests.
"""

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.voice.store import init_db, set_db_path, get_call_record
from app.voice.family_loop import _FAMILY_VERIFICATION_STATE


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    test_db = str(tmp_path / "test_family_loop.db")
    set_db_path(test_db)
    init_db(test_db)
    _FAMILY_VERIFICATION_STATE.clear()
    yield
    set_db_path(None)
    _FAMILY_VERIFICATION_STATE.clear()


def test_classify_caller_triggers_pending_family_verification():
    client = TestClient(app)
    call_id = "call_kidnap_001"

    # classify_caller with kidnap summary
    resp = client.post(
        "/tools/classify_caller",
        json={
            "call_id": call_id,
            "caller_summary": "Claims my son Amit was caught stealing in shop, tied up and demanding ransom",
            "caller_number": "+919876543210",
        },
    )
    assert resp.status_code == 200

    # Call record should exist with family_verification_status = 'PENDING'
    rec = get_call_record(call_id)
    assert rec is not None
    assert rec["family_verification_status"] == "PENDING"
    assert rec["family_verified_at"] is None


def test_verify_son_safe_1click_endpoint():
    client = TestClient(app)
    call_id = "call_kidnap_002"

    # Trigger kidnap classification
    client.post(
        "/tools/classify_caller",
        json={
            "call_id": call_id,
            "caller_summary": "Police arrest extortion: says Amit in custody",
            "caller_number": "+919876543210",
        },
    )

    # 1-Click stage demo confirmation
    resp = client.post(f"/api/calls/{call_id}/verify_son_safe")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["family_verification_status"] == "CONFIRMED_SAFE"
    assert data["verified_at"] is not None

    # DB verified
    rec = get_call_record(call_id)
    assert rec["family_verification_status"] == "CONFIRMED_SAFE"
    assert rec["family_verified_at"] is not None


def test_inbound_webhook_family_verify_json_and_form():
    client = TestClient(app)
    call_id = "call_kidnap_003"

    # Trigger kidnap classification
    client.post(
        "/tools/classify_caller",
        json={
            "call_id": call_id,
            "caller_summary": "Accident in hospital, need urgent money for Amit",
            "caller_number": "+919876543210",
        },
    )

    # Inbound JSON webhook from Amit's WhatsApp
    resp = client.post(
        "/webhooks/family_verify",
        json={"call_id": call_id, "status": "SAFE", "from_number": "+919876543210"},
    )
    assert resp.status_code == 200
    assert resp.json()["family_verification_status"] == "CONFIRMED_SAFE"

    # Verify mid-call context injection on switch_to_honeypot
    switch_resp = client.post(
        "/tools/switch_to_honeypot",
        json={"call_id": call_id, "language": "hi", "persona_id": "ramesh"},
    )
    assert switch_resp.status_code == 200
    switch_data = switch_resp.json()
    assert "Amit just confirmed" in switch_data.get("system_intel", "")
    assert "100% SAFE" in switch_data.get("system_intel", "")


def test_mid_call_intel_injection_on_log_intel():
    client = TestClient(app)
    call_id = "call_kidnap_004"

    # Trigger kidnap
    client.post(
        "/tools/classify_caller",
        json={
            "call_id": call_id,
            "caller_summary": "Extortion kidnap: son Amit captive",
        },
    )

    # Confirm son safe
    client.post(f"/api/calls/{call_id}/verify_son_safe")

    # Scammer gives UPI mid-call
    intel_resp = client.post(
        "/tools/log_intel",
        json={
            "call_id": call_id,
            "kind": "upi",
            "value_raw": "ransom99@oksbi",
            "elicitation": "initial_ask",
        },
    )
    assert intel_resp.status_code == 200
    intel_data = intel_resp.json()
    assert "Amit just confirmed" in intel_data.get("system_intel", "")
    assert "Pune office" in intel_data.get("system_intel", "")
