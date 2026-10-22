"""
tests/unit/test_log_intel_addition1.py - Addition 1 (mule-rotation extraction) for `log_intel`.

Verifies:
  - New fields (kind, value_raw/value_normalized, elicitation, quote, turn_index,
    seconds_from_start, identifier_status) are accepted, stored and returned; legacy
    `type` / `value` / `value_as_heard` requests keep working
  - A call can log several distinct identifiers (mule rotation)
  - Re-logging the same identifier deduplicates: one entry, times_logged++, tactics merged
  - Our own persona bait is flagged `is_bait` and never becomes scammer intel or a suspect packet
  - The new fields survive the post-call webhook into evidence (Report Suspect) packets
"""

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.main import app
from app.voice.evidence import build_report_suspect_packets
from app.voice.store import clear_call_finalized_events, get_call_record, set_db_path


@pytest.fixture
def client():
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_db_path(db_file)
    clear_call_finalized_events()
    try:
        yield TestClient(app)
    finally:
        set_db_path(None)
        if os.path.exists(db_file):
            os.remove(db_file)


def _log(client, **body):
    res = client.post("/tools/log_intel", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_new_fields_are_stored_and_returned(client):
    d = _log(
        client,
        call_id="a1_fields",
        kind="upi",
        value_raw="cbi dot officer at the rate ok axis",
        elicitation="Payment Failed",
        quote="  Sir bhejo cbi dot officer at the rate ok axis pe, abhi turant  ",
        turn_index=7,
        seconds_from_start=42.5,
    )
    assert d["kind"] == d["type"] == "upi"
    assert d["value_raw"] == d["value_as_heard"] == "cbi dot officer at the rate ok axis"
    assert d["value_normalized"] == d["normalized_value"] == "cbi.officer@okaxis"
    assert d["elicitation"] == "payment_failed"  # canonicalised playbook tactic
    assert d["quote"] == "Sir bhejo cbi dot officer at the rate ok axis pe, abhi turant"
    assert d["turn_index"] == 7 and d["seconds_from_start"] == 42.5
    assert d["identifier_status"] == "suspected"
    assert d["duplicate"] is False and d["times_logged"] == 1 and d["identifiers_logged"] == 1

    log = get_call_record("a1_fields")["extracted_intel"]["mid_call_logs"][0]
    assert log["elicitation"] == "payment_failed" and log["turn_index"] == 7
    assert log["status"] == "suspected" and log["is_bait"] is False


def test_legacy_request_shape_still_works(client):
    d = _log(client, call_id="a1_legacy", type="phone", value="9 8 7 6 5 4 3 2 1 0")
    assert d["kind"] == "phone" and d["unparseable"] is False
    assert d["elicitation"] is None and d["quote"] is None


def test_quote_is_truncated_and_unknown_tactic_kept(client):
    d = _log(client, call_id="a1_quote", kind="ifsc", value_raw="SBIN0001234", quote="x" * 300, elicitation="asked twice")
    assert len(d["quote"]) == 120
    assert d["elicitation"] == "asked twice"


def test_mule_rotation_logs_several_identifiers(client):
    _log(client, call_id="a1_mule", kind="upi", value_raw="first.mule@okaxis", elicitation="initial_ask")
    _log(client, call_id="a1_mule", kind="upi", value_raw="second.mule@ybl", elicitation="payment_failed")
    d = _log(client, call_id="a1_mule", kind="ifsc", value_raw="HDFC0001234", elicitation="ifsc_request")
    assert d["identifiers_logged"] == 3

    intel = get_call_record("a1_mule")["extracted_intel"]
    assert intel["upi_ids"] == ["first.mule@okaxis", "second.mule@ybl"]
    assert intel["ifsc_codes"] == ["HDFC0001234"]
    assert len(intel["mid_call_logs"]) == 3


def test_repeat_back_deduplicates_and_merges_context(client):
    first = _log(client, call_id="a1_dedup", kind="upi", value_raw="mule dot raju at the rate ok axis", elicitation="initial_ask")
    again = _log(
        client,
        call_id="a1_dedup",
        kind="upi",
        value_raw="MULE.RAJU@OKAXIS",
        elicitation="repeat_back",
        quote="haan ji mule dot raju at the rate ok axis",
        turn_index=12,
    )
    assert first["duplicate"] is False
    assert again["duplicate"] is True and again["times_logged"] == 2
    assert again["identifiers_logged"] == 1
    # First capture had no quote/turn, so the repeat-back fills them in; the first tactic is kept.
    assert again["elicitation"] == "initial_ask"
    assert again["quote"] == "haan ji mule dot raju at the rate ok axis" and again["turn_index"] == 12

    intel = get_call_record("a1_dedup")["extracted_intel"]
    assert len(intel["mid_call_logs"]) == 1
    assert intel["mid_call_logs"][0]["elicitations"] == ["initial_ask", "repeat_back"]
    assert intel["upi_ids"] == ["mule.raju@okaxis"]
    assert intel["entity_counts"]["mule.raju@okaxis"] == 2


def test_unparseable_values_dedupe_on_what_was_heard(client):
    _log(client, call_id="a1_raw", kind="upi", value_raw="kuch   samajh nahi aaya")
    d = _log(client, call_id="a1_raw", kind="upi", value_raw="Kuch samajh nahi aaya")
    assert d["unparseable"] is True and d["duplicate"] is True


def test_agent_normalized_hint_used_only_when_valid(client):
    ok = _log(client, call_id="a1_hint", kind="upi", value_raw="verma ji wala okaxis", value_normalized="verma.ji@okaxis")
    assert ok["unparseable"] is False and ok["value_normalized"] == "verma.ji@okaxis"
    bad = _log(client, call_id="a1_hint", kind="upi", value_raw="kuch bhi", value_normalized="not a upi")
    assert bad["unparseable"] is True


def test_persona_bait_is_flagged_and_never_scammer_intel(client):
    from app.core.rules import APPROVED_PERSONAS

    bait_upi = APPROVED_PERSONAS["ramesh"]["fake_bait"]["upi_id"]
    d = _log(client, call_id="a1_bait", kind="upi", value_raw=bait_upi)
    assert d["is_bait"] is True and d["identifiers_logged"] == 0
    rec = get_call_record("a1_bait")
    assert bait_upi not in rec["extracted_intel"]["upi_ids"]
    rec["verdict"] = "scam"
    assert all(p.value_normalized != bait_upi for p in build_report_suspect_packets(rec))


def test_fields_survive_webhook_into_suspect_packets(client):
    _log(
        client,
        call_id="a1_hook",
        kind="upi",
        value_raw="fraud dot desk at the rate ybl",
        elicitation="payment_failed",
        quote="payment fail hua? toh fraud dot desk at the rate ybl pe bhejo",
        seconds_from_start=95.0,
    )
    res = client.post(
        "/webhook",
        json={
            "id": "a1_hook",
            "agent_id": "agent-1",
            "status": "completed",
            "conversation_duration": 120.0,
            "user_number": "+919820112233",
            "transcript": "user: main CBI se hoon, abhi paise bhejo.\nassistant: beta payment fail ho gaya.",
        },
    )
    assert res.status_code == 200, res.text
    rec = get_call_record("a1_hook")
    log = rec["extracted_intel"]["mid_call_logs"][0]
    assert log["elicitation"] == "payment_failed" and log["seconds_from_start"] == 95.0

    packets = {p.value_normalized: p for p in build_report_suspect_packets(rec)}
    pkt = packets["fraud.desk@ybl"]
    assert pkt.elicitation == "payment_failed"
    assert pkt.quote.startswith("payment fail hua?")
    assert pkt.seconds_from_start == 95.0


def test_relogging_on_pre_addition1_record_does_not_crash(client):
    # Records created before Addition 1 hold legacy 4-key mid_call_logs entries.
    import json as _json
    from app.voice.store import _get_conn, append_mid_call_intel

    append_mid_call_intel("a1_old", "upi", "cbi dot officer at the rate ok axis", "cbi.officer@okaxis", False)
    conn = _get_conn()
    try:
        row = conn.execute("SELECT extracted_intel_json FROM call_records WHERE call_id = 'a1_old'").fetchone()
        intel = _json.loads(row["extracted_intel_json"])
        intel["mid_call_logs"] = [
            {"type": "upi", "value_as_heard": "cbi dot officer at the rate ok axis",
             "normalized_value": "cbi.officer@okaxis", "unparseable": False}
        ]
        conn.execute("UPDATE call_records SET extracted_intel_json = ? WHERE call_id = 'a1_old'", (_json.dumps(intel),))
        conn.commit()
    finally:
        conn.close()

    d = _log(client, call_id="a1_old", type="upi", value_as_heard="cbi dot officer at the rate ok axis")
    assert d["duplicate"] is True and d["times_logged"] == 2
    assert d["kind"] == "upi" and d["value_raw"] == "cbi dot officer at the rate ok axis"
    assert d["identifier_status"] == "suspected" and d["is_bait"] is False
