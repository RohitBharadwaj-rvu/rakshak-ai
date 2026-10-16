import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.classifier_router import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_classifier_health_endpoint():
    response = client.get("/tools/classify_caller/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "hybrid_stages" in data


def test_api_classify_caller_scam():
    payload = {
        "call_id": "call_scam_test",
        "caller_number": "+919876543210",
        "conversation": [
            {"role": "assistant", "content": "Hello, GuardianLine here."},
            {
                "role": "caller",
                "content": "This is Inspector Sharma from CBI. You are under digital arrest. Transfer 50000 rupees to the safe account immediately.",
            },
        ],
        "language": "en",
    }
    response = client.post("/tools/classify_caller", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["call_id"] == "call_scam_test"
    assert data["verdict"] == "scam"
    assert data["confidence"] >= 0.85
    assert data["latency_ms"] < 200.0  # Heuristic sub-second response
    assert len(data["pillars_detected"]) >= 2


def test_api_classify_caller_genuine():
    payload = {
        "call_id": "call_gen_test",
        "caller_number": "+919810098100",
        "conversation": [
            {"role": "assistant", "content": "नमस्ते, आप कौन बात कर रहे हैं?"},
            {
                "role": "caller",
                "content": "नमस्ते, मैं डॉ सुंदरम क्लिनिक से बोल रहा हूँ। आपका कल सुबह 10 बजे रूटीन डॉक्टर चेकअप अपॉइंटमेंट है।",
            },
        ],
        "language": "hi",
    }
    response = client.post("/tools/classify_caller", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["call_id"] == "call_gen_test"
    assert data["verdict"] == "genuine"
    assert data["confidence"] <= 0.20


def test_api_classify_caller_empty_conversation():
    payload = {
        "call_id": "call_empty_test",
        "caller_number": "",
        "conversation": [],
        "language": "hi",
    }
    response = client.post("/tools/classify_caller", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "unsure"
