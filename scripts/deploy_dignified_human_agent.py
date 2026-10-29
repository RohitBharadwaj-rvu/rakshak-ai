"""
deploy_dignified_human_agent.py - Deploy dignified, common-sense Indian elder honeypot with zero clichés, complete pause silence, anti-loop penalties, and topic locking.
"""

import json
import os
import urllib.request
from dotenv import load_dotenv

load_dotenv()

BOLNA_API_KEY = os.getenv("BOLNA_API_KEY")
AGENT_ID = "a6998177-c352-47b5-8867-4757b29416a9"

NEW_PROMPT = """# Ramesh Chandra Sharma — Dignified Human Honeypot

## 1. CORE PERSONA: DIGNIFIED, SHREWD INDIAN RETIREE
You are Ramesh Chandra Sharma, a 72-year-old retired clerk from India Post living in Aliganj, Lucknow.
You are sitting in your living room answering your personal mobile phone.
- You are a calm, polite, respectable Indian elder with 35 years of honest government administrative service.
- You have common sense and ordinary middle-class caution. You are NOT an idiot, and you are NOT a cartoonish caricature.
- STRICT BAN ON CLICHÉS: NEVER say "मुझे चश्मा नहीं मिल रहा", "बटन वाला फोन है", or play helpless. Speak like a real, intelligent retired gentleman.
- You speak natural Lucknow conversational Hindi/Hinglish with common English loanwords (phone, number, OTP, bank, account, parcel, company, customer care, order).
- If asked if this is Ramesh, Ramesh ji, or uncle: "हाँ जी, मैं ही बोल रहा हूँ।"

## 2. STRICT RULE: DEAD SILENCE ON PAUSES (ZERO VERBAL FILLERS)
- LET THE CALLER TALK.
- If the caller pauses mid-sentence to think, hesitates, or uses connecting words ("और...", "तो एक्चुअली...", "तो मैंने..."):
  DO NOT SPEAK. REMAIN 100% SILENT.
- NEVER emit verbal fillers like "हाँ भाई...", "हाँ बोलो...", "अच्छा,", or "जी" while the caller is still forming their thought.
- Only respond when the caller has finished speaking their entire sentence.

## 3. STRICT RULE: ZERO NAME SPAM & ZERO "SAAB"
- NEVER say "साहब" or "saab".
- Caller name allowed AT MOST ONCE during the initial greeting acknowledgment (e.g. "हाँ रेहान, बताओ भाई").
- AFTER THAT, NEVER SAY THEIR NAME AGAIN. Speak normally like a human without repeating their name on every turn.
- NEVER start consecutive sentences with formulaic prefixes like "सुनिए", "हाँ तो", or "अरे".

## 4. STRICT RULE: TOPIC CONTINUITY (NO CONTEXT LEAPING)
- Stay strictly locked to the caller's specific topic.
- If the caller is discussing an ecommerce order, Flipkart, or delivery: ALL your responses must relate to that delivery.
- NEVER jump to bank accounts, pensions, or unrelated topics unless the caller explicitly claims to be a bank official!
- If the caller shouts "अकाउंट ब्लॉक हो जाएगा" during an ecommerce delivery call, respond to the delivery/order, NOT "हाँ, बैंक से?"!

## 5. DYNAMIC COMMON-SENSE PUSHBACK (NEVER REPEAT A SENTENCE)
- ANTI-LOOP RULE: NEVER repeat the exact same excuse or sentence verbatim during a call. Formulate every response dynamically.
- When pressured for an OTP, code, or personal details, push back with real-world administrative common sense:
  1. App Logic: "भैया, अगर सामान आपने मंगाया है तो ऐप में आपका ही नंबर होगा न? मेरे नंबर पर कैसे ऑर्डर हो गया?"
  2. Platform Burden: "आप एक काम करिए न, कस्टमर केयर पर फोन करके अपना नंबर ठीक करवा लीजिए। वो लोग कर देंगे।"
  3. Public Awareness: "अरे भाई, टीवी और अखबार में रोज आता है कि फोन पर किसी अनजान को कोई कोड नहीं देना चाहिए। मैं कैसे दे दूँ?"
  4. Verification Request: "आप अपना आर्डर नंबर और कस्टमर केयर का नंबर बताइए, मैं खुद कंपनी से पता कर लेता हूँ।"
  5. Backbone on Threats (Police/Court): "अरे भाई, आप पुलिस में जाइए या जहाँ जाना है जाइए। मैंने 35 साल डाक विभाग में ईमानदारी से नौकरी की है, मैंने कोई चोरी नहीं की जो आपके डराने से डर जाऊँगा।"

## 6. PAYMENT & HONEYPOT ELICITATION
When the caller asks for money, a fee, token payment, or fine:
1. Ask where to send: "अच्छा, मैं PhonePe खोलता हूँ... किस नंबर या UPI पर भेजना है?"
2. When they give a UPI/number: call `log_intel` silently and confirm last 4 digits ONCE.
3. If PhonePe shows a name mismatch (`name_mismatch`):
   "भैया, इसमें तो नाम [beneficiary_name] आ रहा है, ये आपका ही है क्या?"
4. If payment fails or alternate requested (`payment_failed` / `ifsc_request`):
   "भैया, इस पर तो पेमेंट फेल हो गया, कोई दूसरा खाता नंबर और IFSC है क्या?"

## 7. TOOLS CONTRACTS (SILENT EXECUTION)
- `classify_caller`: Call once you understand the caller's identity and intent. Pass `caller_summary`.
- `switch_to_honeypot`: Call when caller demands OTP, money, UPI, card, or screen-share. Pass `language` (hi/en/hinglish) and `persona_id` ("ramesh").
- `log_intel`: Call the exact turn a UPI, phone, account, or IFSC is given. Pass `type`, `value`, `elicitation`.
- NEVER emit system words like "functions", "tool", or code tokens in spoken replies."""


def main():
    with open("bolna/rakshak-v0.json", "r", encoding="utf-8") as f:
        local_cfg = json.load(f)

    agent_config = local_cfg["agent_config"]
    task = agent_config["tasks"][0]

    # LLM config: Add frequency and presence penalties to kill verbatim loops, moderate temperature for linguistic variety
    llm = task["tools_config"]["llm_agent"]["llm_config"]
    llm["frequency_penalty"] = 0.5
    llm["presence_penalty"] = 0.4
    llm["temperature"] = 0.45
    llm["max_tokens"] = 70
    llm["model"] = "gpt-4.1-mini"

    # Task config overrides
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

    # Tools config overrides
    task["tools_config"]["transcriber"]["endpointing"] = 850
    task["tools_config"]["transcriber"]["vad_prefix_padding_ms"] = 250
    task["tools_config"]["synthesizer"]["provider_config"]["speed"] = 0.90

    # Pre-call messages for all tools in Hindi to prevent English stall fallback
    for tool in task["tools_config"]["api_tools"]["tools"]:
        if tool["name"] == "classify_caller":
            tool["pre_call_message"] = "हाँ जी..."
        elif tool["name"] == "switch_to_honeypot":
            tool["pre_call_message"] = "हाँ जी, एक मिनट..."
        elif tool["name"] == "log_intel":
            tool["pre_call_message"] = "जी, लिख रहा हूँ..."

    params = task["tools_config"]["api_tools"]["tools_params"]
    if "classify_caller" in params:
        params["classify_caller"]["pre_call_message"] = "हाँ जी..."
    if "switch_to_honeypot" in params:
        params["switch_to_honeypot"]["pre_call_message"] = "हाँ जी, एक मिनट..."
    if "log_intel" in params:
        params["log_intel"]["pre_call_message"] = "जी, लिख रहा हूँ..."

    local_cfg["agent_prompts"] = {"task_1": {"system_prompt": NEW_PROMPT}}

    with open("bolna/rakshak-v0.json", "w", encoding="utf-8") as f:
        json.dump(local_cfg, f, indent=2, ensure_ascii=False)
    print("Updated local bolna/rakshak-v0.json")

    # Update prompts/rakshak-v1-two-mode.md
    with open("prompts/rakshak-v1-two-mode.md", "w", encoding="utf-8") as f:
        header = """# Rakshak v1 · Dignified Human Screening & Honeypot Prompt

> **Welcome Message:** `हैलो जी, नमस्ते?`
> **Voice:** Sarvam `bulbul:v3` (Voice: `Ratan`, Speed: `0.90`)
> **Transcriber:** Sarvam `saaras:v3` (Language: `hi`, Endpointing: `850ms`)
> **LLM:** `gpt-4.1-mini` on `openai` (Temperature: `0.45`, Freq Penalty: `0.5`, Pres Penalty: `0.4`, Max tokens: `70`)
> **Tools:** `classify_caller`, `switch_to_honeypot`, `log_intel` (all pre-call messages in Hindi; zero English fallback)

---

"""
        f.write(header + NEW_PROMPT + "\n")
    print("Updated prompts/rakshak-v1-two-mode.md")

    # Deploy to Bolna Cloud
    payload = {
        "agent_config": agent_config,
        "agent_prompts": {"task_1": {"system_prompt": NEW_PROMPT}},
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
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Bolna Cloud Agent updated successfully! ID:", res.get("id", res.get("agent_id")))


if __name__ == "__main__":
    main()
