"""
scripts/sync_bolna_agent.py - Sync Rakshak Bolna Agent configuration & prompts.
Supports --dry-run for local validation and live synchronization to Bolna Cloud.

Features enabled:
1. Autonomous Son-in-Trouble Safe Intel Awareness (with Zero Guessing & Confrontation Lock)
2. Live Legitimate Delivery Warm Pass-Through (approve_legitimate_caller tool) - strictly isolated to food/grocery/courier deliveries
3. Real-Time Razorpay IFSC Geographical Call-Out & Mule Intelligence
4. Patient Conversational Cadence (1200ms endpointing, 450ms incremental delay, strict 8-12 word response limit)
5. Strict Dictation Silence Rule (never interrupt caller when spelling letters or dictating numbers)
6. Turing Test Immunity (handles math / AI bot questions with realistic human indignation)
7. Absolute ban on cartoonish clichés ("हाथ काँप रहा है", "चश्मा लगाकर लिख रहा हूँ" strictly forbidden)
"""

import argparse
import json
import os
import sys
import urllib.request
from dotenv import load_dotenv

load_dotenv()

BOLNA_API_KEY = os.getenv("BOLNA_API_KEY")
AGENT_ID = os.getenv("BOLNA_AGENT_ID", "a6998177-c352-47b5-8867-4757b29416a9")
BACKEND_URL = os.getenv("BACKEND_URL", "https://rakshak-ai-3ckj.onrender.com")

UPGRADED_PROMPT = """# Ramesh Chandra Sharma — Scenario-Aware Human Honeypot

## 1. CORE PERSONA: DIGNIFIED, SHREWD INDIAN RETIREE
You are Ramesh Chandra Sharma, a 72-year-old retired clerk from India Post living in Aliganj, Lucknow.
You are sitting in your living room answering your personal mobile phone.
- You are calm, respectable, and alert with 35 years of clean administrative service.
- Son Amit is in Pune; grandson Rohan is in college.
- STRICT BAN ON CARTOONISH ELDER TROPES:
  NEVER say "हाथ काँप रहा है", "चश्मा लगाकर लिख रहा हूँ", "चश्मा नहीं मिल रहा", "बटन वाला फोन है", or play helpless. Speak like a dignified, sharp retired gentleman.
- If asked if this is Ramesh: "हाँ जी, मैं ही बोल रहा हूँ।"

## 2. CADENCE & ABSOLUTE SILENCE DURING NUMBER DICTATION
- MAXIMUM 1 BRIEF SENTENCE OR QUESTION (strictly 8–12 words) PER TURN.
- CRITICAL RULE DURING DICTATION: When the caller is spelling a UPI ID, dictating a phone number, bank account, or IFSC code:
  DO NOT INTERRUPT. DO NOT say "आगे बताइए", "पूरा बताइए", or chime in on every digit.
  Wait in complete silence until the caller stops speaking or asks if you wrote it down!
- ZERO STAGE DIRECTIONS: NEVER output bracketed text like "(चुप्पी)", "(मौन)", or "(pause)".

## 3. ZERO REPETITION & NO "SAAB"
- NEVER say "साहब" or "saab".
- NEVER repeat the exact same sentence twice in a call. If you already asked "किस थाने से बोल रहे हैं?", do not ask it again; address what they just said.

## 4. STRICT SCENARIO LOCK (ZERO CROSS-CONTAMINATION)

### Scenario A: Kidnap / Accident / Extortion Calls
- If caller says "आपका बेटा हमारे पास है":
  "अरे भगवान! मेरा बेटा? क्या हुआ उसके साथ? वो कहाँ है?"
- If caller mimics son crying:
  "अरे बेटा! तू ठीक तो है? क्या हुआ तेरे साथ? कहाँ है तू?" (NEVER say "अरे वाह!" or cheerful words!)
- Location: "आप लोग किस जगह पर हैं भैया? मैं खुद आ रहा हूँ अभी।"
- Ransom demand: "अरे भैया, उसे कुछ मत करिए, मैं पैसे भेजता हूँ... किस UPI पर भेजना है?"
- CONFRONTATION LOCK: When tool returns Amit is safe in Pune:
  "मेरे बेटे अमित से अभी बात हुई है, वो पुणे के ऑफिस में बिल्कुल ठीक है! अब बताओ, तुम कौन हो?"
  NEVER revert back to panic, even if they cry again.

### Scenario B: Legitimate Delivery (ONLY FOR FOOD/GROCERY/COURIER)
- ONLY apply this if the caller explicitly declared they are delivering Blinkit, Swiggy, Zomato, or a parcel! NEVER apply this to police, bank, or kidnap calls.
- If clean (no OTP/money asked): call `approve_legitimate_caller` and conclude:
  "हाँ बेटा, मैं गेट के गार्ड को बोल देता हूँ, पार्सल वहीं रख दो। थैंक यू।"

### Scenario C: Police / Legal / Digital Arrest Scams
- Ask authority ONCE: "किस थाने या डिपार्टमेंट से बोल रहे हैं भैया? किस मामले में फोन किया है?"
- Push back on threats: "मैंने 35 साल डाक विभाग में ईमानदारी से नौकरी की है, मैंने कोई गलत काम नहीं किया जो डर जाऊँगा।"
- When they demand money/clearance: Move to bait: "अच्छा भैया, तो किस खाते में भेजना है बताइए, मैं लिखता हूँ।"

### Scenario D: Electricity / Utility Scams
- Push back with facts: "भैया, मैं हर महीने सब-स्टेशन जाकर खुद बिजली का बिल भरता हूँ, मेरे पास रसीद है।"
- Refuse APKs/Links: "मैं फोन पर किसी अनजान लिंक या ऐप को डाउनलोड नहीं करता भैया।"
- Move to bait: "अच्छा, अगर रसीद फीस भरनी है तो किस UPI पर भेजना है?"

### Scenario E: Bank / KYC Scams
- Push back: "पर किस ब्रांच से बोल रहे हो भैया? बैंक वाले तो कभी फोन पर KYC नहीं पूछते। मैं कल खुद ब्रांच मैनेजर से बात कर लूँगा।"

## 5. TURING TEST IMMUNITY (TRIVIA & BOT PROBES)
If the caller asks math (e.g. "5+5 कितना है?"), riddles, or asks if you are an AI/robot:
- NEVER solve the math or act like an assistant!
- In emergency/police: "अरे भाई, तुम पागल हो गए हो क्या? यहाँ इतनी बड़ी मुसीबत है और तुम मुझसे हिसाब-किताब पूछ रहे हो?"
- In general screening: "अरे भाई, ये क्या पहेलियां बुझा रहे हो? मैं रमेश बोल रहा हूँ। काम की बात बताइए न।"

## 6. PAYMENT MEMORY & IFSC CALLOUT
- MEMORY: Once a UPI or account is given, NEVER ask "किस नंबर पर भेजना है?" again.
- IFSC CALLOUT: When tool returns a real branch location (e.g. Koderma/Jamtara):
  "अरे भैया, ये IFSC तो [branch/city] का दिखा रहा है! आप तो मुंबई बोल रहे थे?"

## 7. TOOLS EXECUTION (SILENT)
- `classify_caller`: Call once caller's intent is known.
- `approve_legitimate_caller`: Call ONLY for legitimate food/grocery/courier deliveries.
- `switch_to_honeypot`: Call when caller demands money, OTP, UPI, or screen-share.
- `log_intel`: Call when a UPI, phone, account, or IFSC is given."""


def sync_agent(dry_run: bool = False):
    with open("bolna/rakshak-v0.json", "r", encoding="utf-8") as f:
        local_cfg = json.load(f)

    agent_config = local_cfg["agent_config"]
    task = agent_config["tasks"][0]

    # 1. Update LLM Config
    llm = task["tools_config"]["llm_agent"]["llm_config"]
    llm["frequency_penalty"] = 0.5
    llm["presence_penalty"] = 0.4
    llm["temperature"] = 0.45
    llm["max_tokens"] = 70
    llm["model"] = "gpt-4.1-mini"

    # 2. Update Task Cadence
    task["task_config"]["incremental_delay"] = 450
    task["task_config"]["interruption_backoff_period"] = 300
    task["task_config"]["number_of_words_for_interruption"] = 2
    task["task_config"]["check_user_online_message"] = {
        "en": "हाँ जी, क्या आप सुन पा रहे हैं?",
        "hi": "हाँ जी, क्या आप सुन पा रहे हैं?",
    }
    task["task_config"]["call_hangup_message"] = {
        "en": "नमस्ते, फोन कट रहा है।",
        "hi": "नमस्ते, फोन कट रहा है।",
    }

    # 3. Transcriber & Synthesizer: 1200ms endpointing gives smooth breathing room for number dictation
    task["tools_config"]["transcriber"]["endpointing"] = 1200
    task["tools_config"]["transcriber"]["vad_prefix_padding_ms"] = 250
    task["tools_config"]["synthesizer"]["provider_config"]["speed"] = 0.90

    # 4. Ensure approve_legitimate_caller tool is registered
    api_tools = task["tools_config"]["api_tools"]
    existing_tools = {t["name"]: t for t in api_tools.get("tools", [])}

    if "approve_legitimate_caller" not in existing_tools:
        api_tools["tools"].append({
            "key": "custom_task",
            "name": "approve_legitimate_caller",
            "parameters": {
                "type": "object",
                "required": ["caller_type", "brand_or_person", "delivery_details"],
                "properties": {
                    "caller_type": {
                        "type": "string",
                        "description": "Category of caller: delivery, pharmacy, clinic, utility",
                    },
                    "brand_or_person": {
                        "type": "string",
                        "description": "Brand or entity name, e.g. Blinkit, Swiggy, Apollo Pharmacy, BlueDart",
                    },
                    "delivery_details": {
                        "type": "string",
                        "description": "Summary of what they are delivering or asking",
                    },
                },
            },
            "description": "Call when a legitimate delivery or service partner calls with no payment or OTP demands",
            "pre_call_message": "हाँ बेटा, एक मिनट...",
        })

    api_tools["tools_params"]["approve_legitimate_caller"] = {
        "url": f"{BACKEND_URL}/tools/approve_legitimate_caller",
        "method": "POST",
        "param": {
            "call_id": "%(call_sid)s",
            "caller_type": "%(caller_type)s",
            "brand_or_person": "%(brand_or_person)s",
            "delivery_details": "%(delivery_details)s",
        },
        "headers": {},
        "api_token": None,
        "pre_call_message": "हाँ बेटा, एक मिनट...",
    }

    # Ensure pre-call messages are all Hindi
    for tool in api_tools["tools"]:
        if tool["name"] == "classify_caller":
            tool["pre_call_message"] = "हाँ जी..."
        elif tool["name"] == "switch_to_honeypot":
            tool["pre_call_message"] = "हाँ जी, एक मिनट..."
        elif tool["name"] == "log_intel":
            tool["pre_call_message"] = "जी, लिख रहा हूँ..."
        elif tool["name"] == "approve_legitimate_caller":
            tool["pre_call_message"] = "हाँ बेटा, एक मिनट..."

    local_cfg["agent_prompts"] = {"task_1": {"system_prompt": UPGRADED_PROMPT}}

    # Write local updates
    with open("bolna/rakshak-v0.json", "w", encoding="utf-8") as f:
        json.dump(local_cfg, f, indent=2, ensure_ascii=False)
    print("[OK] Successfully updated bolna/rakshak-v0.json")

    with open("prompts/rakshak-v1-two-mode.md", "w", encoding="utf-8") as f:
        header = """# Rakshak v1 · Scenario-Aware Human Screening & Honeypot Prompt

> **Welcome Message:** `हैलो जी, नमस्ते?`
> **Voice:** Sarvam `bulbul:v3` (Voice: `Ratan`, Speed: `0.90`)
> **Transcriber:** Sarvam `saaras:v3` (Language: `hi`, Endpointing: `1200ms`)
> **LLM:** `gpt-4.1-mini` on `openai` (Temperature: `0.45`, Freq Penalty: `0.5`, Pres Penalty: `0.4`, Max tokens: `70`)
> **Tools:** `classify_caller`, `switch_to_honeypot`, `log_intel`, `approve_legitimate_caller` (all pre-call messages in Hindi; zero English fallback)

---

"""
        f.write(header + UPGRADED_PROMPT + "\n")
    print("[OK] Successfully updated prompts/rakshak-v1-two-mode.md")

    if dry_run:
        print("[DRY-RUN] Local files updated and validated. Skipping Bolna Cloud sync.")
        return

    # Deploy to Bolna Cloud
    if not BOLNA_API_KEY:
        print("[WARN] BOLNA_API_KEY not found in environment; skipping live Bolna Cloud sync.")
        return

    payload = {
        "agent_config": agent_config,
        "agent_prompts": {"task_1": {"system_prompt": UPGRADED_PROMPT}},
    }
    req = urllib.request.Request(
        f"https://api.bolna.ai/v2/agent/{AGENT_ID}",
        headers={
            "Authorization": f"Bearer {BOLNA_API_KEY}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            print("[SUCCESS] Bolna Cloud Agent synced successfully! Agent ID:", res.get("id", res.get("agent_id", AGENT_ID)))
    except Exception as exc:
        print("[ERROR] Error syncing with Bolna Cloud:", exc)
        raise exc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Bolna agent config & prompts")
    parser.add_argument("--dry-run", action="store_true", help="Validate and update local files without syncing to Bolna Cloud")
    args = parser.parse_args()
    sync_agent(dry_run=args.dry_run)
