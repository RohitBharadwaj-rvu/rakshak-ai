"""
Lane C consumes Lane B's contracts (T-CONTRACT). These copies must stay byte-identical to
lane B's files; the checks below pin the fields the alert and dashboard code rely on.
"""

import json
import os

from jsonschema import validate

ROOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..")


def load_schema(name):
    with open(os.path.join(ROOT_DIR, "contracts", name), "r", encoding="utf-8") as f:
        return json.load(f)


LANE_B_EVENT = {
    "event": "call.finalized",
    "call_id": "call_scam_digital_arrest_001",
    "verdict": "scam",
    "caller_number": "+919876543210",
    "timestamp": "2026-10-17T02:00:00+00:00",
    "report_link": "/api/calls/call_scam_digital_arrest_001/report",
    "extracted_intel": {"upi_ids": ["cbi.officer.verma@okaxis"], "links": ["https://fake-cbi.in/pay"]},
}


def test_lane_b_call_finalized_event_validates():
    validate(instance=LANE_B_EVENT, schema=load_schema("call_finalized.schema.json"))


def test_call_record_intel_carries_every_type_lane_a_logs():
    # Lane A's log_intel types: upi, phone, account, ifsc, link
    intel = load_schema("call_record.schema.json")["properties"]["extracted_intel"]["properties"]
    for field in ("upi_ids", "phone_numbers", "bank_accounts", "ifsc_codes", "links"):
        assert field in intel, f"CallRecord.extracted_intel is missing {field}"


def test_call_record_has_fields_the_dashboard_reads():
    props = load_schema("call_record.schema.json")["properties"]
    for field in ("call_id", "caller_number", "start_time", "duration", "verdict", "summary", "transcript", "report_link"):
        assert field in props, f"CallRecord is missing {field}"
