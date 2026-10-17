# GuardianLine Cross-Lane Interface Specification

**Status:** Frozen (Sprint 0 · Oct 17, 2026)  
**Owners:** Lane B (Backend & Intel) & Lane A (Voice Agent)  
**Validation Suite:** `T-CONTRACT` (`tests/contract/test_contracts.py` against `contracts/*.schema.json`)

Every producer and consumer across Lanes A, B, C, and D is tested against the JSON Schemas in `contracts/`. Every schema carries a `version` string (`1.0.0`). Any breaking change requires a schema version bump and a heads-up to all affected lanes.

---

## 1. Authentication & Privacy Rules (`T-PRIV`)

- **Public Health Check:** `GET /health` and `GET /tools/classify_caller/health` are public (`200 OK`).
- **Bolna Tool & Webhook Endpoints (`/tools/*`, `/webhook`):**
  - When `BOLNA_WEBHOOK_SECRET` is set in the environment, requests must pass it via `Authorization: Bearer <secret>`, `X-Bolna-Secret: <secret>`, or query parameter `?secret=<secret>`.
  - In local development / test mode where `BOLNA_WEBHOOK_SECRET` is unset or empty, requests are allowed without a header so local harnesses and `TestClient` suites run seamlessly.
- **Phone Number Masking in Logs:**
  - All backend logs mask caller phone numbers except the last 4 digits (e.g., `******3210`).
  - Full caller numbers are retained inside `CallRecord` so the 1930 cybercrime report has complete evidence.

---

## 2. Mid-Call Tool 1: `classify_caller` (Bolna $\rightarrow$ Backend, Owner: D & B)

- **Endpoint:** `POST /tools/classify_caller`
- **Schemas:**
  - Request: `contracts/classify_caller_request.schema.json`
  - Response: `contracts/classify_caller_response.schema.json`
- **Behavior:**
  - Evaluates caller utterances using Stage 1 heuristics and Stage 2 LLM semantic invariants.
  - Enforces a strict latency budget (`max_latency_budget_s`, default `1.4s`, hard ceiling `1.5s`). If the classifier times out or errors, returns `"verdict": "unsure"` so the live call never hangs.
  - Missing required fields (`call_id`) return HTTP `422` naming the missing field.

### Request Example
```json
{
  "call_id": "call_live_9872",
  "caller_number": "+919876543210",
  "language": "hi",
  "conversation": [
    {"role": "caller", "content": "Main CBI crime branch se bol raha hoon, aap digital arrest par hain."}
  ]
}
```

### Response Example
```json
{
  "call_id": "call_live_9872",
  "verdict": "scam",
  "confidence": 0.96,
  "reason": "Heuristic trigger on scam behavioral pillars: authority_coercion",
  "latency_ms": 1.2,
  "method": "heuristic",
  "pillars_detected": ["authority_coercion"]
}
```

---

## 3. Mid-Call Tool 2: `switch_to_honeypot` (Bolna $\rightarrow$ Backend, Owner: B)

- **Endpoint:** `POST /tools/switch_to_honeypot`
- **Schemas:**
  - Request: `contracts/switch_to_honeypot_request.schema.json`
  - Response: `contracts/switch_to_honeypot_response.schema.json`
- **Behavior:**
  - Returns an elderly honeypot persona (`ramesh`, `sunita`, or `iyer`), in-character spoken stalling lines (`persona_lines`), and fake bait credentials from the approved bait list (`APPROVED_BAIT`).
  - **Idempotent per `call_id`:** A second call with the same `call_id` always returns the exact same persona and bait details.
  - **Language fallback:** Unknown or unsupported language codes automatically fall back to `"hi"` (Hindi).
  - Missing `call_id` returns HTTP `422` naming `call_id`.

### Request Example
```json
{
  "call_id": "call_live_9872",
  "language": "hi"
}
```

### Response Example
```json
{
  "call_id": "call_live_9872",
  "language": "hi",
  "persona_id": "ramesh",
  "persona_name": "Ramesh Sharma",
  "persona_age": 72,
  "persona_city": "Lucknow",
  "persona_lines": [
    "अरे बाप रे! बेटा ज़रा धीरे-धीरे बोलो, मैं चश्मा लगाकर डायरी में लिख रहा हूँ।",
    "मेरा हाथ काँप रहा है बेटा, एक-एक अंक आराम से बोलिए।"
  ],
  "fake_bait": {
    "upi_id": "ramesh.elderly@okhdfc",
    "account_number": "9999000011112222",
    "ifsc_code": "HDFC0009999",
    "phone_number": "9000011111"
  }
}
```

---

## 4. Mid-Call Tool 3: `log_intel` (Bolna $\rightarrow$ Backend, Owner: B)

- **Endpoint:** `POST /tools/log_intel`
- **Schemas:**
  - Request: `contracts/log_intel_request.schema.json`
  - Response: `contracts/log_intel_response.schema.json`
- **Behavior:**
  - Captures mid-call intelligence (`upi`, `phone`, `account`, `ifsc`, `link`, `pan`, `other`) as heard by the voice agent.
  - Runs the deterministic spoken-number normalizer (`app/voice/normalizer.py`) on `value_as_heard` and stores both `value_as_heard` and `normalized_value`.
  - **Never rejects unparseable values:** If `value_as_heard` cannot be validated into canonical format, it is stored with `"unparseable": true` so no evidence is ever lost mid-call.
  - **Pending record creation:** If `log_intel` arrives for a `call_id` that has not yet received its post-call webhook, a pending `CallRecord` is created in SQLite and merged when the webhook arrives.
  - Missing required fields (`call_id`, `type`, `value_as_heard`) return HTTP `422` naming the field.

### Request Example
```json
{
  "call_id": "call_live_9872",
  "type": "upi",
  "value_as_heard": "cbi dot officer dot verma at the rate ok axis"
}
```

### Response Example
```json
{
  "status": "logged",
  "call_id": "call_live_9872",
  "type": "upi",
  "value_as_heard": "cbi dot officer dot verma at the rate ok axis",
  "normalized_value": "cbi.officer.verma@okaxis",
  "unparseable": false
}
```

---

## 5. Post-Call Webhook (Bolna $\rightarrow$ Backend, Owner: B)

- **Endpoint:** `POST /webhook`
- **Schema:** `contracts/webhook.schema.json`
- **Behavior:**
  - Ingests the completed Bolna call payload (`call_id`, `agent_id`, `caller_number`, `call_duration`, `call_status`, `call_recording_url`, `transcript`, `metadata`).
  - **Idempotent:** Repeated deliveries of the same `call_id` update/return the single existing `CallRecord` without creating duplicates, and fire `call.finalized` at most once.
  - **Pre-webhook merge:** Any `log_intel` captures or `switch_to_honeypot` persona assignments recorded mid-call for `call_id` are merged into the final `CallRecord`.
  - **Withheld caller number:** If `caller_number` is empty or missing, `caller_number` is stored as `""` and `caller_number_missing` is set to `true` for carrier coverage tracking.
  - **Fast response (< 1s):** Heavy post-call tasks run asynchronously so even a 60-minute transcript answers in under 1 second.
  - **Malformed payload:** Returns HTTP `400` (`Bad Request`), logs the error with `call_id` if present, and keeps the server healthy.

---

## 6. `CallRecord` Store & Read API (Owner: B, Read by A, C, D)

- **Schema:** `contracts/call_record.schema.json`
- **Storage:** SQLite (`guardianline_calls.db` by default, configurable via `GUARDIANLINE_DB_PATH`).
- **Endpoints:**
  - `GET /api/calls`: Lists `CallRecord` items newest-first (up to 50 per page), optional `?verdict=scam|genuine|unsure` filter.
  - `GET /api/calls/{call_id}`: Returns full `CallRecord` JSON, or `404` if unknown.

---

## 7. `call.finalized` Event (Backend $\rightarrow$ Alerts & Dashboard, Owner: B to C)

- **Schema:** `contracts/call_finalized.schema.json`
- **Behavior:**
  - Fired exactly once per `call_id` when its `CallRecord` transitions to `finalized`.
  - Subscribers (such as Lane C's family alert service in `app/notify/`) can register in-process callbacks via `register_call_finalized_listener(fn)` or inspect the event log.
