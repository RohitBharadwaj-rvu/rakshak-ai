"""
tests/integration/test_webhook.py - Webhook, CallRecord Store & `call.finalized` Suite (T-HOOK).

Verifies:
  - Each of the 6 fixtures produces exactly one CallRecord with every required field
    and accurately extracts planted UPI IDs / accounts / IFSCs / phone numbers
  - The same payload delivered twice still makes one record, and `call.finalized` fires once
  - `log_intel` captures that arrived before the webhook are merged into the record
  - A malformed payload gets a 400, is logged with its call ID, and the server keeps running
  - A missing caller number keeps the record, with `caller_number` left empty and `caller_number_missing=True`
  - A 60-minute transcript answers in under 1 s, and the record is final within 60 s
  - If the LLM cleanup is down, the record is saved with rule-based intel and marked 'cleanup_pending'
"""

import glob
import json
import os
import sys
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.main import app
from app.voice.store import (
    clear_call_finalized_events,
    get_call_finalized_events,
    get_call_record,
    list_call_records,
    set_db_path,
)
from app.voice.webhook import set_cleanup_hook

FIXTURES_DIR = os.path.join(ROOT_DIR, "tests", "fixtures")


@pytest.fixture()
def client():
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_db_path(db_file)
    clear_call_finalized_events()
    set_cleanup_hook(None)
    test_client = TestClient(app)
    yield test_client
    set_cleanup_hook(None)
    set_db_path(None)
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except OSError:
            pass


def test_all_6_fixtures_produce_exact_call_records_and_planted_intel(client):
    fixture_files = sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json")))
    assert len(fixture_files) == 6

    for fpath in fixture_files:
        with open(fpath, "r", encoding="utf-8") as f:
            payload = json.load(f)

        res = client.post("/webhook", json=payload)
        assert res.status_code == 200
        rec = res.json()
        assert rec["call_id"] == payload["call_id"]
        assert rec["status"] == "finalized"

        planted = payload.get("metadata", {}).get("planted_intel", {})
        if "upi_id" in planted:
            assert planted["upi_id"] in rec["extracted_intel"]["upi_ids"]
        if "phone_number" in planted:
            assert planted["phone_number"] in rec["extracted_intel"]["phone_numbers"]
        if "account_number" in planted:
            assert planted["account_number"] in rec["extracted_intel"]["bank_accounts"]
        if "ifsc_code" in planted:
            assert planted["ifsc_code"] in rec["extracted_intel"]["ifsc_codes"]

    all_records = list_call_records(limit=50)
    assert len(all_records) == 6
    assert len(get_call_finalized_events()) == 6


def test_duplicate_webhook_delivery_creates_one_record_and_fires_once(client):
    fpath = os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json")
    with open(fpath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    r1 = client.post("/webhook", json=payload)
    r2 = client.post("/webhook", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200

    records = list_call_records()
    assert len(records) == 1
    events = get_call_finalized_events(payload["call_id"])
    assert len(events) == 1


def test_pre_webhook_log_intel_merges_into_final_record(client):
    call_id = "call_pre_log_001"
    client.post(
        "/tools/log_intel",
        json={
            "call_id": call_id,
            "type": "ifsc",
            "value_as_heard": "S B I N zero zero zero nine nine आठ आठ",
        },
    )

    payload = {
        "call_id": call_id,
        "agent_id": "bolna_agent_guardianline_v0",
        "caller_number": "+919876543210",
        "call_duration": 90.0,
        "call_status": "completed",
        "transcript": [
            {"role": "user", "content": "Send money to ramesh.scam@okaxis immediately."}
        ],
    }
    res = client.post("/webhook", json=payload)
    assert res.status_code == 200
    rec = res.json()
    assert "SBIN0009988" in rec["extracted_intel"]["ifsc_codes"]
    assert "ramesh.scam@okaxis" in rec["extracted_intel"]["upi_ids"]


def test_malformed_payload_returns_400_and_server_keeps_running(client):
    # 1. Invalid JSON
    r_bad_json = client.post(
        "/webhook",
        content=b"{not_valid_json",
        headers={"Content-Type": "application/json"},
    )
    assert r_bad_json.status_code == 400

    # 2. Missing required fields (with call_id present so it is logged & returned)
    r_missing = client.post("/webhook", json={"call_id": "bad_call_99", "agent_id": "a1"})
    assert r_missing.status_code == 400
    assert r_missing.json()["call_id"] == "bad_call_99"

    # 3. Server remains healthy
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"


def test_missing_caller_number_sets_flag(client):
    fpath = os.path.join(FIXTURES_DIR, "06_early_hangup.json")
    with open(fpath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    res = client.post("/webhook", json=payload)
    assert res.status_code == 200
    rec = res.json()
    assert rec["caller_number"] == ""
    assert rec["caller_number_missing"] is True


def test_60_minute_transcript_answers_under_1s(client):
    # 60-minute call (~360 turns)
    turns = []
    for i in range(180):
        turns.append(
            {
                "role": "user",
                "content": "सुनिए तुरंत पचास हज़ार रुपये cbi dot officer at the rate ok axis पर भेजिए।",
                "timestamp": float(i * 20),
            }
        )
        turns.append(
            {
                "role": "assistant",
                "content": "बेटा ज़रा धीरे बोलो, मैं डायरी में लिख रहा हूँ।",
                "timestamp": float(i * 20 + 10),
            }
        )

    payload = {
        "call_id": "call_60min_stress",
        "agent_id": "bolna_agent_guardianline_v0",
        "caller_number": "+919876543210",
        "call_duration": 3600.0,
        "call_status": "completed",
        "transcript": turns,
    }
    t0 = time.perf_counter()
    res = client.post("/webhook", json=payload)
    elapsed_s = time.perf_counter() - t0

    assert res.status_code == 200
    assert elapsed_s < 1.0, f"60-minute webhook took {elapsed_s:.3f}s (bar: < 1.0s)"
    rec = get_call_record("call_60min_stress")
    assert rec is not None
    assert rec["status"] == "finalized"
    assert "cbi.officer@okaxis" in rec["extracted_intel"]["upi_ids"]


def test_llm_cleanup_down_marks_record_cleanup_pending_with_rule_based_intel(client):
    def broken_cleanup(_ctx):
        raise ConnectionError("Mistral LLM cleanup service unreachable")

    set_cleanup_hook(broken_cleanup)

    fpath = os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json")
    with open(fpath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    res = client.post("/webhook", json=payload)
    assert res.status_code == 200
    rec = res.json()
    assert rec["status"] == "cleanup_pending"
    assert "cbi.officer.verma@okaxis" in rec["extracted_intel"]["upi_ids"]
    assert "9876543210" in rec["extracted_intel"]["phone_numbers"]


def test_real_bolna_webhook_payload_exact_json(client):
    from jsonschema import validate

    schema_path = os.path.join(ROOT_DIR, "contracts", "webhook.schema.json")
    with open(schema_path, "r", encoding="utf-8") as sf:
        webhook_schema = json.load(sf)

    real_bolna_payload = {
        "id": "bolna-exec-9f8e7d6c-5b4a-3210",
        "agent_id": "2840f8c1-77a2-4d3b-9c12-112233445566",
        "batch_id": None,
        "conversation_time": 94.2,
        "conversation_duration": 94.2,
        "status": "completed",
        "user_number": "+919820112233",
        "agent_number": "+918035737000",
        "created_at": "2026-10-17T09:15:00Z",
        "updated_at": "2026-10-17T09:16:34Z",
        "transcript": (
            "assistant: हैलो जी?\n"
            "user: मैं CBI क्राइम ब्रांच मुंबई से बोल रहा हूँ, आप डिजिटल अरेस्ट पर हैं। तुरंत cbi dot verma at the rate ok axis पर पैसे भेजो।\n"
            "assistant: अरे बाप रे! बेटा ज़रा धीरे बोलो, मैं लिख रहा हूँ।\n"
            "user: मेरा नंबर नौ आठ सात छह पाँच चार तीन दो एक शून्य है, तुरंत भेजो।"
        ),
        "telephony_data": {
            "duration": "95",
            "to_number": "+918035737000",
            "from_number": "+919820112233",
            "recording_url": "https://media.plivo.com/v1/Account/MAXX/Recording/rec-9f8e7d6c.mp3",
            "hosted_telephony": True,
            "provider_call_id": "plivo-call-uuid-99887766",
            "call_type": "inbound",
            "provider": "plivo",
            "hangup_by": "Caller",
            "hangup_reason": "Caller hungup",
            "hangup_provider_code": 16,
        },
        "extracted_data": None,
        "context_details": {"recipient_data": {}},
    }

    # 1. Validates against contracts/webhook.schema.json
    validate(instance=real_bolna_payload, schema=webhook_schema)

    # 2. POST /webhook accepts it with 200 OK and maps all native Bolna fields
    res = client.post("/webhook", json=real_bolna_payload)
    assert res.status_code == 200
    rec = res.json()
    assert rec["call_id"] == "bolna-exec-9f8e7d6c-5b4a-3210"
    assert rec["caller_number"] == "+919820112233"
    assert rec["caller_number_missing"] is False
    assert rec["duration"] == 94.2
    assert rec["call_recording_url"] == "https://media.plivo.com/v1/Account/MAXX/Recording/rec-9f8e7d6c.mp3"
    assert rec["verdict"] == "scam"
    assert "cbi.verma@okaxis" in rec["extracted_intel"]["upi_ids"]
    assert "9876543210" in rec["extracted_intel"]["phone_numbers"]


def test_webhook_enforces_bolna_webhook_secret_when_set(client, monkeypatch):
    monkeypatch.setenv("BOLNA_WEBHOOK_SECRET", "test-strong-webhook-secret-999")
    fpath = os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json")
    with open(fpath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # 1. Missing header -> 401
    r_no_hdr = client.post("/webhook", json=payload)
    assert r_no_hdr.status_code == 401

    # 2. Wrong header -> 401
    r_bad_hdr = client.post(
        "/webhook",
        json=payload,
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert r_bad_hdr.status_code == 401

    # 3. Valid Authorization: Bearer <secret> -> 200
    r_ok = client.post(
        "/webhook",
        json=payload,
        headers={"Authorization": "Bearer test-strong-webhook-secret-999"},
    )
    assert r_ok.status_code == 200

