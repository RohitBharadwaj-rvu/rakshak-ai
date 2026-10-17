"""
tests/unit/test_report.py - 1930 Report Generator Golden File Suite (T-RPT).

Verifies:
  - Reports for 5+ fixture CallRecords match their golden files in `tests/golden/`
    exactly, with the generation time masked
  - Each report has: scammer number, every UPI ID, account and IFSC, call date and
    time in IST, duration, summary, and a line asking the family to check it before reporting
  - A field the call didn't capture prints "Not captured", never a blank or a guess
  - `/api/calls/{id}/report` returns the pre-filled report when authenticated and 401 when unauthenticated
"""

import glob
import json
import os
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.main import app
from app.voice.report import generate_1930_report, mask_report_generation_time
from app.voice.store import clear_call_finalized_events, set_db_path

FIXTURES_DIR = os.path.join(ROOT_DIR, "tests", "fixtures")
GOLDEN_DIR = os.path.join(ROOT_DIR, "tests", "golden")
AUTH_HEADERS = {"Authorization": "Bearer local_api_token_123"}


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


def test_fixture_reports_match_golden_files_exactly(client):
    fixture_files = sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json")))
    assert len(fixture_files) >= 5

    for fpath in fixture_files:
        base = os.path.splitext(os.path.basename(fpath))[0]
        golden_path = os.path.join(GOLDEN_DIR, f"{base}.report.txt")
        assert os.path.exists(golden_path), f"Missing golden file {golden_path}"

        with open(fpath, "r", encoding="utf-8") as f:
            payload = json.load(f)
        payload["start_time"] = "2026-10-24T10:30:00Z"

        res = client.post("/webhook", json=payload)
        assert res.status_code == 200
        record = res.json()

        generated = mask_report_generation_time(generate_1930_report(record))
        with open(golden_path, "r", encoding="utf-8") as gf:
            expected_golden = gf.read()

        assert generated == expected_golden, f"Report mismatch for {base}"

        # Required structural checks on every report
        assert "Suspect / Scammer Number  :" in generated
        assert "UPI IDs                   :" in generated
        assert "Bank Account Numbers      :" in generated
        assert "IFSC Codes                :" in generated
        assert "Call Date & Time (IST)    : 2026-10-24 16:00:00 IST" in generated
        assert "Call Duration             :" in generated
        assert "3. INCIDENT SUMMARY" in generated
        assert "Please review and verify every field in this pre-filled report" in generated


def test_uncaptured_fields_print_not_captured_never_blank():
    empty_record = {
        "call_id": "call_empty_test",
        "verdict": "scam",
        "caller_number": "",
        "start_time": "",
        "duration": None,
        "summary": "",
        "extracted_intel": {
            "upi_ids": [],
            "bank_accounts": [],
            "ifsc_codes": [],
            "phone_numbers": [],
            "pan_numbers": [],
            "links": [],
        },
    }
    rpt = generate_1930_report(empty_record, mask_generation_time=True)
    assert "Suspect / Scammer Number  : Not captured" in rpt
    assert "Call Date & Time (IST)    : Not captured" in rpt
    assert "Call Duration             : Not captured" in rpt
    assert "UPI IDs                   : Not captured" in rpt
    assert "Bank Account Numbers      : Not captured" in rpt
    assert "IFSC Codes                : Not captured" in rpt
    assert "Suspect Phone Numbers     : Not captured" in rpt
    assert "PAN Numbers               : Not captured" in rpt
    assert "Suspicious Links / URLs   : Not captured" in rpt


def test_report_endpoint_auth_and_response(client):
    with open(os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json"), "r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["start_time"] = "2026-10-24T10:30:00Z"
    client.post("/webhook", json=payload)

    call_id = payload["call_id"]
    # Unauthenticated request returns 401
    assert client.get(f"/api/calls/{call_id}/report").status_code == 401

    # Authenticated request returns 200 plain text report matching golden
    res = client.get(f"/api/calls/{call_id}/report", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert "cbi.officer.verma@okaxis" in res.text
    assert "+919876543210" in res.text

    # JSON format option
    res_json = client.get(f"/api/calls/{call_id}/report?format=json", headers=AUTH_HEADERS)
    assert res_json.status_code == 200
    assert res_json.json()["call_id"] == call_id
    assert "cbi.officer.verma@okaxis" in res_json.json()["report"]
