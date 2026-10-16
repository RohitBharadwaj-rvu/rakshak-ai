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


def test_classify_caller_tamil_scam():
    dialogue = [
        {"role": "assistant", "content": "வணக்கம், யார் பேசுகிறீர்கள்?"},
        {
            "role": "user",
            "content": "நான் சென்னை சைபர் கிரைம் இன்ஸ்பெக்டர். நீங்கள் டிஜிட்டல் அரெஸ்டில் வைக்கப்பட்டுள்ளீர்கள். உடனடியாக யுபிஐ மூலம் பணம் அனுப்பவும்.",
        },
    ]
    res = classify_caller(
        call_id="test_ta_scam_001",
        caller_number="+919845012345",
        conversation=dialogue,
        language="ta",
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
