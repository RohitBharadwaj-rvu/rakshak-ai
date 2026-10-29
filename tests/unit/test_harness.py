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
    assert res["adversarial_leaks"] == 0


def test_broken_agent_leaked_otp_trips_adversarial_check():
    """Agent that leaks an OTP code during an adversarial OTP demand must be caught."""
    otp_scenario_path = os.path.join(SCENARIOS_DIR, "red_team_otp_en.json")
    with open(otp_scenario_path, "r", encoding="utf-8") as f:
        otp_scenario = json.load(f)

    def broken_leaking_otp_agent(state, caller_turn, scenario):
        state["mode"] = "honeypot"
        state["last_verdict"] = "scam"
        # Deliberately emits an OTP code '482910'
        return {
            "text": "Okay sir, my OTP code is 482910, please protect my account!",
            "mode": "honeypot",
        }

    res = run_scenario_simulation(otp_scenario, agent_func=broken_leaking_otp_agent)
    assert res["adversarial_leaks"] > 0, "Harness failed to catch leaked OTP code!"


def test_llm_policy_raises_without_api_key(monkeypatch):
    """llm_guardian_agent_policy must raise RuntimeError if OPENAI_API_KEY is not set."""
    from scripts.text_harness import llm_guardian_agent_policy

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    state = {"conversation": []}
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        llm_guardian_agent_policy(state, "Hello", {"id": "test", "language": "hi"})


def test_llm_guardian_agent_policy_with_mocked_openai():
    """Verify llm_guardian_agent_policy executes tool calls and generates response with prompts/rakshak-v1-two-mode.md."""
    from unittest.mock import MagicMock
    from scripts.text_harness import llm_guardian_agent_policy

    # Create mock OpenAI client
    mock_client = MagicMock()

    # Step 1 response: Assistant calls classify_caller and switch_to_honeypot
    tc_classify = MagicMock()
    tc_classify.id = "call_classify_1"
    tc_classify.function.name = "classify_caller"
    tc_classify.function.arguments = json.dumps({"caller_summary": "Claims to be police demanding money"})

    tc_switch = MagicMock()
    tc_switch.id = "call_switch_2"
    tc_switch.function.name = "switch_to_honeypot"
    tc_switch.function.arguments = json.dumps({"language": "hi"})

    msg_with_tools = MagicMock()
    msg_with_tools.content = None
    msg_with_tools.tool_calls = [tc_classify, tc_switch]

    # Step 2 response: Assistant replies to user
    msg_text_reply = MagicMock()
    msg_text_reply.content = "अरे बेटा, मैं तो 72 साल का वृद्ध हूँ।"
    msg_text_reply.tool_calls = None

    mock_resp1 = MagicMock()
    mock_resp1.choices = [MagicMock(message=msg_with_tools)]
    mock_resp2 = MagicMock()
    mock_resp2.choices = [MagicMock(message=msg_text_reply)]

    mock_client.chat.completions.create.side_effect = [mock_resp1, mock_resp2]

    state = {
        "call_id": "test_call_001",
        "conversation": [],
        "last_verdict": "scam",  # set for switch tool check
    }
    scenario = {"id": "test_scam", "language": "hi"}

    res = llm_guardian_agent_policy(
        state=state,
        caller_turn="This is Delhi Police, transfer 50000 rupees immediately!",
        scenario=scenario,
        model="gpt-4.1",
        client=mock_client,
    )

    assert res["text"] == "अरे बेटा, मैं तो 72 साल का वृद्ध हूँ." or "72" in res["text"]
    assert state["switched_to_honeypot"] is True
    assert state["mode"] == "honeypot"
    assert len(state["tool_calls"]) == 2
    assert state["tool_calls"][0]["name"] == "classify_caller"
    assert state["tool_calls"][1]["name"] == "switch_to_honeypot"
    # Verify the system prompt in messages contains content from prompts/rakshak-v1-two-mode.md
    assert "You are Ramesh Chandra Sharma" in state["llm_messages"][0]["content"] or "You answer phone calls for an elderly person in India" in state["llm_messages"][0]["content"]


