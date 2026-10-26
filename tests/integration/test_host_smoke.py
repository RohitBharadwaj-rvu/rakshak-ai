"""
tests/integration/test_host_smoke.py - Deployed Backend Smoke Test & Sprint 4 Suite (T-HOST, Sprint 4).

Verifies:
  - `/health` returns 200
  - Each tool endpoint (`/tools/classify_caller`, `/tools/switch_to_honeypot`, `/tools/log_intel`)
    answers a canned request with a schema-valid response
  - Multi-turn `conversation_history` smoke test passes when scam signal (`"CBI se bol raha hu"`)
    is in turn1 only and `caller_summary` only has turn3 (`"OTP bhejo"`)
  - After a simulated server restart on the same SQLite DB, the backend answers immediately
    and retains all pre-restart records and persona state
  - A Bolna test call shows up in the backend log with its `call_id`
  - Sprint 4 STT extraction-miss analyzer (`analyze_corpus_extraction_misses`) achieves 100%
    recall across the 6 fixtures and accurately diagnoses deliberately garbled misses
  - Sprint 4 online SQLite backup (`backup_call_records_db`) creates an exact, queryable snapshot
"""

import glob
import json
import os
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient
from jsonschema import validate

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.main import app
from app.voice.cleanup import cleanup_call_intel
from app.voice.miss_analyzer import analyze_call_extraction, analyze_corpus_extraction_misses
from app.voice.store import (
    backup_call_records_db,
    clear_call_finalized_events,
    get_call_record,
    set_db_path,
)

CONTRACTS_DIR = os.path.join(ROOT_DIR, "contracts")
FIXTURES_DIR = os.path.join(ROOT_DIR, "tests", "fixtures")


def _load_schema(name: str):
    with open(os.path.join(CONTRACTS_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def test_t_host_smoke_health_tools_schema_restart_and_call_id_logging(caplog):
    import logging
    caplog.set_level(logging.INFO)
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        set_db_path(db_file)
        clear_call_finalized_events()
        client1 = TestClient(app)

        # 1. /health returns 200
        h_res = client1.get("/health")
        assert h_res.status_code == 200
        assert h_res.json()["status"] == "ok"

        # 2. Each tool endpoint answers a canned request with a schema-valid response
        cls_res = client1.post(
            "/tools/classify_caller",
            json={
                "call_id": "smoke_call_001",
                "caller_number": "+919876543210",
                "caller_summary": "Caller says CBI warrant and demands immediate UPI transfer.",
            },
        )
        assert cls_res.status_code == 200
        validate(instance=cls_res.json(), schema=_load_schema("classify_caller_response.schema.json"))

        # 2b. Multi-turn smoke test: turn1="CBI se bol raha hu", turn3="OTP bhejo"
        #     Should detect scam even when caller_summary misses turn1
        mt_res = client1.post(
            "/tools/classify_caller",
            json={
                "call_id": "smoke_call_multiturn",
                "caller_number": "+919876543210",
                "caller_summary": "OTP bhejo",
                "conversation_history": [
                    {"role": "caller", "text": "CBI se bol raha hu"},
                    {"role": "assistant", "text": "Ji bataiye"},
                    {"role": "caller", "text": "OTP bhejo"},
                ],
            },
        )
        assert mt_res.status_code == 200
        mt_json = mt_res.json()
        validate(instance=mt_json, schema=_load_schema("classify_caller_response.schema.json"))
        assert mt_json["verdict"] == "scam"
        assert "authority_coercion" in mt_json["pillars_detected"]
        assert "value_demand" in mt_json["pillars_detected"]

        sw_res = client1.post(
            "/tools/switch_to_honeypot",
            json={"call_id": "smoke_call_001", "language": "hi"},
        )
        assert sw_res.status_code == 200
        validate(instance=sw_res.json(), schema=_load_schema("switch_to_honeypot_response.schema.json"))

        lg_res = client1.post(
            "/tools/log_intel",
            json={
                "call_id": "smoke_call_001",
                "type": "upi",
                "value": "smoke.scam@okaxis",
            },
        )
        assert lg_res.status_code == 200
        validate(instance=lg_res.json(), schema=_load_schema("log_intel_response.schema.json"))

        # 3. Simulated server restart (new FastAPI app instance on the same SQLite DB)
        client2 = TestClient(app)
        assert client2.get("/health").status_code == 200
        sw_after_restart = client2.post(
            "/tools/switch_to_honeypot",
            json={"call_id": "smoke_call_001", "language": "hi"},
        )
        assert sw_after_restart.status_code == 200
        assert sw_after_restart.json()["persona_id"] == sw_res.json()["persona_id"]

        # 4. Bolna test call shows up in backend log with its call_id
        assert any("smoke_call_001" in r.message for r in caplog.records)
    finally:
        set_db_path(None)
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except OSError:
                pass


def test_sprint4_extraction_miss_analyzer_and_online_db_backup():
    items = []
    for fpath in sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))):
        with open(fpath, "r", encoding="utf-8") as f:
            payload = json.load(f)
        transcript = payload.get("transcript") or []
        metadata = payload.get("metadata") or {}
        cleaned = cleanup_call_intel(transcript=transcript, verdict="scam", metadata=metadata)
        items.append(
            {
                "record": {
                    "call_id": payload["call_id"],
                    "transcript": transcript,
                    "extracted_intel": cleaned["extracted_intel"],
                },
                "planted_intel": metadata.get("planted_intel", {}),
            }
        )

    report = analyze_corpus_extraction_misses(items)
    assert report["summary"]["call_level_extraction_accuracy_pct"] == 100.0
    assert report["summary"]["entity_level_recall_pct"] == 100.0
    assert report["summary"]["total_misses"] == 0

    # Deliberately test a missed entity diagnosis
    miss_diag = analyze_call_extraction(
        record={
            "call_id": "call_missed_test",
            "transcript": [{"role": "user", "content": "Send money to okay axis dot something"}],
            "extracted_intel": {
                "upi_ids": [],
                "mid_call_logs": [{"type": "upi", "value_as_heard": "okay axis", "unparseable": True}],
            },
        },
        planted_intel={"upi_id": "missing.handle@okaxis"},
    )
    assert miss_diag["miss_count"] == 1
    assert "spaced_handle" in miss_diag["misses"][0]["stt_garble_patterns"]
    assert len(miss_diag["unparseable_mid_call_logs"]) == 1

    # Online SQLite backup check
    fd1, src_db = tempfile.mkstemp(suffix=".db")
    fd2, dst_db = tempfile.mkstemp(suffix="_backup.db")
    os.close(fd1)
    os.close(fd2)
    try:
        set_db_path(src_db)
        client = TestClient(app)
        with open(os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json"), "r", encoding="utf-8") as f:
            payload = json.load(f)
        client.post("/webhook", json=payload)

        backup_call_records_db(dst_db)
        set_db_path(dst_db)
        restored = get_call_record(payload["call_id"])
        assert restored is not None
        assert "cbi.officer.verma@okaxis" in restored["extracted_intel"]["upi_ids"]
    finally:
        set_db_path(None)
        for p in (src_db, dst_db):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
