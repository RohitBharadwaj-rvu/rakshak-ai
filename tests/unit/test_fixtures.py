import glob
import json
import os
import pytest
from jsonschema import validate, ValidationError

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURES_DIR = os.path.join(ROOT_DIR, "tests", "fixtures")
SCHEMA_PATH = os.path.join(ROOT_DIR, "contracts", "webhook.schema.json")


def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def webhook_schema():
    assert os.path.exists(SCHEMA_PATH), f"Webhook schema missing at {SCHEMA_PATH}"
    return load_json(SCHEMA_PATH)


def test_fixtures_exist():
    fixtures = glob.glob(os.path.join(FIXTURES_DIR, "*.json"))
    assert len(fixtures) >= 6, f"Expected at least 6 fixtures, found {len(fixtures)}"


def test_required_fixtures_present():
    expected_stems = [
        "01_scam_digital_arrest",
        "02_scam_kyc_account",
        "03_genuine_courier",
        "04_genuine_clinic",
        "05_scam_garbled_digits",
        "06_early_hangup",
    ]
    found = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(FIXTURES_DIR, "*.json"))]
    for exp in expected_stems:
        assert exp in found, f"Missing required fixture: {exp}"


@pytest.mark.parametrize(
    "fixture_file",
    sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))),
    ids=lambda p: os.path.basename(p),
)
def test_each_fixture_validates_against_webhook_schema(fixture_file, webhook_schema):
    payload = load_json(fixture_file)
    try:
        validate(instance=payload, schema=webhook_schema)
    except ValidationError as e:
        pytest.fail(f"Fixture {os.path.basename(fixture_file)} failed schema validation: {e.message}")


def test_callrecord_and_finalized_schemas_exist_and_validate():
    callrecord_path = os.path.join(ROOT_DIR, "contracts", "callrecord.schema.json")
    finalized_path = os.path.join(ROOT_DIR, "contracts", "call_finalized.schema.json")
    assert os.path.exists(callrecord_path), "callrecord.schema.json missing"
    assert os.path.exists(finalized_path), "call_finalized.schema.json missing"

    cr_schema = load_json(callrecord_path)
    fin_schema = load_json(finalized_path)

    sample_callrecord = {
        "call_id": "call_sample_001",
        "caller_number": "+919876543210",
        "verdict": "scam",
        "duration": 120.0,
        "start_time": "2026-10-17T02:00:00Z",
        "created_at": "2026-10-17T02:00:00Z",
        "summary": "Suspected scam attempt",
        "extracted_intel": {
            "upi_ids": ["attacker@okaxis"],
            "bank_accounts": [],
            "ifsc_codes": [],
            "phone_numbers": [],
            "links": ["https://malicious-kyc.com/verify"]
        }
    }
    validate(instance=sample_callrecord, schema=cr_schema)

    sample_event = {
        "event": "call.finalized",
        "call_id": "call_sample_001",
        "timestamp": "2026-10-17T02:02:00Z",
        "record": sample_callrecord
    }
    validate(instance=sample_event, schema=fin_schema)

