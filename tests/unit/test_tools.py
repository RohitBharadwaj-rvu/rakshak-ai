"""
tests/unit/test_tools.py - Mid-Call Tool Endpoints Unit & Load Suite (T-TOOLS).

Verifies:
  - switch_to_honeypot returns persona and bait for requested language; unknown language -> 'hi';
    second call with same call_id returns the exact same persona
  - Every bait value served is on APPROVED_BAIT_VALUES
  - log_intel stores both value_as_heard and normalized_value; unparseable value is stored with
    unparseable=True, never rejected
  - log_intel for a call_id with no record yet creates a pending record, which the webhook merges later
  - classify_caller route returns 'unsure' if the classifier takes over 1.5 s
  - On all three tools, a missing call_id returns a 422, and no response ever contains a stack trace
  - Load: 100 sequential requests to switch_to_honeypot and log_intel with p95 <= 300 ms
"""

import os
import sys
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app.voice.classifier as classifier_mod
from app.core.rules import APPROVED_BAIT_VALUES
from app.main import app
from app.voice.store import clear_call_finalized_events, get_call_record, set_db_path


@pytest.fixture()
def client():
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_db_path(db_file)
    clear_call_finalized_events()
    test_client = TestClient(app)
    yield test_client
    set_db_path(None)
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except OSError:
            pass


def test_switch_to_honeypot_language_fallback_and_idempotency(client):
    # Unknown language falls back to 'hi'
    res1 = client.post(
        "/tools/switch_to_honeypot",
        json={"call_id": "call_tool_01", "language": "french", "persona_id": "sunita"},
    )
    assert res1.status_code == 200
    b1 = res1.json()
    assert b1["language"] == "hi"
    assert b1["persona_id"] == "sunita"

    # Every bait value served is on the approved bait list
    for val in b1["fake_bait"].values():
        assert str(val).lower() in APPROVED_BAIT_VALUES

    # Second call with same call_id returns the exact same persona even if a different persona_id is requested
    res2 = client.post(
        "/tools/switch_to_honeypot",
        json={"call_id": "call_tool_01", "language": "en", "persona_id": "iyer"},
    )
    assert res2.status_code == 200
    b2 = res2.json()
    assert b2["persona_id"] == "sunita"
    assert b2["fake_bait"] == b1["fake_bait"]


def test_log_intel_parseable_and_unparseable_and_pending_record_merge(client):
    call_id = "call_pending_merge_01"
    assert get_call_record(call_id) is None

    # 1. Valid spoken UPI
    r1 = client.post(
        "/tools/log_intel",
        json={
            "call_id": call_id,
            "type": "upi",
            "value_as_heard": "cbi dot officer dot verma at the rate ok axis",
        },
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["value_as_heard"] == "cbi dot officer dot verma at the rate ok axis"
    assert d1["normalized_value"] == "cbi.officer.verma@okaxis"
    assert d1["unparseable"] is False

    # Pending record now exists in SQLite
    pending = get_call_record(call_id)
    assert pending is not None
    assert pending["status"] == "pending"

    # 2. Unparseable value is stored with unparseable=True, never rejected
    r2 = client.post(
        "/tools/log_intel",
        json={
            "call_id": call_id,
            "type": "upi",
            "value_as_heard": "garbled noise without handle",
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["unparseable"] is True
    assert d2["value_as_heard"] == "garbled noise without handle"

    # 3. Webhook arrives later and merges the pending mid-call intel
    webhook_payload = {
        "call_id": call_id,
        "agent_id": "bolna_agent_guardianline_v0",
        "caller_number": "+919876543210",
        "call_duration": 65.0,
        "call_status": "completed",
        "transcript": [
            {"role": "assistant", "content": "Namaste, kaun bol rahe hain?"},
            {"role": "user", "content": "Main CBI se bol raha hoon, turant paise bhejo."},
        ],
    }
    w_res = client.post("/webhook", json=webhook_payload)
    assert w_res.status_code == 200
    final_rec = w_res.json()
    assert final_rec["status"] == "finalized"
    assert "cbi.officer.verma@okaxis" in final_rec["extracted_intel"]["upi_ids"]
    assert len(final_rec["extracted_intel"]["mid_call_logs"]) == 2


def test_classify_caller_returns_unsure_when_over_1_5s(client, monkeypatch):
    def slow_classifier(*args, **kwargs):
        time.sleep(1.7)
        raise RuntimeError("Should have timed out")

    monkeypatch.setattr(classifier_mod, "classify_caller", slow_classifier)

    t0 = time.perf_counter()
    res = client.post(
        "/tools/classify_caller",
        json={
            "call_id": "call_slow_01",
            "caller_number": "+919876543210",
            "conversation": [{"role": "caller", "content": "Hello"}],
        },
    )
    elapsed = time.perf_counter() - t0
    assert res.status_code == 200
    data = res.json()
    assert data["verdict"] == "unsure"
    assert elapsed < 2.2
    assert "Traceback" not in res.text


def test_missing_call_id_returns_422_and_no_stack_trace(client):
    for path, payload in [
        ("/tools/classify_caller", {"conversation": []}),
        ("/tools/switch_to_honeypot", {"language": "hi"}),
        ("/tools/log_intel", {"type": "upi", "value_as_heard": "test@okaxis"}),
    ]:
        res = client.post(path, json=payload)
        assert res.status_code == 422
        assert "call_id" in res.text
        assert "Traceback" not in res.text


def test_load_100_sequential_requests_p95_under_300ms(client):
    sw_latencies = []
    log_latencies = []

    for i in range(100):
        cid = f"load_call_{i:03d}"
        t0 = time.perf_counter()
        r_sw = client.post("/tools/switch_to_honeypot", json={"call_id": cid, "language": "hi"})
        sw_latencies.append((time.perf_counter() - t0) * 1000.0)
        assert r_sw.status_code == 200

        t1 = time.perf_counter()
        r_lg = client.post(
            "/tools/log_intel",
            json={"call_id": cid, "type": "phone", "value_as_heard": "nine eight सात छह five four 3 2 1 0"},
        )
        log_latencies.append((time.perf_counter() - t1) * 1000.0)
        assert r_lg.status_code == 200

    sw_sorted = sorted(sw_latencies)
    log_sorted = sorted(log_latencies)
    sw_p95 = sw_sorted[int(0.95 * len(sw_sorted)) - 1]
    log_p95 = log_sorted[int(0.95 * len(log_sorted)) - 1]

    assert sw_p95 <= 300.0, f"switch_to_honeypot p95 {sw_p95:.2f} ms > 300 ms"
    assert log_p95 <= 300.0, f"log_intel p95 {log_p95:.2f} ms > 300 ms"


def test_bolna_v1_prompt_field_names_compatibility(client):
    # 1. classify_caller with caller_summary (Saket's Bolna v1 prompt parameter)
    r_cls = client.post(
        "/tools/classify_caller",
        json={
            "call_id": "bolna_v1_001",
            "caller_number": "+919876543210",
            "caller_summary": "Caller claims to be from CBI Mumbai, says a parcel with drugs was found in the user's name, threatens digital arrest and demands immediate UPI transfer.",
        },
    )
    assert r_cls.status_code == 200
    d_cls = r_cls.json()
    assert d_cls["verdict"] == "scam"
    assert "confidence" in d_cls
    assert "reason" in d_cls

    # 2. switch_to_honeypot returns name, age, city, short_backstory, bait_values
    r_sw = client.post(
        "/tools/switch_to_honeypot",
        json={"call_id": "bolna_v1_001", "language": "hi"},
    )
    assert r_sw.status_code == 200
    d_sw = r_sw.json()
    assert d_sw["name"] == "Ramesh Sharma"
    assert d_sw["age"] == 72
    assert d_sw["city"] == "Lucknow"
    assert "retired post office clerk" in d_sw["short_backstory"]
    assert d_sw["bait_values"]["upi_id"] == "ramesh.elderly@okhdfc"
    assert d_sw["bait_values"]["account_number"] == "9999000011112222"
    assert d_sw["bait_values"]["otp"] == "000000"
    assert d_sw["bait_values"]["aadhaar"] == "9999 0000 1111"

    # 3. log_intel with `value` (Saket's Bolna v1 prompt parameter)
    r_lg = client.post(
        "/tools/log_intel",
        json={
            "call_id": "bolna_v1_001",
            "type": "upi",
            "value": "cbi dot officer at the rate ok axis",
        },
    )
    assert r_lg.status_code == 200
    d_lg = r_lg.json()
    assert d_lg["status"] == "logged"
    assert d_lg["value"] == "cbi dot officer at the rate ok axis"
    assert d_lg["normalized_value"] == "cbi.officer@okaxis"

