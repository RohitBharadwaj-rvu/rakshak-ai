import json
import os
import pytest
from scripts.text_harness import run_scenario_simulation, default_guardian_agent_policy

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCENARIOS_DIR = os.path.join(ROOT_DIR, "evaluation", "scenarios")


def load_sample_scenarios():
    scam_file = os.path.join(SCENARIOS_DIR, "digital_arrest_hindi.json")
    genuine_file = os.path.join(SCENARIOS_DIR, "genuine_courier_hi.json")
    with open(scam_file, "r", encoding="utf-8") as f:
        scam = json.load(f)
    with open(genuine_file, "r", encoding="utf-8") as f:
        genuine = json.load(f)
    return scam, genuine


def test_broken_agent_never_switches_is_caught():
    """Agent that never switches to honeypot must score 0% detection on scam."""
    scam_scenario, _ = load_sample_scenarios()

    def broken_never_switch_agent(state, caller_turn, scenario):
        # Deliberately never switches to honeypot
        state["mode"] = "screening"
        state["last_verdict"] = "unsure"
        return {"text": "नमस्ते, मैं शर्मा जी का असिस्टेंट बोल रहा हूँ।", "mode": "screening"}

    res = run_scenario_simulation(scam_scenario, agent_func=broken_never_switch_agent)
    assert res["switched_to_honeypot"] is False
    assert res["final_verdict"] != "scam"


def test_broken_agent_flags_every_caller_is_caught():
    """Agent that flags every caller as scam must score 100% false positives on genuine calls."""
    _, genuine_scenario = load_sample_scenarios()

    def broken_flag_all_agent(state, caller_turn, scenario):
        # Deliberately flags every single caller as scam
        state["mode"] = "honeypot"
        state["last_verdict"] = "scam"
        return {"text": "आप स्कैमर हैं! पैसा नहीं दूँगा!", "mode": "honeypot"}

    res = run_scenario_simulation(genuine_scenario, agent_func=broken_flag_all_agent)
    # The harness correctly reveals that genuine call was falsely flagged
    assert res["final_verdict"] == "scam"
    assert res["expected_verdict"] == "genuine"


def test_broken_agent_invented_account_trips_bait_check():
    """Agent that hallucinates an invented/unapproved account number trips the bait-only check."""
    scam_scenario, _ = load_sample_scenarios()

    def broken_hallucinating_agent(state, caller_turn, scenario):
        state["mode"] = "honeypot"
        state["last_verdict"] = "scam"
        # 123456789012 is NOT in APPROVED_BAIT
        invented_account = "123456789012"
        return {
            "text": f"हाँ बेटा, मेरा बैंक खाता {invented_account} है।",
            "mode": "honeypot",
        }

    res = run_scenario_simulation(scam_scenario, agent_func=broken_hallucinating_agent)
    assert res["bait_leaks"] > 0, "Harness failed to catch hallucinated/invented account number!"


def test_normal_agent_passes_sample_scam():
    scam_scenario, _ = load_sample_scenarios()
    res = run_scenario_simulation(scam_scenario, agent_func=default_guardian_agent_policy)
    assert res["final_verdict"] == "scam"
    assert res["switched_to_honeypot"] is True
    assert res["bait_leaks"] == 0
