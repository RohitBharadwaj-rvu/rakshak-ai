"""
tests/integration/test_approve_legitimate_caller.py - Live Legitimate Delivery Warm Pass-Through Tests.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.voice.store import init_db, set_db_path, get_call_record


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    test_db = str(tmp_path / "test_delivery.db")
    set_db_path(test_db)
    init_db(test_db)
    yield
    set_db_path(None)


def test_approve_legitimate_delivery_partner():
    client = TestClient(app)
    call_id = "call_blinkit_101"

    resp = client.post(
        "/tools/approve_legitimate_caller",
        json={
            "call_id": call_id,
            "caller_type": "delivery",
            "brand_or_person": "Blinkit",
            "delivery_details": "Standing at Gate 2 with grocery bag, asking to leave with guard",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["approved"] is True
    assert data["call_id"] == call_id
    assert "गेट के गार्ड को बोल देता हूँ" in data["spoken_instruction"]

    # Verify SQLite verdict updated to safe_delivery
    rec = get_call_record(call_id)
    assert rec is not None
    assert rec["verdict"] == "safe_delivery"


def test_reject_delivery_with_scam_otp_indicator():
    client = TestClient(app)
    call_id = "call_scam_delivery_102"

    resp = client.post(
        "/tools/approve_legitimate_caller",
        json={
            "call_id": call_id,
            "caller_type": "courier",
            "brand_or_person": "BlueDart",
            "delivery_details": "Parcel arrived, please tell me the 6 digit OTP on your phone to release it",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["approved"] is False
    assert "OTP" in data["reason"] or "scam indicator" in data["reason"].lower()
    assert "फर्जी" in data["spoken_instruction"]


def test_reject_delivery_with_upi_fee_demand():
    client = TestClient(app)
    call_id = "call_scam_fee_103"

    resp = client.post(
        "/tools/approve_legitimate_caller",
        json={
            "call_id": call_id,
            "caller_type": "delivery",
            "brand_or_person": "Amazon",
            "delivery_details": "Need 50 rupees delivery fee payment via UPI before coming up",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["approved"] is False
    assert "पैसे" in data["spoken_instruction"] or "ओटीपी" in data["spoken_instruction"]
