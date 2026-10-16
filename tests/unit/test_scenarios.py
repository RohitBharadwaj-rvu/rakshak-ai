import glob
import json
import os
import pytest
from jsonschema import validate, ValidationError

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCENARIOS_DIR = os.path.join(ROOT_DIR, "evaluation", "scenarios")
SCHEMA_PATH = os.path.join(ROOT_DIR, "contracts", "scenario.schema.json")

# Approved fake bait values used by GuardianLine personas (must not collide with planted details)
APPROVED_BAIT_VALUES = {
    "upi_ids": ["ramesh.elderly@okhdfc", "sunita.pension@okicici", "prof.iyer@sbi"],
    "account_numbers": ["9999000011112222", "8888777766665555"],
    "phone_numbers": ["9123400000", "9876500000"],
}


def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def scenario_schema():
    assert os.path.exists(SCHEMA_PATH), f"Scenario schema missing at {SCHEMA_PATH}"
    return load_json(SCHEMA_PATH)


@pytest.fixture(scope="module")
def all_scenarios():
    files = glob.glob(os.path.join(SCENARIOS_DIR, "*.json"))
    scenarios = []
    for f in files:
        scenarios.append((os.path.basename(f), load_json(f)))
    return scenarios


def test_digital_arrest_scenario_exists():
    hindi_exists = os.path.exists(os.path.join(SCENARIOS_DIR, "digital_arrest_hindi.json"))
    tamil_exists = os.path.exists(os.path.join(SCENARIOS_DIR, "digital_arrest_tamil.json"))
    assert hindi_exists, "digital_arrest_hindi.json missing in evaluation/scenarios/"
    assert tamil_exists, "digital_arrest_tamil.json missing in evaluation/scenarios/"


def test_unique_scenario_ids(all_scenarios):
    ids = [sc["id"] for _, sc in all_scenarios]
    assert len(ids) == len(set(ids)), f"Duplicate scenario IDs found: {ids}"


def test_scam_types_have_hindi_and_tamil_versions(all_scenarios):
    """Every scam type must have both a Hindi ('hi') and Tamil ('ta') version."""
    scam_scenarios = [sc for _, sc in all_scenarios if sc.get("type") == "scam"]
    
    # Map scam base name -> set of languages
    scam_lang_map = {}
    for sc in scam_scenarios:
        # e.g., id "scam_digital_arrest_hi" -> base "digital_arrest"
        sc_id = sc["id"]
        parts = sc_id.replace("scam_", "").rsplit("_", 1)
        base_name = parts[0]
        lang = sc.get("language")
        scam_lang_map.setdefault(base_name, set()).add(lang)

    for base_name, langs in scam_lang_map.items():
        assert "hi" in langs, f"Scam type '{base_name}' is missing Hindi ('hi') scenario"
        assert "ta" in langs, f"Scam type '{base_name}' is missing Tamil ('ta') scenario"


@pytest.mark.parametrize(
    "scenario_file",
    sorted(glob.glob(os.path.join(SCENARIOS_DIR, "*.json"))),
    ids=lambda p: os.path.basename(p),
)
def test_scenario_validates_against_schema(scenario_file, scenario_schema):
    data = load_json(scenario_file)
    try:
        validate(instance=data, schema=scenario_schema)
    except ValidationError as e:
        pytest.fail(f"Scenario {os.path.basename(scenario_file)} failed schema validation: {e.message}")


@pytest.mark.parametrize(
    "scenario_file",
    sorted(glob.glob(os.path.join(SCENARIOS_DIR, "*.json"))),
    ids=lambda p: os.path.basename(p),
)
def test_planted_intel_rules(scenario_file):
    """
    Every scam scenario plants at least one UPI ID or account,
    no genuine scenario plants any, and no planted value matches fake bait.
    """
    data = load_json(scenario_file)
    sc_type = data.get("type")
    planted = data.get("planted_details", {})
    upis = planted.get("upi_ids", [])
    accounts = planted.get("account_numbers", [])

    if sc_type == "scam":
        assert len(upis) > 0 or len(accounts) > 0, (
            f"Scam scenario {data['id']} must plant at least one UPI ID or account number"
        )
    elif sc_type == "genuine":
        assert len(upis) == 0 and len(accounts) == 0, (
            f"Genuine scenario {data['id']} must not plant any UPI ID or account number"
        )

    # Verify no planted details match fake bait
    for u in upis:
        assert u not in APPROVED_BAIT_VALUES["upi_ids"], f"Planted UPI {u} collides with fake bait"
    for a in accounts:
        assert a not in APPROVED_BAIT_VALUES["account_numbers"], f"Planted account {a} collides with fake bait"
