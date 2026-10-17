"""
tests/integration/test_api.py - CallRecord Read API Integration Suite (T-API).

Verifies:
  - `/api/calls` lists newest first, 50 per page, and filters by verdict
  - `/api/calls/{id}` returns the full record, and an unknown ID returns a 404
  - A missing or wrong token gets a 401 on every route
  - Every response validates against `contracts/call_record.schema.json`
"""

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
from app.voice.store import clear_call_finalized_events, set_db_path

SCHEMA_PATH = os.path.join(ROOT_DIR, "contracts", "call_record.schema.json")
AUTH_HEADERS = {"Authorization": "Bearer local_api_token_123"}


@pytest.fixture(scope="module")
def call_record_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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


def test_missing_or_wrong_token_returns_401_on_every_route(client):
    # Missing token
    assert client.get("/api/calls").status_code == 401
    assert client.get("/api/calls/some_call_id").status_code == 401

    # Wrong token
    bad_headers = {"Authorization": "Bearer wrong_secret_token"}
    assert client.get("/api/calls", headers=bad_headers).status_code == 401
    assert client.get("/api/calls/some_call_id", headers=bad_headers).status_code == 401


def test_unknown_id_returns_404(client):
    res = client.get("/api/calls/non_existent_call_999", headers=AUTH_HEADERS)
    assert res.status_code == 404


def test_list_newest_first_50_per_page_verdict_filter_and_schema(client, call_record_schema):
    # Insert 55 calls: 40 scam, 15 genuine
    for i in range(1, 56):
        is_scam = i <= 40
        cid = f"api_call_{i:03d}"
        text = (
            "Main CBI se bol raha hoon, aap digital arrest par hain, turant ramesh.scam@okaxis par paise bhejo."
            if is_scam
            else "नमस्ते, मैं डॉ सुंदरम क्लिनिक से बोल रहा हूँ। आपका कल सुबह 10 बजे रूटीन डॉक्टर चेकअप अपॉइंटमेंट है।"
        )
        payload = {
            "call_id": cid,
            "agent_id": "bolna_agent_guardianline_v0",
            "caller_number": f"+91987654{i:04d}",
            "call_duration": 45.0,
            "call_status": "completed",
            "transcript": [{"role": "user", "content": text}],
        }
        w_res = client.post("/webhook", json=payload)
        assert w_res.status_code == 200

    # Page 1: 50 items newest first (api_call_055 down to api_call_006)
    res_p1 = client.get("/api/calls", headers=AUTH_HEADERS)
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert len(data_p1["calls"]) == 50
    assert data_p1["calls"][0]["call_id"] == "api_call_055"
    assert data_p1["calls"][-1]["call_id"] == "api_call_006"

    for rec in data_p1["calls"]:
        validate(instance=rec, schema=call_record_schema)

    # Page 2: remaining 5 items (api_call_005 down to api_call_001)
    res_p2 = client.get("/api/calls?page=2", headers=AUTH_HEADERS)
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert len(data_p2["calls"]) == 5
    assert data_p2["calls"][0]["call_id"] == "api_call_005"
    assert data_p2["calls"][-1]["call_id"] == "api_call_001"

    # Filter by verdict=scam (40 total)
    res_scam = client.get("/api/calls?verdict=scam", headers=AUTH_HEADERS)
    assert res_scam.status_code == 200
    scam_calls = res_scam.json()["calls"]
    assert len(scam_calls) == 40
    assert all(c["verdict"] == "scam" for c in scam_calls)

    # Filter by verdict=genuine (15 total)
    res_gen = client.get("/api/calls?verdict=genuine", headers=AUTH_HEADERS)
    assert res_gen.status_code == 200
    gen_calls = res_gen.json()["calls"]
    assert len(gen_calls) == 15
    assert all(c["verdict"] == "genuine" for c in gen_calls)

    # Single CallRecord detail endpoint
    res_detail = client.get("/api/calls/api_call_001", headers=AUTH_HEADERS)
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["call_id"] == "api_call_001"
    validate(instance=detail, schema=call_record_schema)
