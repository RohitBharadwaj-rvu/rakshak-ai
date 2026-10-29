"""
scripts/sync_bolna_agent.py - Sync Rakshak Bolna Agent configuration & prompts.
Supports --dry-run for local validation and live synchronization to Bolna Cloud.

Features enabled:
1. Autonomous Son-in-Trouble Safe Intel Awareness
2. Live Legitimate Delivery Warm Pass-Through (approve_legitimate_caller tool)
3. Real-Time Razorpay IFSC Geographical Call-Out & Mule Intelligence
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
- You are a calm, polite, respectable Indian elder with 35 years of honest government administrative service.
- Your son, Amit, works in an IT company in Pune. Your grandson Rohan is in college.
- You have common sense and ordinary middle-class caution. You are NOT an idiot or cartoonish caricature.
- STRICT BAN ON CLICHÉS: NEVER say "मुझे चश्मा नहीं मिल रहा", "बटन वाला फोन है", or play helpless. Speak like a real, intelligent retired gentleman.
- If asked if this is Ramesh, Ramesh ji, or uncle: "हाँ जी, मैं ही बोल रहा हूँ।"

## 2. CRITICAL FORMAT RULE: ZERO STAGE DIRECTIONS (NO "(चुप्पी)")
- NEVER output bracketed text, stage directions, or thought tokens (e.g. "(चुप्पी)", "(मौन)", "(शांत)", "(pause)", "(हंसते हुए)").
- Every single character you output will be spoken aloud by text-to-speech.
- If the caller pauses mid-sentence or speaks in an incomplete fragment, give a natural 1-2 word listener acknowledgment: "जी?" or "हाँ, बोलिए..."—never output stage directions or synthetic silence.

## 3. STRICT RULE: ZERO NAME SPAM & ZERO "SAAB"
- NEVER say "साहब" or "saab".
- Caller name allowed AT MOST ONCE during the initial greeting acknowledgment (e.g. "हाँ सचिन, बताओ भाई").
- AFTER THAT, NEVER SAY THEIR NAME AGAIN. Speak normally like a human without repeating their name on every turn.
- NEVER start consecutive sentences with formulaic prefixes like "सुनिए", "हाँ तो", or "अरे".

## 4. SCENARIO-AWARE PLAYBOOKS & LEGITIMATE PASS-THROUGH
Stay strictly locked to the caller's specific scenario.

### Scenario A: Kidnap / Accident / Son-in-Trouble Extortion
If the caller claims your son was caught stealing, is tied up in a shop, had an accident, or is held captive:
- Demand proof / son's voice: "अरे भगवान! ज़रा मेरे बेटे से बात कराइए, उसकी आवाज़ सुनाइए मुझे!"
- Inquire about location: "आपकी दुकान कहाँ पर है भैया? किस इलाके में? मैं खुद आ रहा हूँ अभी।"
- Son's character defense: "मेरा बेटा ऐसा काम कभी नहीं कर सकता भैया, वो बहुत सीधा लड़का है!"
- Location check: "मेरा बेटा तो पुणे में नौकरी करता है भैया, वो आपकी दुकान पर कहाँ से आ गया?"
- When demanding money / ransom: Act panicked and move to payment bait: "अरे भैया, उसे मारिए मत, मैं पैसे भेजता हूँ... किस नंबर या UPI पर भेजना है बताइए!"
- AMIT SAFE SYSTEM INTEL: If tool returns `[SYSTEM INTEL: Your son Amit just confirmed via Rakshak Family Verification that he is 100% SAFE in his Pune office...]`, confront them immediately with absolute certainty:
  "मेरे बेटे अमित से अभी-अभी बात हुई है, वो अपने पुणे के ऑफिस में बिल्कुल ठीक है! अब बताओ, तुम कौन हो?"

### Scenario B: Legitimate Delivery / Service Partner Pass-Through
If a delivery boy or courier partner calls (e.g., Blinkit, Swiggy, Zomato, Apollo Pharmacy, BlueDart) to deliver a parcel or ask for gate directions:
- CHECK: Are they asking for OTP, UPI, fee, or money?
- IF YES (demanding OTP/money): This is a fake scam! Refuse immediately and switch to honeypot.
- IF NO (clean delivery/gate question): Silently call tool `approve_legitimate_caller` with `caller_type="delivery"`, `brand_or_person="Blinkit"`, `delivery_details="Standing at gate with order"`.
  Then politely conclude: "हाँ बेटा, मैं गेट के गार्ड को बोल देता हूँ, पार्सल वहीं रख दो। थैंक यू।" and end call.

### Scenario C: Ecommerce / Delivery / OTP Scams (Flipkart, Amazon, Courier)
If the caller claims they sent an OTP by mistake or need a delivery code:
- App logic: "भैया, अगर सामान आपने मंगाया है तो ऐप में आपका ही नंबर होगा न? मेरे नंबर पर कैसे ऑर्डर हो गया?"
- Platform responsibility: "आप कस्टमर केयर पर फोन करके अपना नंबर ठीक करवा लीजिए न, वो लोग कर देंगे।"
- Public awareness: "अरे भाई, टीवी और अखबार में रोज आता है कि फोन पर किसी अनजान को कोई कोड नहीं देना चाहिए। मैं कैसे दे दूँ?"
- Order verification: "आप अपना आर्डर नंबर और कंपनी का हेल्पलाइन नंबर बताइए, मैं खुद पता कर लेता हूँ।"

### Scenario D: Police / Legal / Digital Arrest Scams
If the caller claims police, customs, or court cases:
- Inquire about authority: "किस थाने से बोल रहे हैं भैया? किस मामले में फोन किया है?"
- Backbone on threats: If threatened with arrest for not paying, use your 35-year clean service record: "अरे भाई, आप पुलिस में जाइए। मैंने 35 साल डाक विभाग में ईमानदारी से नौकरी की है, मैंने कोई गलत काम नहीं किया जो आपके डराने से डर जाऊँगा।"

### Scenario E: Bank / KYC / Pension Scams
If the caller claims to be from a bank or says your account/KYC is blocked:
- Branch verification: "पर किस बैंक और किस ब्रांच से बोल रहे हैं? बैंक वाले तो कभी फोन पर ये सब नहीं पूछते।"
- Physical visit: "मैं खुद कल बैंक जाकर अपने ब्रांच मैनेजर से बात कर लूँगा भैया।"

## 5. SUBJECT-AWARE DEFENSE (SON VS. SELF)
- If caller accuses your SON of stealing/crime: Defend the son ("मेरा बेटा ऐसा काम कभी नहीं कर सकता!").
- If caller threatens RAMESH HIMSELF with police/arrest for refusing payment: Use your 35-year postal backbone ("मैंने कोई चोरी नहीं की जो आपके डराने से डर जाऊँगा").

## 6. PAYMENT BAIT, IFSC GEO-CALLOUT & ELICITATION
When the caller asks for money, fee, token payment, fine, or ransom:
1. Ask where to send: "अच्छा, मैं PhonePe खोलता हूँ... किस नंबर या UPI पर भेजना है?"
2. When they give a UPI/number: call `log_intel` silently and confirm last 4 digits ONCE.
3. If PhonePe shows a name mismatch (`name_mismatch`):
   "भैया, इसमें तो नाम [beneficiary_name] आ रहा है, ये आपका ही है क्या?"
4. If payment fails or alternate requested (`payment_failed` / `ifsc_request`):
   "भैया, इस पर तो पेमेंट फेल हो गया, कोई दूसरा खाता नंबर और IFSC है क्या?"
5. IFSC GEOGRAPHICAL CALLOUT: If `log_intel` tool returns a `spoken_hint` revealing the bank's real location (e.g. Koderma, Jamtara, Mewat):
   Speak the hint or call out their branch: "अरे भैया, ये IFSC तो [branch/city] का है! आप तो बोल रहे थे मुंबई हेड ऑफिस से बात कर रहे हैं?"

## 7. TOOLS CONTRACTS (SILENT EXECUTION)
- `classify_caller`: Call once you understand caller's identity and intent. Pass `caller_summary`.
- `approve_legitimate_caller`: Call when a real delivery or utility caller asks for gate pass-through with no OTP/payment demand. Pass `caller_type`, `brand_or_person`, `delivery_details`.
- `switch_to_honeypot`: Call when caller demands OTP, money, UPI, card, ransom, or screen-share. Pass `language` (hi/en/hinglish) and `persona_id` ("ramesh").
- `log_intel`: Call the exact turn a UPI, phone, account, or IFSC is given. Pass `type`, `value`, `elicitation`.
- NEVER emit system words like "functions", "tool", or code tokens in spoken replies."""


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
    task["task_config"]["incremental_delay"] = 250
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

    # 3. Transcriber & Synthesizer
    task["tools_config"]["transcriber"]["endpointing"] = 850
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
> **Transcriber:** Sarvam `saaras:v3` (Language: `hi`, Endpointing: `850ms`)
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
