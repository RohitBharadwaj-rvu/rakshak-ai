"""
tests/integration/test_ifsc_and_syndicate_graph.py - Real-Time Razorpay IFSC Call-Out & Cross-Call Syndicate Graph Tests.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.voice.store import init_db, set_db_path, list_mule_identifiers


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    test_db = str(tmp_path / "test_syndicate.db")
    set_db_path(test_db)
    init_db(test_db)
    yield
    set_db_path(None)


def test_ifsc_geographical_callout_resolution():
    client = TestClient(app)
    call_id = "call_ifsc_001"

    # Log Jamtara / Koderma SBI IFSC
    resp = client.post(
        "/tools/log_intel",
        json={
            "call_id": call_id,
            "kind": "ifsc",
            "value_raw": "SBIN0004821",
            "elicitation": "ifsc_request",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "ifsc"
    assert data["bank_name"] == "State Bank of India"
    assert data["bank_city"] == "Koderma"
    assert data["bank_state"] == "Jharkhand"
    assert "Koderma" in data["spoken_hint"]
    assert "Jharkhand" in data["spoken_hint"]


def test_cross_call_mule_tracking_and_syndicate_match():
    client = TestClient(app)
    call1 = "call_mule_alpha"
    call2 = "call_mule_beta"
    shared_upi = "scam_network_mule@ybl"

    # Call 1 logs UPI
    r1 = client.post(
        "/tools/log_intel",
        json={
            "call_id": call1,
            "kind": "upi",
            "value_raw": shared_upi,
        },
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["syndicate_match"] is False

    # Call 2 logs SAME UPI
    r2 = client.post(
        "/tools/log_intel",
        json={
            "call_id": call2,
            "kind": "upi",
            "value_raw": shared_upi,
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["syndicate_match"] is True
    assert call1 in d2["linked_call_ids"]
    assert call2 in d2["linked_call_ids"]

    # Check mule_identifiers in DB
    mules = list_mule_identifiers()
    assert len(mules) >= 1
    mule = next(m for m in mules if m["identifier_value"] == shared_upi)
    assert mule["hit_count"] == 2
    assert call1 in mule["linked_call_ids"]
    assert call2 in mule["linked_call_ids"]


def test_syndicate_graph_api():
    client = TestClient(app)
    call1 = "call_syn_1"
    call2 = "call_syn_2"
    mule_upi = "syndicate_lead@paytm"

    client.post(
        "/tools/log_intel",
        json={"call_id": call1, "kind": "upi", "value_raw": mule_upi},
    )
    client.post(
        "/tools/log_intel",
        json={"call_id": call2, "kind": "upi", "value_raw": mule_upi},
    )

    resp = client.get("/api/syndicate/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert "syndicates" in data
    assert "repeat_mules" in data
    assert data["total_mules_tracked"] >= 1
    assert data["total_repeat_mules"] >= 1
    assert any(m["identifier_value"] == mule_upi for m in data["repeat_mules"])
