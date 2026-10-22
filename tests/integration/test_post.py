"""
tests/integration/test_post.py - Post-Call Reflection & Enrichment Suite (T-POST) + Sprint 3 Hardening.

Verifies:
  - Both reflection and enrichment tasks run on all 6 fixtures without errors
  - They start AFTER the CallRecord is saved and `call.finalized` is emitted, never
    delaying the webhook response or the family alert
  - Each finishes well within 60 s (sub-second locally)
  - A failure in either reflection or enrichment is logged with `call_id` and leaves
    the saved CallRecord completely intact
  - Webhook retry on `cleanup_pending` transitions the record to `finalized`, and CSV
    export (`/api/calls/export.csv`) outputs valid rows for `scripts/compute_metrics.py`
"""

import csv
import glob
import io
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
    register_call_finalized_listener,
    set_db_path,
)
from app.voice.webhook import (
    set_cleanup_hook,
    set_enrichment_hook,
    set_reflection_hook,
)

FIXTURES_DIR = os.path.join(ROOT_DIR, "tests", "fixtures")
AUTH_HEADERS = {"Authorization": "Bearer test_api_token_not_secret"}


@pytest.fixture()
def client():
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_db_path(db_file)
    clear_call_finalized_events()
    set_cleanup_hook(None)
    set_reflection_hook(None)
    set_enrichment_hook(None)
    test_client = TestClient(app)
    yield test_client
    set_cleanup_hook(None)
    set_reflection_hook(None)
    set_enrichment_hook(None)
    set_db_path(None)
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except OSError:
            pass


def test_reflection_and_enrichment_run_on_all_6_fixtures_within_60s(client):
    fixture_files = sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json")))
    assert len(fixture_files) == 6

    for fpath in fixture_files:
        with open(fpath, "r", encoding="utf-8") as f:
            payload = json.load(f)

        t0 = time.perf_counter()
        res = client.post("/webhook", json=payload)
        elapsed = time.perf_counter() - t0

        assert res.status_code == 200
        assert elapsed < 60.0

        saved = get_call_record(payload["call_id"])
        assert saved is not None
        assert saved["status"] == "finalized"

        intel = saved["extracted_intel"]
        assert "reflection" in intel, f"Missing reflection on {payload['call_id']}"
        assert "enrichment" in intel, f"Missing enrichment on {payload['call_id']}"
        assert intel["reflection"]["call_id"] == payload["call_id"]
        assert intel["enrichment"]["call_id"] == payload["call_id"]


def test_tasks_start_after_record_saved_and_after_family_alert(client):
    execution_order = []

    def on_alert(evt):
        # When `call.finalized` fires, the record must already exist in SQLite,
        # and post-call reflection/enrichment must not have run yet.
        rec = get_call_record(evt["call_id"])
        assert rec is not None
        execution_order.append("alert_fired")

    def tracked_reflection(rec):
        execution_order.append("reflection_started")
        return {"call_id": rec["call_id"], "engagement_outcome": "tracked"}

    def tracked_enrichment(rec):
        execution_order.append("enrichment_started")
        return {"call_id": rec["call_id"], "upi_enrichment": []}

    register_call_finalized_listener(on_alert)
    set_reflection_hook(tracked_reflection)
    set_enrichment_hook(tracked_enrichment)

    with open(os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json"), "r", encoding="utf-8") as f:
        payload = json.load(f)

    res = client.post("/webhook", json=payload)
    assert res.status_code == 200
    assert execution_order[0] == "alert_fired"
    assert "reflection_started" in execution_order[1:]
    assert "enrichment_started" in execution_order[1:]


def test_reflection_or_enrichment_failure_is_logged_and_leaves_call_record_intact(client, caplog):
    def failing_reflection(_rec):
        raise RuntimeError("Simulated reflection crash")

    def failing_enrichment(_rec):
        raise RuntimeError("Simulated enrichment crash")

    set_reflection_hook(failing_reflection)
    set_enrichment_hook(failing_enrichment)

    with open(os.path.join(FIXTURES_DIR, "02_scam_kyc_account.json"), "r", encoding="utf-8") as f:
        payload = json.load(f)

    res = client.post("/webhook", json=payload)
    assert res.status_code == 200

    saved = get_call_record(payload["call_id"])
    assert saved is not None
    assert saved["status"] == "finalized"
    assert saved["verdict"] == "scam"
    assert "50100432891234" in saved["extracted_intel"]["bank_accounts"]
    assert "HDFC0001234" in saved["extracted_intel"]["ifsc_codes"]
    assert any(payload["call_id"] in r.message for r in caplog.records)


def test_webhook_retry_heals_cleanup_pending_and_csv_export_works(client):
    def broken_cleanup(_ctx):
        raise RuntimeError("LLM timeout on first try")

    set_cleanup_hook(broken_cleanup)

    with open(os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json"), "r", encoding="utf-8") as f:
        payload = json.load(f)

    # First delivery fails cleanup -> saved as cleanup_pending
    r1 = client.post("/webhook", json=payload)
    assert r1.status_code == 200
    assert r1.json()["status"] == "cleanup_pending"
    assert len(get_call_finalized_events(payload["call_id"])) == 1

    # Retry after cleanup recovers -> transitions to finalized without firing a 2nd alert
    set_cleanup_hook(None)
    r2 = client.post("/webhook", json=payload)
    assert r2.status_code == 200
    assert r2.json()["status"] == "finalized"
    assert len(get_call_finalized_events(payload["call_id"])) == 1

    # Export CSV endpoint
    csv_res = client.get("/api/calls/export.csv", headers=AUTH_HEADERS)
    assert csv_res.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_res.text)))
    assert len(rows) == 1
    assert rows[0]["call_id"] == payload["call_id"]
    assert rows[0]["final_verdict"] == "scam"
    assert "cbi.officer.verma@okaxis" in rows[0]["upi_ids"]
