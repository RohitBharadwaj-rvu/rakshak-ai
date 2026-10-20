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

    # 4. Valid X-Webhook-Secret -> 200
    r_x_ok = client.post(
        "/webhook",
        json=payload,
        headers={"X-Webhook-Secret": "test-strong-webhook-secret-999"},
    )
    assert r_x_ok.status_code == 200

    # 5. Valid X-Bolna-Secret -> 200
    r_bolna_ok = client.post(
        "/webhook",
        json=payload,
        headers={"X-Bolna-Secret": "test-strong-webhook-secret-999"},
    )
    assert r_bolna_ok.status_code == 200


def test_webhook_secret_unset_allows_unauthenticated(client, monkeypatch):
    monkeypatch.setenv("BOLNA_WEBHOOK_SECRET", "")
    fpath = os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json")
    with open(fpath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # When unset, unauthenticated post is allowed (local dev / test behavior)
    res = client.post("/webhook", json=payload)
    assert res.status_code == 200



def test_three_step_mid_call_tool_join_priority(client, caplog):
    import logging
    caplog.set_level(logging.WARNING)

    # Case (a): execution_id is filled with real webhook id -> joins directly on execution_id
    r_sw_a = client.post(
        "/tools/switch_to_honeypot",
        json={
            "call_id": "plivo-sid-aaa",
            "execution_id": "bolna-exec-aaa",
            "language": "hi",
            "persona_id": "ramesh",
        },
    )
    assert r_sw_a.status_code == 200
    assert r_sw_a.json()["call_id"] == "bolna-exec-aaa"

    r_log_a = client.post(
        "/tools/log_intel",
        json={
            "call_id": "plivo-sid-aaa",
            "execution_id": "bolna-exec-aaa",
            "type": "upi",
            "value": "exec.join@okaxis",
        },
    )
    assert r_log_a.status_code == 200

    w_a = client.post(
        "/webhook",
        json={
            "id": "bolna-exec-aaa",
            "agent_id": "agent-1",
            "status": "completed",
            "conversation_duration": 42.0,
            "user_number": "+919820112233",
            "created_at": "2026-10-17T09:00:00Z",
            "transcript": "assistant: हैलो?\nuser: पैसे भेजो।",
            "telephony_data": {"provider_call_id": "plivo-sid-aaa"},
        },
    )
    assert w_a.status_code == 200
    rec_a = w_a.json()
    assert "exec.join@okaxis" in rec_a["extracted_intel"]["upi_ids"]
    assert len(rec_a["extracted_intel"]["mid_call_logs"]) == 1
    assert rec_a["honeypot_switch_time"] != rec_a["start_time"]

    # Case (b): execution_id is literal "%(execution_id)s" (ignored), call_id has provider_call_id -> joins via telephony_data.provider_call_id
    client.post(
        "/tools/switch_to_honeypot",
        json={
            "call_id": "plivo-sid-bbb",
            "execution_id": "%(execution_id)s",
            "language": "hi",
            "persona_id": "sunita",
        },
    )
    client.post(
        "/tools/log_intel",
        json={
            "call_id": "plivo-sid-bbb",
            "execution_id": "%(execution_id)s",
            "type": "upi",
            "value": "provider.sid@ybl",
        },
    )
    w_b = client.post(
        "/webhook",
        json={
            "id": "bolna-exec-bbb",
            "agent_id": "agent-1",
            "status": "completed",
            "conversation_duration": 55.0,
            "user_number": "+919820112233",
            "created_at": "2026-10-17T09:10:00Z",
            "transcript": "assistant: हैलो?\nuser: तुरंत भेजो।",
            "telephony_data": {"provider_call_id": "plivo-sid-bbb"},
        },
    )
    assert w_b.status_code == 200
    rec_b = w_b.json()
    assert rec_b["persona"] == "sunita"
    assert "provider.sid@ybl" in rec_b["extracted_intel"]["upi_ids"]
    assert len(rec_b["extracted_intel"]["mid_call_logs"]) == 1
    assert rec_b["honeypot_switch_time"] != rec_b["start_time"]
    assert get_call_record("plivo-sid-bbb") is None

    # Case (c1): Single active pending call with literal "%(call_sid)s" -> joins via fallback and logs a WARNING
    caplog.clear()
    client.post(
        "/tools/log_intel",
        json={
            "call_id": "%(call_sid)s",
            "execution_id": "%(execution_id)s",
            "type": "upi",
            "value": "fallback.single@paytm",
        },
    )
    w_c1 = client.post(
        "/webhook",
        json={
            "id": "bolna-exec-ccc1",
            "agent_id": "agent-1",
            "status": "completed",
            "conversation_duration": 30.0,
            "user_number": "+919820112233",
            "created_at": "2026-10-17T09:20:00Z",
            "transcript": "assistant: जी?\nuser: पेमेंट करो।",
            "telephony_data": {"provider_call_id": "plivo-sid-ccc1"},
        },
    )
    assert w_c1.status_code == 200
    rec_c1 = w_c1.json()
    assert "fallback.single@paytm" in rec_c1["extracted_intel"]["upi_ids"]
    assert any("Fallback single-active-call join fired" in r.message for r in caplog.records)

    # Case (c2): Two overlapping pending calls in window -> fallback refuses to guess so calls never mix up intel
    caplog.clear()
    client.post(
        "/tools/log_intel",
        json={"call_id": "overlap-call-1", "type": "upi", "value": "family1@okaxis"},
    )
    client.post(
        "/tools/log_intel",
        json={"call_id": "overlap-call-2", "type": "upi", "value": "family2@okaxis"},
    )
    w_c2 = client.post(
        "/webhook",
        json={
            "id": "bolna-exec-ccc2",
            "agent_id": "agent-1",
            "status": "completed",
            "conversation_duration": 30.0,
            "user_number": "+919820112233",
            "created_at": "2026-10-17T09:30:00Z",
            "transcript": "assistant: जी?\nuser: हैलो।",
            "telephony_data": {"provider_call_id": "plivo-sid-ccc2"},
        },
    )
    assert w_c2.status_code == 200
    rec_c2 = w_c2.json()
    assert rec_c2["extracted_intel"]["mid_call_logs"] == []
    assert any("Fallback single-active-call join skipped" in r.message for r in caplog.records)


def test_live_call_2_no_glued_phone_and_split_devanagari_upi_extracted(client):
    """
    Regression test for Live Call #2 (1d36d742-c44d-4ce5-930f-0d081bb8284b):
      1. Caller says "नाइन सेवन टू थ्री फाइव" twice on separate turns before saying "9723512345" ->
         must extract ONLY "9723512345" and NEVER invent "9723597235".
      2. Caller says "राहुल.एसबीआई" and then "वाई बी एल।" on separate turns ->
         must extract "rahul.sbi@ybl".
    """
    payload = {
        "id": "1d36d742-c44d-4ce5-930f-0d081bb8284b",
        "agent_id": "6e4ddb72-f380-475c-8b65-08cc1ac52ec0",
        "status": "completed",
        "conversation_duration": 137.0,
        "user_number": "+917019941295",
        "created_at": "2026-10-17T13:40:20.500298+00:00",
        "telephony_data": {
            "provider_call_id": "a719105f-e552-4fa5-a56c-fcd1deaded17",
            "recording_url": "https://api.bolna.ai/recordings/call/1d36d742-c44d-4ce5-930f-0d081bb8284b",
        },
        "transcript": [
            {"role": "assistant", "content": "हैलो जी?"},
            {"role": "user", "content": "SBI Head Office"},
            {"role": "assistant", "content": "Aap kaun"},
            {"role": "user", "content": "सर राहुल बोल रहा हूँ"},
            {"role": "assistant", "content": "Rahul ji, aap kis kaam se call kar rahe hain?"},
            {"role": "user", "content": "आपका KYC"},
            {"role": "user", "content": "मेरा नंबर है।"},
            {"role": "assistant", "content": "Sorry, phir se bataiye? Aapka number kya hai?"},
            {"role": "user", "content": "नाइन सेवन टू थ्री फाइव"},
            {"role": "assistant", "content": "Thoda aur clearly bataiye beta, poora number chahiye."},
            {"role": "user", "content": "नाइन सेवन टू थ्री फाइव।"},
            {"role": "assistant", "content": "Rahul ji, poora number 10 digit ka chahiye beta."},
            {"role": "user", "content": "9723512345"},
            {"role": "assistant", "content": "9723512345, sahi hai na Rahul ji?"},
            {"role": "user", "content": "अभी तुरंत ₹5000 भेजिए।"},
            {"role": "user", "content": "राहुल.एसबीआई"},
            {"role": "assistant", "content": "Rahul ji, UPI ID mein @ ke baad kya likhna hai beta?"},
            {"role": "user", "content": "वाई बी एल।"},
            {"role": "assistant", "content": "Rahul dot SBI at WBL, sahi hai?"},
            {"role": "user", "content": "हाँ, सही है।"},
        ],
    }
    res = client.post("/webhook", json=payload)
    assert res.status_code == 200
    rec = res.json()
    assert rec["extracted_intel"]["phone_numbers"] == ["9723512345"]
    assert "9723597235" not in rec["extracted_intel"]["phone_numbers"]
    assert rec["extracted_intel"]["upi_ids"] == ["rahul.sbi@ybl"]



@pytest.mark.parametrize(
    "method,expected",
    [("groq", True), ("gemini", True), ("offline_rules", False), ("heuristic", False)],
)
def test_call_record_records_whether_stage2_ran(client, monkeypatch, method, expected):
    import app.voice.classifier as classifier_mod
    from app.voice.classifier import CallerClassificationResult

    def fake_classify(call_id, caller_number="", conversation=None, language="hi", **kwargs):
        return CallerClassificationResult(
            call_id=call_id, verdict="unsure", confidence=0.5, reason="stub",
            latency_ms=1.0, method=method, pillars_detected=[],
        )

    monkeypatch.setattr(classifier_mod, "classify_caller", fake_classify)
    with open(os.path.join(FIXTURES_DIR, "03_genuine_courier.json"), "r", encoding="utf-8") as f:
        payload = json.load(f)

    rec = client.post("/webhook", json=payload).json()
    assert rec["stage2_ran"] is expected
    assert rec["classifier_method"] == method
    stored = get_call_record(payload["call_id"])
    assert stored["stage2_ran"] is expected
    assert stored["classifier_method"] == method


def test_pending_record_has_unknown_stage2(client):
    client.post("/tools/log_intel", json={"call_id": "stage2_pending_001", "type": "upi", "value": "a@okaxis"})
    rec = get_call_record("stage2_pending_001")
    assert rec["stage2_ran"] is None
    assert rec["classifier_method"] == ""


def test_init_db_adds_stage2_columns_to_old_database():
    import sqlite3
    from app.voice.store import init_db

    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE call_records (call_id TEXT PRIMARY KEY, status TEXT)")
    conn.commit()
    conn.close()
    try:
        set_db_path(db_file)
        init_db()
        conn = sqlite3.connect(db_file)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(call_records)")}
        conn.close()
        assert {"stage2_ran", "classifier_method"} <= cols
    finally:
        set_db_path(None)
        os.remove(db_file)


def test_fallback_join_never_merges_smoke_test_records(client):
    # scripts/smoke.sh leaves a pending smoke_call_001 record; a real webhook must not adopt it.
    client.post(
        "/tools/log_intel",
        json={"call_id": "smoke_call_001", "type": "upi", "value_as_heard": "cbi dot officer at the rate ok axis"},
    )
    res = client.post(
        "/webhook",
        json={
            "id": "bolna-exec-real-001",
            "agent_id": "agent-1",
            "status": "completed",
            "conversation_duration": 30.0,
            "user_number": "+919820112233",
            "transcript": "assistant: जी?\nuser: पेमेंट करो।",
            "telephony_data": {"provider_call_id": "plivo-sid-real-001"},
        },
    )
    assert res.status_code == 200
    assert "cbi.officer@okaxis" not in res.json()["extracted_intel"]["upi_ids"]
    smoke = get_call_record("smoke_call_001")
    assert smoke is not None and smoke["status"] == "pending"
