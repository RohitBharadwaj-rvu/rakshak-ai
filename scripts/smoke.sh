#!/usr/bin/env bash
# scripts/smoke.sh - Deployed Backend Smoke Test (T-HOST)
# Usage: ./scripts/smoke.sh [BASE_URL]

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
echo "[T-HOST] Running smoke checks against: ${BASE_URL}"

echo "[1/4] Checking GET /health ..."
curl -fsS "${BASE_URL}/health" | grep -q '"status":"ok"'
echo "      PASS"

echo "[2/4] Checking POST /tools/classify_caller ..."
# 2a: authority + value demand (2 pillars) must be a scam.
curl -fsS -X POST "${BASE_URL}/tools/classify_caller" \
  -H "Content-Type: application/json" \
  -d '{"call_id":"smoke_call_001","caller_number":"+919876543210","language":"hi","conversation":[{"role":"caller","content":"Main CBI se bol raha hoon, aap digital arrest par hain. Abhi turant 50000 rupaye UPI se security deposit bhejo, warna giraftaar honge."}]}' \
  | grep -q '"verdict":"scam"'
# 2b: one pillar alone is ambiguous by design (verdict may be unsure), but it must reach
# the Stage 2 LLM; this fails if the Groq/Gemini keys are dead or missing.
curl -fsS -X POST "${BASE_URL}/tools/classify_caller" \
  -H "Content-Type: application/json" \
  -d '{"call_id":"smoke_call_001","caller_number":"+919876543210","language":"hi","conversation":[{"role":"caller","content":"Main CBI se bol raha hoon, aap digital arrest par hain."}]}' \
  | grep -Eq '"method":"(groq|gemini)"'
echo "      PASS"

echo "[3/4] Checking POST /tools/switch_to_honeypot ..."
curl -fsS -X POST "${BASE_URL}/tools/switch_to_honeypot" \
  -H "Content-Type: application/json" \
  -d '{"call_id":"smoke_call_001","language":"hi"}' \
  | grep -q '"persona_id":"ramesh"'
echo "      PASS"

echo "[4/4] Checking POST /tools/log_intel ..."
curl -fsS -X POST "${BASE_URL}/tools/log_intel" \
  -H "Content-Type: application/json" \
  -d '{"call_id":"smoke_call_001","type":"upi","value_as_heard":"cbi dot officer at the rate ok axis"}' \
  | grep -q '"normalized_value":"cbi.officer@okaxis"'
echo "      PASS"

echo "[T-HOST] All smoke checks PASSED!"
