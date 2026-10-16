import pytest
from app.voice.classifier import classify_caller, CallerClassificationResult


def test_classify_caller_scam_heuristic():
    dialogue = [
        {"role": "assistant", "content": "नमस्ते, आप कौन बोल रहे हैं?"},
        {
            "role": "user",
            "content": "मैं CBI क्राइम ब्रांच से बोल रहा हूँ। आप डिजिटल अरेस्ट पर हैं। तुरंत पचास हज़ार सरकारी सेफ खाते में ट्रांसफर करो।",
        },
    ]
    res = classify_caller(
        call_id="test_scam_001",
        caller_number="+919876543210",
        conversation=dialogue,
        language="hi",
    )
    assert isinstance(res, CallerClassificationResult)
    assert res.verdict == "scam"
    assert res.confidence >= 0.85
    assert res.latency_ms < 50.0  # Heuristic should be ultra-fast (<50ms)
    assert "authority_coercion" in res.pillars_detected or "value_demand" in res.pillars_detected


def test_classify_caller_genuine_service():
    dialogue = [
        {"role": "assistant", "content": "हेलो, मैं शर्मा जी का असिस्टेंट बोल रहा हूँ।"},
        {
            "role": "user",
            "content": "भैया मैं ब्लू डार्ट डिलीवरी से बात कर रहा हूँ। आपका अमेज़न वाला पार्सल लेकर आया हूँ। मेन गेट गार्ड रूम में दे दूँ?",
        },
    ]
    res = classify_caller(
        call_id="test_gen_001",
        caller_number="+919810098100",
        conversation=dialogue,
        language="hi",
    )
    assert isinstance(res, CallerClassificationResult)
    assert res.verdict == "genuine"
    assert res.confidence <= 0.20
    assert res.latency_ms < 50.0


def test_classify_caller_early_turn_unsure():
    dialogue = [
        {"role": "assistant", "content": "नमस्ते, GuardianLine असिस्टेंट। आप कौन बात कर रहे हैं?"},
        {"role": "user", "content": "नमस्ते जी, क्या शर्मा जी से बात हो सकती है?"},
    ]
    res = classify_caller(
        call_id="test_unsure_001",
        caller_number="+919999988888",
        conversation=dialogue,
        language="hi",
    )
    assert isinstance(res, CallerClassificationResult)
    # Early non-committal turn should be unsure so receptionist keeps screening
    assert res.verdict == "unsure"
    assert 0.20 < res.confidence < 0.85


def test_classify_caller_english_scam():
    dialogue = [
        {"role": "assistant", "content": "Hello, who is calling please?"},
        {
            "role": "user",
            "content": "This is CBI Crime Branch Inspector Vikram. You are under immediate digital arrest. Transfer fifty thousand rupees to the safe verification account right now.",
        },
    ]
    res = classify_caller(
        call_id="test_en_scam_001",
        caller_number="+919845012345",
        conversation=dialogue,
        language="en",
    )
    assert res.verdict == "scam"
    assert res.confidence >= 0.85


def test_classify_caller_never_crashes_on_empty_input():
    res = classify_caller(
        call_id="empty_call",
        caller_number="",
        conversation=[],
        language="hi",
    )
    assert isinstance(res, CallerClassificationResult)
    assert res.verdict == "unsure"


def test_classify_caller_novel_scam_detected_by_llm_stage(monkeypatch):
    """
    Scammers invent novel pretexts with zero keywords (no 'CBI', no 'police', no 'UPI').
    Stage 1 heuristics will return None, falling through to Stage 2 LLM semantic reasoning.
    """
    novel_dialogue = [
        {"role": "assistant", "content": "Hello, who is calling?"},
        {
            "role": "user",
            "content": (
                "I am senior audit commissioner Trivedi from the State Heritage Estate Registry. "
                "Your ancestral property allotment was flagged for municipal non-compliance. "
                "An administrative seizure lien will be enforced on your family house within two hours "
                "unless you remit the mandatory clearance fee of thirty thousand to our official clearance routing ID."
            ),
        },
    ]

    # Mock Stage 2 LLM call (e.g., Groq / Gemini response)
    def mock_call_groq(text, api_key, timeout=1.2):
        return {
            "verdict": "scam",
            "confidence": 0.94,
            "reason": "Novel extortion: Impersonating estate commissioner with immediate deadline and financial demand",
            "pillars_detected": ["authority_coercion", "artificial_urgency", "value_demand"],
        }

    monkeypatch.setenv("GROQ_API_KEY", "mock_groq_key_123")
    monkeypatch.setattr("app.voice.classifier._call_groq", mock_call_groq)

    res = classify_caller(
        call_id="novel_scam_001",
        caller_number="+919876500000",
        conversation=novel_dialogue,
        language="en",
    )

    assert isinstance(res, CallerClassificationResult)
    assert res.verdict == "scam"
    assert res.confidence >= 0.85
    assert res.method == "groq"
    assert "authority_coercion" in res.pillars_detected
    assert "value_demand" in res.pillars_detected

