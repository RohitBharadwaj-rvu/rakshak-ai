"""
tests/unit/test_evidence.py - Unit and Integration tests for Evidence Packets & Verification (Addition 2).

Tests:
1. Canonical JSON transcript SHA-256 hashing (sorted keys, UTF-8, compact separators).
2. Audio recording bytes SHA-256 download hashing (10s timeout, hashes bytes not URL).
3. Call finalization stores transcript_sha256, recording_sha256, hashed_at, money_lost, evidence_status.
4. GET /api/calls/{id}/evidence/verify recomputes and compares against stored values (match true/false).
5. 1930 Gating: money_lost (bool, default False); report generated only when money_lost is True.
6. Confirm flow: draft -> confirmed_by_family; POST /api/calls/{id}/evidence/confirm sets status + confirmed_at.
   Explicitly verifies auto_submitted is False and no automatic portal submission occurs.
7. Chakshu category mapping in ONE config dict with demo TODO comment; description template uses CallRecord facts.
8. Report Suspect packet: kind, value_normalized, value_raw, seconds_from_start, quote (<=120 chars), elicitation.
   Fields missing from older records are omitted, not invented.
9. Privacy test: packets contain NO parent personal data (name, address, own number).
10. Auth checks for verify and confirm endpoints.
"""

import hashlib
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.main import app
from app.voice.evidence import (
    CHAKSHU_CATEGORY_MAPPING,
    build_1930_report,
    build_chakshu_description,
    build_chakshu_packet,
    build_report_suspect_packets,
    compute_canonical_transcript_hash,
    compute_evidence_hash,
    compute_recording_bytes_hash,
)
from app.voice.store import (
    clear_call_finalized_events,
    confirm_call_evidence,
    get_call_record,
    set_db_path,
)

AUTH_HEADERS = {"Authorization": "Bearer test_api_token_not_secret"}


@pytest.fixture
def client():
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_db_path(db_file)
    clear_call_finalized_events()
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        set_db_path(None)
        if os.path.exists(db_file):
            os.remove(db_file)


@pytest.fixture
def sample_call_record():
    return {
        "call_id": "call_test_evidence_101",
        "caller_number": "+919876543210",
        "start_time": "2026-10-20T10:00:00Z",
        "duration": 420,
        "transcript": "Caller: Transfer 25000 to fraud@upi or police warrant issued. Assistant: Let me find my glasses beta.",
        "summary": "Suspect posing as cyber police officer demanding UPI payment.",
        "call_recording_url": "https://storage.googleapis.com/guardianline-recordings/call_101.wav",
        "recording_url": "https://storage.googleapis.com/guardianline-recordings/call_101.wav",
        "verdict": "scam",
        "extracted_intel": {
            "upi_ids": ["fraud@upi", "mule@okaxis"],
            "account_numbers": ["918273645019"],
            "ifsc_codes": ["SBIN0001234"],
            "phone_numbers": ["+919876543210", "+919123456789"],
            "links": ["https://pay-fine-portal.in"],
        },
    }


# ==============================================================================
# 1. HASHING TESTS
# ==============================================================================

def test_canonical_transcript_hash_key_ordering_invariance():
    # Transcript turns with different key orders must yield identical canonical SHA-256
    t1 = [{"role": "assistant", "content": "Hello"}, {"role": "user", "content": "Pay now"}]
    t2 = [{"content": "Hello", "role": "assistant"}, {"content": "Pay now", "role": "user"}]
    h1 = compute_canonical_transcript_hash(t1)
    h2 = compute_canonical_transcript_hash(t2)
    assert h1 == h2
    assert len(h1) == 64


def test_recording_bytes_hash_empty_or_missing_url():
    h, reason = compute_recording_bytes_hash(None)
    assert h is None
    assert reason == "no_recording_url"

    h, reason = compute_recording_bytes_hash("")
    assert h is None
    assert reason == "no_recording_url"


def test_recording_bytes_hash_downloads_raw_bytes():
    fake_audio_bytes = b"RIFF....WAVEfmt ....dataFAKEAUDIO12345"
    expected_sha256 = hashlib.sha256(fake_audio_bytes).hexdigest()

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_audio_bytes
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        actual_hash, err = compute_recording_bytes_hash(
            "https://cdn.example.org/recordings/call_42.wav",
            timeout=10.0,
        )
        assert err is None
        assert actual_hash == expected_sha256
        assert len(actual_hash) == 64
        # Verify it hashed the raw audio bytes, not the URL string
        assert actual_hash != hashlib.sha256(b"https://cdn.example.org/recordings/call_42.wav").hexdigest()
        assert mock_urlopen.call_count == 1


def test_recording_bytes_hash_handles_fetch_failure():
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        actual_hash, err = compute_recording_bytes_hash(
            "https://cdn.example.org/unreachable.wav",
            timeout=10.0,
        )
        assert actual_hash is None
        assert "fetch_failed" in err


# ==============================================================================
# 2. CALL FINALIZATION PERSISTENCE & 1930 GATING
# ==============================================================================

def test_webhook_finalization_computes_and_stores_hashes(client):
    payload = {
        "call_id": "call_ev_hash_001",
        "agent_id": "agent-1",
        "status": "completed",
        "conversation_duration": 45.0,
        "caller_number": "+919876543210",
        "transcript": [{"role": "user", "content": "Send money"}],
        "money_lost": False,
    }
    res = client.post("/webhook", json=payload)
    assert res.status_code == 200

    rec = get_call_record("call_ev_hash_001")
    assert rec is not None
    assert rec["transcript_sha256"] is not None
    assert len(rec["transcript_sha256"]) == 64
    assert rec["recording_sha256"] is None  # no recording URL passed
    assert rec["recording_hash_error"] == "no_recording_url"
    assert rec["hashed_at"] is not None
    assert rec["money_lost"] is False
    assert rec["evidence_status"] == "draft"


def test_1930_gating_logic():
    rec_no_loss = {"call_id": "c1", "money_lost": False, "caller_number": "+919999999999"}
    assert build_1930_report(rec_no_loss) is None

    rec_with_loss = {
        "call_id": "c2",
        "money_lost": True,
        "caller_number": "+919999999999",
        "start_time": "2026-10-20T10:00:00Z",
        "duration": 120,
        "summary": "Victim coerced into transfer",
        "extracted_intel": {"upi_ids": ["scammer@ybl"]},
    }
    report = build_1930_report(rec_with_loss)
    assert report is not None
    assert "1930" in report
    assert "scammer@ybl" in report


# ==============================================================================
# 3. VERIFY ENDPOINT RECOMPUTATION & MATCH COMPARISON
# ==============================================================================

def test_verify_endpoint_recomputes_and_compares_hashes(client):
    payload = {
        "call_id": "call_verify_match_001",
        "agent_id": "agent-1",
        "status": "completed",
        "conversation_duration": 30.0,
        "caller_number": "+919876543210",
        "transcript": [{"role": "user", "content": "Hello world"}],
        "money_lost": True,
    }
    client.post("/webhook", json=payload)

    # 401 unauthenticated
    unauth = client.get("/api/calls/call_verify_match_001/evidence/verify")
    assert unauth.status_code == 401

    # Authenticated verify
    res = client.get("/api/calls/call_verify_match_001/evidence/verify", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    assert data["call_id"] == "call_verify_match_001"
    assert data["transcript_match"] is True
    assert data["recording_match"] is True
    assert data["matches"]["transcript"] is True
    assert data["matches"]["recording"] is True
    assert data["transcript_sha256"]["match"] is True
    assert data["evidence_status"] == "draft"
    assert data["money_lost"] is True
    assert data["report_1930"] is not None  # Generated because money_lost is True
    assert "chakshu_packet" in data
    assert "report_suspect_packets" in data


# ==============================================================================
# 4. CONFIRM FLOW & NO AUTO-SUBMISSION
# ==============================================================================

def test_confirm_flow_transitions_status_and_never_auto_submits(client):
    payload = {
        "call_id": "call_confirm_001",
        "agent_id": "agent-1",
        "status": "completed",
        "conversation_duration": 60.0,
        "caller_number": "+919876543210",
        "transcript": [{"role": "user", "content": "Police calling"}],
        "money_lost": False,
    }
    client.post("/webhook", json=payload)

    # Pre-confirm state
    rec_before = get_call_record("call_confirm_001")
    assert rec_before["evidence_status"] == "draft"
    assert rec_before["confirmed_at"] is None

    # Unauthenticated POST -> 401
    unauth = client.post("/api/calls/call_confirm_001/evidence/confirm")
    assert unauth.status_code == 401

    # Authenticated POST -> 200
    res = client.post("/api/calls/call_confirm_001/evidence/confirm", headers=AUTH_HEADERS)
    assert res.status_code == 200
    body = res.json()

    assert body["evidence_status"] == "confirmed_by_family"
    assert body["confirmed_at"] is not None
    assert body["auto_submitted"] is False
    assert body["portal_submission"] == "manual_only"

    # Verify DB update
    rec_after = get_call_record("call_confirm_001")
    assert rec_after["evidence_status"] == "confirmed_by_family"
    assert rec_after["confirmed_at"] is not None


# ==============================================================================
# 5. CHAKSHU CONFIG & TEMPLATE FACTS
# ==============================================================================

def test_chakshu_category_mapping_config():
    # Verify mapping is in ONE config dict with the required TODO comment
    assert isinstance(CHAKSHU_CATEGORY_MAPPING, dict)
    assert "digital_arrest" in CHAKSHU_CATEGORY_MAPPING
    assert "kyc" in CHAKSHU_CATEGORY_MAPPING
    assert "courier" in CHAKSHU_CATEGORY_MAPPING

    # Verify TODO comment exists in evidence.py source
    import inspect
    import app.voice.evidence as ev_mod
    src = inspect.getsource(ev_mod)
    assert "verify current categories on sancharsaathi.gov.in before demo" in src


def test_build_chakshu_description_template_uses_only_facts(sample_call_record):
    desc = build_chakshu_description(sample_call_record)
    assert "call_test_evidence_101" in desc
    assert "+919876543210" in desc
    assert "420 seconds" in desc
    assert "scam" in desc


# ==============================================================================
# 6. REPORT SUSPECT PACKET DETAILS & OMISSION OF MISSING FIELDS
# ==============================================================================

def test_report_suspect_packets_provenance_and_field_omission():
    # Record with rich log_intel fields
    rich_record = {
        "call_id": "call_rich_intel_001",
        "caller_number": "+919876543210",
        "start_time": "2026-10-20T10:00:00Z",
        "duration": 300,
        "transcript": [],
        "verdict": "scam",
        "extracted_intel": {
            "mid_call_logs": [
                {
                    "type": "upi",
                    "normalized_value": "officer@okaxis",
                    "value_as_heard": "officer at okaxis",
                    "seconds_from_start": 45.2,
                    "quote": "Send fine to officer@okaxis immediately or face jail",
                    "elicitation": "fake_legal_demand",
                }
            ]
        },
    }
    packets = build_report_suspect_packets(rich_record)
    assert len(packets) == 1
    p = packets[0]
    p_dict = p.to_dict()

    assert p.kind == "upi"
    assert p.value_normalized == "officer@okaxis"
    assert p.value_raw == "officer at okaxis"
    assert p.status == "suspected"
    assert p.seconds_from_start == 45.2
    assert p.quote == "Send fine to officer@okaxis immediately or face jail"
    assert p.elicitation == "fake_legal_demand"

    # Older record without log_intel fields: missing fields must be omitted, NOT invented
    old_record = {
        "call_id": "call_old_001",
        "caller_number": "+919876543210",
        "start_time": "2026-10-20T10:00:00Z",
        "duration": 180,
        "transcript": [],
        "verdict": "scam",
        "extracted_intel": {
            "upi_ids": ["legacy@upi"],
        },
    }
    old_packets = build_report_suspect_packets(old_record)
    assert len(old_packets) == 1
    old_p_dict = old_packets[0].to_dict()

    assert old_p_dict["kind"] == "upi"
    assert old_p_dict["value_normalized"] == "legacy@upi"
    assert old_p_dict["status"] == "suspected"
    # Missing fields are omitted from serialized dict
    assert "seconds_from_start" not in old_p_dict
    assert "quote" not in old_p_dict
    assert "elicitation" not in old_p_dict


# ==============================================================================
# 7. PRIVACY TEST: NO PARENT PERSONAL DATA IN PACKETS
# ==============================================================================

def test_packets_contain_no_parent_personal_data():
    parent_name = "Ram Sharma"
    parent_phone = "+919820011223"
    parent_address = "Flat 402, Shanti Niketan, Pune"

    call_record = {
        "call_id": "call_privacy_test_001",
        "caller_number": "+919123456789",  # Scammer number
        "user_number": parent_phone,       # Parent/callee number
        "parent_phone": parent_phone,
        "parent_name": parent_name,
        "parent_address": parent_address,
        "start_time": "2026-10-20T10:00:00Z",
        "duration": 250,
        "verdict": "scam",
        "summary": f"Scammer called Ram Sharma at Flat 402, Shanti Niketan, Pune demanding payment.",
        "extracted_intel": {
            "mid_call_logs": [
                {
                    "type": "upi",
                    "normalized_value": "scam.mule@hdfc",
                    "value_as_heard": "scam mule at hdfc",
                    "seconds_from_start": 30.0,
                    "quote": f"Listen {parent_name}, send payment right now from {parent_phone}",
                },
                {
                    "type": "phone",
                    "normalized_value": parent_phone,
                    "value_as_heard": parent_phone,
                },
            ],
            "phone_numbers": [parent_phone, "+919123456789"],
            "upi_ids": ["scam.mule@hdfc"],
        },
    }

    chakshu = build_chakshu_packet(call_record)
    suspect_packets = build_report_suspect_packets(call_record)

    # 1. Chakshu packet verification
    chakshu_json = json.dumps(chakshu.model_dump(), ensure_ascii=False)
    assert parent_name not in chakshu_json
    assert parent_phone not in chakshu_json
    assert parent_address not in chakshu_json

    # 2. Suspect identifiers must NOT contain parent phone or data
    for ident in chakshu.suspect_identifiers:
        assert ident.value_normalized != parent_phone
        assert ident.value_raw != parent_phone
        if ident.quote:
            assert parent_name not in ident.quote
            assert parent_phone not in ident.quote

    # 3. Report Suspect packets verification
    for sp in suspect_packets:
        sp_dict = sp.to_dict()
        sp_json = json.dumps(sp_dict, ensure_ascii=False)
        assert parent_name not in sp_json
        assert parent_phone not in sp_json
        assert parent_address not in sp_json
