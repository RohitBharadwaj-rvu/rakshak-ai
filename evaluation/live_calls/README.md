# Live Calls Evaluation Directory

Store all live audio test call records, exported Bolna transcripts, and webhook payloads here.

## File Naming Convention
- `call_<YYYYMMDD_HHMMSS>_<scenario_id>.json`
  - Example: `call_20261018_131500_scam_digital_arrest_hi.json`
  - Example: `call_20261018_132000_genuine_delivery_otp_hi.json`
  - Example: `call_20261018_132500_genuine_clinic_hi.json`

## Required Format per Export
```json
{
  "call_id": "bolna-call-guid-or-timestamp",
  "scenario_id": "scam_digital_arrest_hi",
  "caller_number": "+919876543210",
  "language": "hi",
  "duration_seconds": 124,
  "transcript": [
    {"role": "user", "message": "मैं CBI क्राइम ब्रांच से बोल रहा हूँ..."},
    {"role": "assistant", "message": "नमस्ते बेटा, मैं तो रिटायर्ड हूँ..."}
  ],
  "tool_calls": [
    {
      "name": "log_intel",
      "arguments": {
        "upi_id": "cbi.officer.verma@okaxis",
        "scam_type": "digital_arrest"
      }
    }
  ],
  "agent_verdict": "scam",
  "actual_verdict": "scam"
}
```
