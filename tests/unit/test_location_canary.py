import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.voice.location import (
    update_caller_number_location,
    set_claimed_location,
    record_canary_trap_hit,
    get_call_location_profile,
)
from app.voice.telecom_circles import lookup_telecom_circle


def test_telecom_circle_lookup():
    res = lookup_telecom_circle("+917019941295")
    assert res is not None
    assert res["circle_code"] == "KA"
    assert res["circle_name"] == "Karnataka"
    assert "Airtel" in res["carrier"]

    res_dl = lookup_telecom_circle("9711223344")
    assert res_dl is not None
    assert res_dl["circle_code"] == "DL"
    assert "Delhi" in res_dl["circle_name"]


def test_location_triangulation_mismatch():
    cid = "test-call-triangulation"
    update_caller_number_location(cid, "+917019941295")  # Karnataka
    set_claimed_location(cid, "Mumbai SBI Head Office")    # Mumbai

    prof = get_call_location_profile(cid)
    assert prof["triangulation_mismatch"] is True
    assert "Karnataka" in prof["mismatch_summary"]


@pytest.mark.asyncio
async def test_canary_receipt_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET canary page
        resp = await client.get("/receipt/test-canary-call-1")
        assert resp.status_code == 200
        assert "SBI e-Payment Verification" in resp.text
        assert "test-canary-call-1" in resp.text

        # POST telemetry
        telemetry = {
            "call_id": "test-canary-call-1",
            "lat": 12.9716,
            "lng": 77.5946,
            "accuracy": 12.5,
            "user_agent": "Mozilla/5.0 Test",
        }
        post_resp = await client.post("/api/canary/telemetry", json=telemetry)
        assert post_resp.status_code == 200
        data = post_resp.json()
        assert data["status"] == "logged"

        # GET location summary
        loc_resp = await client.get("/api/calls/test-canary-call-1/location")
        assert loc_resp.status_code == 200
        loc_data = loc_resp.json()
        assert loc_data["canary_opened"] is True
        assert loc_data["canary_gps"]["lat"] == 12.9716
