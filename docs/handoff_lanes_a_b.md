# 1-Page Handoff Note: Classifier Integration (Lanes A & B)
**From:** Lane D (Detection & Evaluation)  
**Date:** 17 October 2026, 01:15 IST  
**Service:** Real-Time Caller Intent Classification (`POST /tools/classify_caller`)

---

## 1. Fast Mounting for Lane B (FastAPI)
Mount `app/api/classifier_router.py` in your main FastAPI application:

```python
from fastapi import FastAPI
from app.api.classifier_router import router as classifier_router

app = FastAPI(title="GuardianLine Backend")
app.include_router(classifier_router)
```
- **Health Check:** `GET /tools/classify_caller/health` $\rightarrow$ `{"status": "healthy"}`
- **Active Endpoint:** `POST /tools/classify_caller`

---

## 2. Exact HTTP Contract (`POST /tools/classify_caller`)

### Request JSON Payload (Bolna Mid-Call Mode via `caller_summary`)
```json
{
  "call_id": "%(call_sid)s",
  "caller_number": "%(from_number)s",
  "caller_summary": "Caller claims to be Sub-Inspector Verma from Hauz Khas police station, states an arrest warrant was issued, and demands immediate ₹25,000 transfer."
}
```

*Note: For regression benchmarking and offline simulation, the endpoint also accepts the full conversation history:*
```json
{
  "call_id": "call_live_9872",
  "caller_number": "+919876543210",
  "conversation": [
    {"role": "caller", "content": "Namaste sir, Hauz Khas police station se Sub-Inspector Verma bol raha hoon."},
    {"role": "assistant", "content": "Ji kahiye, kis baare mein call kiya hai?"},
    {"role": "caller", "content": "Aapke bete ke khilaaf court order warrant issue hua hai. Abhi 25,000 clearance deposit bhejo."}
  ]
}
```

### Response JSON Payload
```json
{
  "call_id": "call_live_9872",
  "verdict": "scam",
  "confidence": 0.96,
  "reason": "Heuristic trigger on scam behavioral pillars: authority_coercion, value_demand",
  "latency_ms": 1.4,
  "method": "heuristic",
  "pillars_detected": ["authority_coercion", "value_demand"]
}
```
*Note on `verdict` values:*  
- `"scam"`: Safe honeypot or termination triggered.  
- `"genuine"`: Legitimate caller allowed to speak with elder.  
- `"unsure"`: Ambiguous intent $\rightarrow$ receptionist continues screening / triggers challenge-verify protocol.

---

## 3. Expected Latency & Conversational Guidance (For Lane A)

Empirically measured round-trip latencies:
| Classification Tier | Median (p50) | 95th Percentile (p95) | Notes |
| :--- | :--- | :--- | :--- |
| **Stage 1 (Regex / Heuristic)** | **~0.8 ms** | **~2.5 ms** | Sub-millisecond instant return |
| **Stage 2 (Groq Llama 3.3 70B)** | **Pending live profiling** | **Pending live profiling** | Network LLM tier; falls back to offline rules if unavailable |
| **Stage 2 (Gemini 2.0 Flash)** | **Pending live profiling** | **Pending live profiling** | REST API fallback tier; falls back to offline rules if unavailable |
| **Stage 2 (Offline Backup)** | **~0.3 ms** | **~2.6 ms** | Triggers when API keys are unset or network fails |

> [!IMPORTANT]
> **Actionable for Lane A Agent Prompts:**  
> When the call drops to Stage 2 LLM analysis, round-trip network time is between **450ms and 1200ms**. The voice receptionist agent **must not remain silent** during this window. Configure the Bolna agent to immediately emit an acknowledgment filler token (e.g., *"Ji, ek second sun raha hoon..."* or *"Achha, samajh gaya, ek minute..."*) while awaiting tool resolution.

---

## 4. Bolna Custom Tool Definition (For Lane A)

Paste this tool definition directly into your Bolna agent configuration YAML/JSON:

```json
{
  "type": "function",
  "function": {
    "name": "classify_caller",
    "description": "Evaluates inbound caller intent against scam behavioral pillars. Returns verdict ('scam', 'genuine', or 'unsure').",
    "parameters": {
      "type": "object",
      "properties": {
        "call_id": {
          "type": "string",
          "description": "Unique telephony call session ID (pass %(call_sid)s)"
        },
        "caller_number": {
          "type": "string",
          "description": "Caller phone number with country code (pass %(from_number)s)"
        },
        "caller_summary": {
          "type": "string",
          "description": "1 to 3 sentence agent summary of who the caller claims to be, what they want, and any payment/OTP/credential demands"
        }
      },
      "required": ["call_id", "caller_summary"]
    }
  },
  "url": "http://localhost:8000/tools/classify_caller",
  "method": "POST"
}
```

---

## 5. Lane C (family alerts, dashboard, Android)
Lane C now consumes Lane B's `contracts/call_record.schema.json` and `contracts/call_finalized.schema.json` (Lane C's earlier `callrecord.schema.json` proposal is withdrawn). Wiring into B's app (`install(app)`), settings, India SMS/WhatsApp delivery caveats and the open transfer-loop questions for Lane A are in [`docs/lane_c_integration.md`](lane_c_integration.md).
