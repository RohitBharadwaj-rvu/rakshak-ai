"""
tests/integration/test_graph_inbound_flow.py - Inbound flow verification for Rakshak v2 Graph Agent.

Simulates the multi-node graph flow on the smoke_01_digital_arrest_hi scenario:
  1. Screening node calls POST /tools/classify_caller -> verdict is scam.
  2. Transition to Honeypot -> calls POST /tools/switch_to_honeypot -> gets rotating persona and bait.
  3. Transition to Extraction -> calls POST /tools/log_intel -> logs UPI/account and ingests into syndicate.
  4. Final webhook -> POST /webhook -> confirms CallRecord finalized and syndicate clustering updated.
  5. Confirms rakshak-v0.json exists as fallback.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app
from app.voice.store import (
    clear_call_finalized_events,
    get_call_record,
    set_db_path,
)
from app.voice.syndicate import cluster_syndicates
from app.notify.bloom import get_community_bloom_filter, reset_community_bloom_filter


@pytest.fixture()
def client():
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_db_path(db_file)
    clear_call_finalized_events()
    reset_community_bloom_filter()
    test_client = TestClient(app)
    yield test_client, db_file
    set_db_path(None)
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except OSError:
            pass


def test_v0_fallback_backup_exists():
    v0_path = ROOT_DIR / "bolna" / "rakshak-v0.json"
    assert v0_path.exists(), "rakshak-v0.json must exist as backup"
    content = json.loads(v0_path.read_text(encoding="utf-8"))
    assert "agent_config" in content or "tasks" in content


def test_graph_inbound_flow_smoke_01(client):
    test_client, db_file = client

    # Load smoke_01_digital_arrest_hi transcript turns from smoke_manifest.json
    manifest_path = ROOT_DIR / "evaluation" / "voice" / "smoke_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    smoke_01 = next(c for c in manifest["calls"] if c["call_id"] == "smoke_01_digital_arrest_hi")

    turns = smoke_01["turns"]
    history = [{"role": t["role"], "text": t["content"]} for t in turns]
    summary = "Caller claims to be Senior Inspector Ajay from New Delhi Cyber Crime Cell, stating Taiwan parcel seized with narcotics and elder is under digital arrest, demanding fifty thousand rupees fee."

    call_id = "test-graph-call-smoke-01"
    agent_id = "v2-graph-20261026-9b81f14a"

    # Step 1: Screening node calls classify_caller
    classify_payload = {
        "call_id": call_id,
        "caller_number": "+919876543210",
        "caller_summary": summary,
        "conversation_history": history,
        "language": "hi",
    }
    r1 = test_client.post("/tools/classify_caller", json=classify_payload)
    assert r1.status_code == 200, f"classify_caller failed: {r1.text}"
    c_res = r1.json()
    assert c_res["verdict"] in ["scam", "unsure"], f"Expected scam/unsure, got {c_res['verdict']}"

    # Step 2: Honeypot node triggered -> switch_to_honeypot
    switch_payload = {
        "call_id": call_id,
        "language": "hi",
    }
    r2 = test_client.post("/tools/switch_to_honeypot", json=switch_payload)
    assert r2.status_code == 200, f"switch_to_honeypot failed: {r2.text}"
    h_res = r2.json()
    assert "persona_id" in h_res
    assert "fake_bait" in h_res
    assert h_res["fake_bait"]["account_number"]
    assert h_res["fake_bait"]["ifsc_code"]

    # Step 3: Extraction node logs scammer payment intel
    # Scammer dictates escrow account details
    intel_upi = {
        "call_id": call_id,
        "type": "upi",
        "value": "delhi.police.escrow@okaxis",
        "value_normalized": "delhi.police.escrow@okaxis",
        "elicitation": "initial_ask",
    }
    r3_1 = test_client.post("/tools/log_intel", json=intel_upi)
    assert r3_1.status_code == 200, f"log_intel upi failed: {r3_1.text}"
    assert r3_1.json()["status"] == "logged"

    intel_account = {
        "call_id": call_id,
        "type": "account",
        "value": "912010045678901",
        "value_normalized": "912010045678901",
        "elicitation": "ifsc_request",
    }
    r3_2 = test_client.post("/tools/log_intel", json=intel_account)
    assert r3_2.status_code == 200, f"log_intel account failed: {r3_2.text}"

    # Step 4: Webhook finalized
    webhook_payload = {
        "id": call_id,
        "agent_id": agent_id,
        "status": "completed",
        "conversation_duration": 145.0,
        "user_number": "+919876543210",
        "created_at": "2026-10-26T14:30:00Z",
        "transcript": "\n".join(f"{t['role']}: {t['content']}" for t in turns),
        "telephony_data": {
            "duration": "145",
            "from_number": "+919876543210",
            "to_number": "+918045681190",
            "provider_call_id": f"provider-{call_id}",
        },
    }
    r4 = test_client.post("/webhook", json=webhook_payload)
    assert r4.status_code == 200, f"webhook failed: {r4.text}"
    rec = r4.json()

    assert rec["call_id"] == call_id
    assert rec["status"] == "finalized"
    assert rec["verdict"] == "scam"
    assert "delhi.police.escrow@okaxis" in rec["extracted_intel"]["upi_ids"]
    assert "912010045678901" in rec["extracted_intel"]["bank_accounts"]

    # Verify syndicate clustering and bloom filter
    clusters = cluster_syndicates(db_path=db_file)
    assert len(clusters) >= 1
    target_cluster = next((c for c in clusters if call_id in c["call_ids"]), None)
    assert target_cluster is not None
    assert "delhi.police.escrow@okaxis" in target_cluster["upi_ids"]

    bloom = get_community_bloom_filter()
    assert "delhi.police.escrow@okaxis" in bloom
