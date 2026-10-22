"""
tests/contract/test_contracts.py - Cross-Lane JSON Schema Contract Suite (T-CONTRACT).

Verifies:
  - Every schema in contracts/*.schema.json exists, is valid JSON Schema, and carries a version number
  - docs/interfaces.md exists and documents all interfaces
  - Backend responses for all three tools validate against their response schemas
  - Every fixture in tests/fixtures/*.json validates against contracts/webhook.schema.json
  - CallRecords returned by /webhook and /api/calls validate against contracts/call_record.schema.json
  - call.finalized events validate against contracts/call_finalized.schema.json
  - Requests missing a required field get HTTP 422 naming the missing field
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
from app.voice.store import (
    clear_call_finalized_events,
    get_call_finalized_events,
    set_db_path,
)

CONTRACTS_DIR = os.path.join(ROOT_DIR, "contracts")
FIXTURES_DIR = os.path.join(ROOT_DIR, "tests", "fixtures")


def _load_schema(name: str) -> dict:
    path = os.path.join(CONTRACTS_DIR, name)
    assert os.path.exists(path), f"Missing contract schema: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def temp_client():
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_db_path(db_file)
    clear_call_finalized_events()
    client = TestClient(app)
    yield client
    set_db_path(None)
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except OSError:
            pass


def test_interfaces_doc_exists():
    doc_path = os.path.join(ROOT_DIR, "docs", "interfaces.md")
    assert os.path.exists(doc_path), "docs/interfaces.md must exist"
    with open(doc_path, "r", encoding="utf-8") as f:
        text = f.read()
    for term in (
        "classify_caller",
        "switch_to_honeypot",
        "log_intel",
        "/webhook",
        "CallRecord",
        "call.finalized",
    ):
        assert term in text, f"docs/interfaces.md missing documentation for {term}"


def test_all_schemas_carry_version_number():
    schema_files = sorted(glob.glob(os.path.join(CONTRACTS_DIR, "*.schema.json")))
    assert len(schema_files) >= 10, f"Expected >= 10 schemas in contracts/, found {len(schema_files)}"
    for path in schema_files:
        with open(path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        assert "version" in schema and isinstance(schema["version"], str) and schema["version"], (
            f"Schema {os.path.basename(path)} is missing a non-empty 'version' field"
        )


def test_tool_responses_validate_against_schemas(temp_client):
    # 1. classify_caller
    req_cls = {
        "call_id": "contract_call_01",
        "caller_number": "+919876543210",
        "language": "hi",
        "conversation": [
            {"role": "caller", "content": "Main CBI se bol raha hoon, aap digital arrest par hain."}
        ],
    }
    validate(instance=req_cls, schema=_load_schema("classify_caller_request.schema.json"))
    res_cls = temp_client.post("/tools/classify_caller", json=req_cls)
    assert res_cls.status_code == 200
    validate(instance=res_cls.json(), schema=_load_schema("classify_caller_response.schema.json"))

    # 2. switch_to_honeypot
    req_sw = {"call_id": "contract_call_01", "language": "hi"}
    validate(instance=req_sw, schema=_load_schema("switch_to_honeypot_request.schema.json"))
    res_sw = temp_client.post("/tools/switch_to_honeypot", json=req_sw)
    assert res_sw.status_code == 200
    validate(instance=res_sw.json(), schema=_load_schema("switch_to_honeypot_response.schema.json"))

    # 3. log_intel
    req_log = {
        "call_id": "contract_call_01",
        "type": "upi",
        "value_as_heard": "cbi dot officer at the rate ok axis",
    }
    validate(instance=req_log, schema=_load_schema("log_intel_request.schema.json"))
    res_log = temp_client.post("/tools/log_intel", json=req_log)
    assert res_log.status_code == 200
    validate(instance=res_log.json(), schema=_load_schema("log_intel_response.schema.json"))


@pytest.mark.parametrize(
    "fixture_path",
    sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))),
    ids=lambda p: os.path.basename(p),
)
def test_webhook_and_callrecord_and_finalized_event_schemas(temp_client, fixture_path):
    with open(fixture_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    validate(instance=payload, schema=_load_schema("webhook.schema.json"))

    res = temp_client.post("/webhook", json=payload)
    assert res.status_code == 200
    record = res.json()
    validate(instance=record, schema=_load_schema("call_record.schema.json"))

    # Also verify read API response validates against CallRecord schema
    get_res = temp_client.get(
        f"/api/calls/{payload['call_id']}",
        headers={"Authorization": "Bearer test_api_token_not_secret"},
    )
    assert get_res.status_code == 200
    validate(instance=get_res.json(), schema=_load_schema("call_record.schema.json"))

    # Verify call.finalized event validates against call_finalized.schema.json
    events = get_call_finalized_events(payload["call_id"])
    assert len(events) == 1
    validate(instance=events[0], schema=_load_schema("call_finalized.schema.json"))


def test_missing_required_field_returns_422_naming_field(temp_client):
    for endpoint, body, missing_field in [
        ("/tools/classify_caller", {"language": "hi"}, "call_id"),
        ("/tools/switch_to_honeypot", {"language": "hi"}, "call_id"),
        ("/tools/log_intel", {"type": "upi", "value_as_heard": "abc@okaxis"}, "call_id"),
        ("/tools/log_intel", {"call_id": "c1", "value_as_heard": "abc@okaxis"}, "type"),
        ("/tools/log_intel", {"call_id": "c1", "type": "upi"}, "value_as_heard"),
    ]:
        res = temp_client.post(endpoint, json=body)
        assert res.status_code == 422, f"Expected 422 on {endpoint} missing {missing_field}, got {res.status_code}"
        text = res.text
        assert missing_field in text, f"422 response on {endpoint} did not name missing field '{missing_field}': {text}"
        assert "Traceback" not in text
