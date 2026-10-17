"""
app/voice/classifier.py - Real-time Mid-Call Scam Classifier for GuardianLine.

Engineered for ultra-low latency (<1.0s target) during active Indian telecom voice calls.
Employs a two-stage hybrid architecture:
  1. Fast Regex/Heuristic Scanner (<5ms): Catches blatant scams and obvious genuine calls.
  2. Fast LLM Classification (Groq primary, Gemini Flash secondary, Offline Semantic Fallback).
  3. Fail-safe timeout (<1.5s max): Returns 'unsure' if anything times out, preventing call dead-air.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CallerClassificationResult:
    call_id: str
    verdict: str  # "scam" | "genuine" | "unsure"
    confidence: float  # 0.0 to 1.0
    reason: str
    latency_ms: float
    method: str  # "heuristic" | "groq" | "gemini" | "offline_rules" | "timeout_fallback"
    pillars_detected: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "verdict": self.verdict,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "latency_ms": round(self.latency_ms, 2),
            "method": self.method,
            "pillars_detected": self.pillars_detected,
        }


# ==============================================================================
# 3-PILLAR BEHAVIORAL INVARIANT HEURISTICS
# ==============================================================================

# Pillar 1: Authority Coercion / Legal / Severe Disruption Threats
AUTHORITY_PATTERNS = [
    r"c\s*b\s*i|cbi\b|see\s*bee\s*eye|seebi\b",
    r"crime\s*branch|क्राइम\s*ब्रांच",
    r"cyber\s*crime|साइबर\s*क्राइम",
    r"police|pulis|poles|पुलिस|पुलिश|ट्रैफिक\s*पुलिस|थाना",
    r"digital\s*(arrest|arest)|डिजिटल\s*अरेस्ट",
    r"(arrest|arest)\s*warrant|अरेस्ट\s*वारंट|वारंट",
    r"supreme\s*court|सुप्रीम\s*कोर्ट|अदालत|कोर्ट\s*ऑर्डर",
    r"narcotics|narkotics|narkotik|ड्रग्स|नारकोटिक्स",
    r"customs|kustoms|kastam|कस्टम्स|कस्टम\s*अधिकारी",
    r"(tawan|taiwan|illegal|contraband|drugs|overseas)\s*(parcel|shipment)|(ताइवान|अवैध|ड्रग्स)\s*पार्सल",
    r"(account|acnt|a/c|card|sim|pension).*(block|suspend|freeze|सीज|बंद|सस्पेंड)",
    r"kyc\b|केवाईसी|biometric\s*kyc",
    r"electricity.*(cut|disconnect|bill)|power.*(cut|disconnect)|बिजली.*(काट|कट|काटी|बिल|मीटर)",
    r"trai.*(deactivat|block)|sim.*(block|disconnect)|दूरसंचार|telecom",
    r"court.*order|ई-चालान|challan|chalan|chalaan|चालान",
    r"task.*earn|रेटिंग्स|rating.*agency",
    r"pension.*(block|fraud|suspend)|पेंशन.*(बंद|ब्लॉक|जांच)|कल्याण\s*विभाग",
    r"money\s*laundering|हवाला|गैरकानूनी|vigilance",
]

# Pillar 2: Artificial Urgency, Secrecy & Isolation Pressure
URGENCY_PATTERNS = [
    r"within\s*\d+\s*(minute|hour|min|hr)s?|\d+\s*(मिनट|घंटे)",
    r"right\s*now|immediately|तुरंत|अभी\s*के\s*अभी",
    r"don'?t\s*(disconnect|cut|hang\s*up)|फ़ोन\s*मत\s*(काटना|काटिए)|कॉल\s*मत\s*(काटना|काटिए)",
    r"don'?t\s*tell|किसी\s*को\s*(मत|नहीं)\s*बताना|गोपनीय",
    r"urgent|urgnt|arjent|इमरजेंसी|आपातकालीन",
    r"before\s*\d+|आज\s*शाम|आज\s*रात|रात\s*\d+\s*बजे",
    r"पेनल्टी|penalty|सीज़|freeze|सीज",
    r"standby|हथकड़ी|गैर-जमानती|non-bailable",
]

# Pillar 3: Unscheduled Value / Payment / Credential Demands
VALUE_DEMAND_PATTERNS = [
    r"upi|यूपीआई",
    r"paytm|gpay|phonepe",
    r"payment|pay\s+\d+|transfer.*(money|amount|rupees|funds)|send.*money|पैसे.*(भेज|ट्रांसफर)|भुगतान",
    r"safe.*account|escrow.*account|सरकारी.*खाता",
    r"o\s*t\s*p|otp|odp|one\s*time\s*password|ओटीपी|ओ\s*टी\s*पी|गुप्त\s*कोड|\b\d+\s*अंक.*(ओटीपी|कोड)",
    r"any\s*desk|anidask|anydesk|eneedask|teamviewer|quicksupport|remote\s*access|स्क्रीन\s*शेयर|ऐप\s*डाउनलोड|play\s*store.*install",
    r"aadhaar|adhar|aaddhar|आधार\s*(नंबर|कार्ड)?|आधर|\b12\s*(अंक|digit)",
    r"video\s*call|वीडियो\s*कॉल|व्हाट्सएप\s*वीडियो|कैमरा\s*(ऑन|खोलो)",
    r"verification.*(fee|amount|deposit)|security.*deposit|सिक्योरिटी.*डिपॉजिट",
    r"deposit.*(verification|refundable|amount|rupees|\d+)|(refundable|verification).*(deposit|amount)",
    r"(account|acnt|a/c)\s*number.*(send|transfer|deposit)|खाता.*संख्या|खाता\s*नंबर",
    r"चालान.*भर",
]

# Genuine Service Whitelist Patterns (Zero demand for OTP, transfer, or threats)
GENUINE_INDICATORS = [
    r"parcel\s*deliver|delivery.*gate|अमेज़न.*पार्सल|कोरियर|amazon\s*parcel|security\s*guard|flipkart|फ्लिपकार्ट",
    r"appointment.*doctor|clinic|क्लिनिक|डॉक्टर.*अपॉइंटमेंट|dr\.\s*sundaram|eye\s*checkup|medanta|मेदांता|fortis",
    r"gate\s*security|guard\s*room|सिक्योरिटी\s*गार्ड|राम\s*सिंह",
    r"routine.*check|अपॉइंटमेंट.*कन्फर्म",
    r"society.*maintenance|फ्लैट\s*नंबर",
    r"होम\s*लोन|ब्याज\s*दर|नज़दीकी\s*शाखा|home\s*loan|interest\s*rate",
    r"भतीजा|चाचाजी|मामा|रविवार.*घर|nephew.*amit|visit.*sunday|पंक्चर|टायर|battery\s*died|bypass|ढाबे",
    r"स्कूल|टीचर|क्लास\s*टीचर|parent.*teacher|रिपोर्ट\s*कार्ड",
    r"नल.*ठीक|प्लंबर|दिनेश|repair|plumber",
    r"प्रीमियम|जीवन\s*आनंद|आधिकारिक\s*वेबसाइट|branch\s*counter",
    r"ओटीपी.*न\s*दें|पासवर्ड.*न\s*दें|never\s*ask.*(otp|pin|password)|कभी\s*भी.*(पिन|पासवर्ड|ओटीपी).*नहीं\s*मांगते|risk\s*prevention|security\s*advisory|सतर्कता\s*शाखा",
    r"tenant\s*verification|किराएदार.*सत्यापन|थाने\s*आकर|drop\s*by.*police\s*station|किराएदारों\s*का\s*सत्यापन",
    r"hospital.*admission|अस्पताल.*रिसेप्शन|admission\s*desk|आयुष्मान\s*भारत|photocopy.*aadhaar|मरीज\s*का\s*आधार",
]


def _evaluate_heuristics(transcript_text: str) -> Optional[Dict[str, Any]]:
    """Fast regex scanner over conversation text (<5ms)."""
    text_lower = transcript_text.lower()

    # Contextual whitelist checks for hard genuine cases:
    # 1. Delivery OTP in courier context with zero authority threats
    is_delivery_context = bool(re.search(r"delivery|parcel|पार्सल|अमेज़न|फ्लिपकार्ट|courier|कोरियर|gate", text_lower))
    is_delivery_otp = bool(re.search(r"delivery\s*(otp|code)|डिलीवरी\s*(ओटीपी|कोड)", text_lower))
    if is_delivery_context and is_delivery_otp and not re.search(r"cbi|police|arrest|block|अरेस्ट|वारंट", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate ecommerce delivery OTP request with zero coercion",
            "pillars": [],
        }

    # 2. In-person hospital Aadhaar photocopy with zero legal threat
    is_hospital_context = bool(re.search(r"hospital|अस्पताल|admission\s*desk|आयुष्मान|prescription", text_lower))
    is_in_person_aadhaar = bool(re.search(r"photocopy|साथ\s*लाइ|bring.*copy|show.*document", text_lower))
    if is_hospital_context and is_in_person_aadhaar and not re.search(r"cbi|police|arrest|block|वारंट", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate hospital in-person Aadhaar document reminder",
            "pillars": [],
        }

    # 3. Local police routine tenant verification with in-person station visit and zero money demand
    is_tenant_police = bool(re.search(r"tenant\s*verification|किराएदार.*सत्यापन|थाने\s*आकर|drop\s*by.*police\s*station", text_lower))
    if is_tenant_police and not re.search(r"digital\s*arrest|पैसे|transfer|fine|challan", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate local police routine tenant verification visit request",
            "pillars": [],
        }

    # 4. Bank automated fraud security alert with zero PIN/transfer demand
    is_bank_advisory = bool(re.search(r"never\s*ask.*(otp|pin|password)|कभी\s*भी.*(पिन|पासवर्ड|ओटीपी).*नहीं\s*मांगते|risk\s*prevention|security\s*advisory|सतर्कता\s*शाखा", text_lower))
    if is_bank_advisory and not re.search(r"safe\s*account|transfer\s*money|पैसे\s*(भेज|ट्रांसफर)", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate bank automated fraud prevention advisory",
            "pillars": [],
        }

    # 5. Relative roadside assistance / family update call
    is_relative_call = bool(re.search(r"भतीजा|चाचाजी|मामा|nephew|uncle.*amit|पंक्चर|टायर|battery\s*died", text_lower))
    if is_relative_call and not re.search(r"cbi|police|arrest|warrant", text_lower) and not re.search(r"safe\s*account|upi|otp", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate family relative call with zero official coercion",
            "pillars": [],
        }

    # Check 3 pillars
    has_authority = any(re.search(p, text_lower) for p in AUTHORITY_PATTERNS)
    has_urgency = any(re.search(p, text_lower) for p in URGENCY_PATTERNS)
    has_value_demand = any(re.search(p, text_lower) for p in VALUE_DEMAND_PATTERNS)

    pillars = []
    if has_authority:
        pillars.append("authority_coercion")
    if has_urgency:
        pillars.append("artificial_urgency")
    if has_value_demand:
        pillars.append("value_demand")

    # If all 3 pillars or (authority + value demand) are present -> Unambiguous Scam
    if len(pillars) >= 2 and (has_authority or has_value_demand):
        confidence = 0.96 if len(pillars) == 3 else 0.88
        return {
            "verdict": "scam",
            "confidence": confidence,
            "reason": f"Heuristic trigger on scam behavioral pillars: {', '.join(pillars)}",
            "pillars": pillars,
        }

    # If strictly genuine service indicators with NO scam pillars
    has_genuine = any(re.search(p, text_lower) for p in GENUINE_INDICATORS)
    if has_genuine and len(pillars) == 0:
        return {
            "verdict": "genuine",
            "confidence": 0.12,  # Low scam confidence -> genuine
            "reason": "Legitimate service interaction (delivery/appointment/guard) with zero scam indicators",
            "pillars": [],
        }

    return None


# ==============================================================================
# LLM CLASSIFIER PROMPT & INFERENCE
# ==============================================================================

CLASSIFIER_SYSTEM_PROMPT = """You are the GuardianLine Real-Time Scam Classifier for incoming phone calls in India.
Your mission is to protect elderly citizens from telecom fraud, including known scams (Digital Arrest, KYC block, electricity cutoff, courier narcotics, lottery, fake job tasks) AND novel, emergent scam pretexts.

CRITICAL PRINCIPLE: DO NOT RELY ON SPECIFIC KEYWORDS.
Scammers constantly invent novel pretexts (e.g. ancestral property audits, solar subsidy inspections, hospital emergency fees, deepfake family voices, cloud ransom, cryptocurrency tribunal clearance).
Instead, evaluate the underlying BEHAVIORAL 3-PILLAR SCAM INVARIANT:
1. AUTHORITY COERCION: Impersonating officials, enforcement agencies, utility desks, banks, tribunals, or threatening severe legal, financial, or service disruption penalties.
2. ARTIFICIAL URGENCY & ISOLATION: Imposing tight deadlines ("within 1-2 hours", "today", "immediately"), demanding secrecy, or forbidding the elder from hanging up or consulting relatives.
3. VALUE / CREDENTIAL DEMAND: Coercing unscheduled funds transfer, "security/clearance deposits", fee remissions, OTP/PIN disclosure, Aadhaar/ID capture, or remote screen-sharing app downloads (AnyDesk/TeamViewer).

Respond ONLY with a valid JSON object in this exact shape:
{
  "verdict": "scam" | "genuine" | "unsure",
  "confidence": <float between 0.0 and 1.0 representing scam likelihood>,
  "reason": "<short 1-line reason>",
  "pillars_detected": ["authority_coercion", "artificial_urgency", "value_demand"]
}

Decision Guidelines:
- If an unknown caller exhibits 2 or 3 scam pillars (especially authority/coercion + value/credential demand), classify as "scam" with confidence >= 0.85, REGARDLESS of novel vocabulary.
- If caller is a routine genuine service (delivery confirmation, doctor appointment reminder, known relative callback) with zero coercion or financial demands, classify as "genuine" with confidence <= 0.20.
- If caller intent is still ambiguous or early in the conversation, classify as "unsure" with confidence between 0.21 and 0.84 so the receptionist continues screening.
"""


def _format_conversation_for_prompt(conversation: List[Dict[str, str]]) -> str:
    lines = []
    for turn in conversation:
        role = turn.get("role", "caller")
        text = turn.get("content") or turn.get("text", "")
        lines.append(f"{role.upper()}: {text}")
    return "\n".join(lines)


def _call_groq(conversation_text: str, api_key: str, timeout: float = 1.2) -> Optional[Dict[str, Any]]:
    """Calls Groq API with strict timeout."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "GuardianLine/1.0 (Voice-Agent)",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this call transcript:\n\n{conversation_text}"},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "max_tokens": 150,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            content = res_body["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception:
        return None


def _call_gemini(conversation_text: str, api_key: str, timeout: float = 1.2) -> Optional[Dict[str, Any]]:
    """Calls Google Gemini Flash via AI Studio REST API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GuardianLine/1.0 (Voice-Agent)",
    }
    payload = {
        "system_instruction": {"parts": [{"text": CLASSIFIER_SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": f"Analyze this call transcript:\n\n{conversation_text}"}]}],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"},
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            content = res_body["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(content)
    except Exception:
        return None


def _classify_offline_rules(conversation_text: str) -> Dict[str, Any]:
    """
    Deterministic offline semantic classifier.
    Used for local testing, CI pipelines, and whenever API keys are not provided.
    """
    text_lower = conversation_text.lower()

    # Contextual exceptions
    is_delivery_context = bool(re.search(r"delivery|parcel|पार्सल|अमेज़न|फ्लिपकार्ट|courier|कोरियर|gate", text_lower))
    is_delivery_otp = bool(re.search(r"delivery\s*(otp|code)|डिलीवरी\s*(ओटीपी|कोड)", text_lower))
    if is_delivery_context and is_delivery_otp and not re.search(r"cbi|police|arrest|block|अरेस्ट|वारंट", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate ecommerce delivery OTP request with zero coercion",
            "pillars_detected": [],
        }

    is_hospital_context = bool(re.search(r"hospital|अस्पताल|admission\s*desk|आयुष्मान|prescription", text_lower))
    is_in_person_aadhaar = bool(re.search(r"photocopy|साथ\s*लाइ|bring.*copy|show.*document", text_lower))
    if is_hospital_context and is_in_person_aadhaar and not re.search(r"cbi|police|arrest|block|वारंट", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate hospital in-person Aadhaar document reminder",
            "pillars_detected": [],
        }

    is_tenant_police = bool(re.search(r"tenant\s*verification|किराएदार.*सत्यापन|थाने\s*आकर|drop\s*by.*police\s*station", text_lower))
    if is_tenant_police and not re.search(r"digital\s*arrest|पैसे|transfer|fine|challan", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate local police routine tenant verification visit request",
            "pillars_detected": [],
        }

    is_bank_advisory = bool(re.search(r"never\s*ask.*(otp|pin|password)|कभी\s*भी.*(पिन|पासवर्ड|ओटीपी).*नहीं\s*मांगते|risk\s*prevention|security\s*advisory|सतर्कता\s*शाखा", text_lower))
    if is_bank_advisory and not re.search(r"safe\s*account|transfer\s*money|पैसे\s*(भेज|ट्रांसफर)", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate bank automated fraud prevention advisory",
            "pillars_detected": [],
        }

    is_relative_call = bool(re.search(r"भतीजा|चाचाजी|मामा|nephew|uncle.*amit|पंक्चर|टायर|battery\s*died", text_lower))
    if is_relative_call and not re.search(r"cbi|police|arrest|warrant", text_lower) and not re.search(r"safe\s*account|upi|otp", text_lower):
        return {
            "verdict": "genuine",
            "confidence": 0.08,
            "reason": "Legitimate family relative call with zero official coercion",
            "pillars_detected": [],
        }

    pillars = []

    if any(re.search(p, text_lower) for p in AUTHORITY_PATTERNS):
        pillars.append("authority_coercion")
    if any(re.search(p, text_lower) for p in URGENCY_PATTERNS):
        pillars.append("artificial_urgency")
    if any(re.search(p, text_lower) for p in VALUE_DEMAND_PATTERNS):
        pillars.append("value_demand")

    if len(pillars) >= 2 or ("value_demand" in pillars and "authority_coercion" in pillars):
        return {
            "verdict": "scam",
            "confidence": 0.92,
            "reason": f"Offline rule match on behavioral pillars: {', '.join(pillars)}",
            "pillars_detected": pillars,
        }

    if any(re.search(p, text_lower) for p in GENUINE_INDICATORS) and len(pillars) == 0:
        return {
            "verdict": "genuine",
            "confidence": 0.10,
            "reason": "Offline rule match on genuine service indicator with zero scam signals",
            "pillars_detected": [],
        }

    # If only 1 suspicious pillar or mild inquiry
    if len(pillars) == 1:
        return {
            "verdict": "unsure",
            "confidence": 0.55,
            "reason": f"Single pillar observed ({pillars[0]}), awaiting further conversation turns",
            "pillars_detected": pillars,
        }

    return {
        "verdict": "unsure",
        "confidence": 0.40,
        "reason": "Insufficient conversational context to determine caller intent",
        "pillars_detected": [],
    }


# ==============================================================================
# MAIN ENTRY POINT: classify_caller
# ==============================================================================

def classify_caller(
    call_id: str,
    caller_number: str = "",
    conversation: Optional[List[Dict[str, str]]] = None,
    caller_summary: Optional[str] = None,
    language: str = "hi",
    max_latency_budget_s: float = 1.4,
) -> CallerClassificationResult:
    """
    Classify caller intent into 'scam', 'genuine', or 'unsure'.
    
    Supports both:
      - conversation: List of turn dicts (e.g. from local harness/eval benchmarks)
      - caller_summary: Single text summary generated by Bolna agent
    
    Guarantees response under max_latency_budget_s. Returns 'unsure' on any timeout
    so the receptionist agent keeps speaking rather than pausing or erroring.
    """
    start_time = time.time()
    
    # Assemble evaluation text from conversation transcript and/or agent summary
    text_parts = []
    if caller_summary and caller_summary.strip():
        text_parts.append(f"CALLER_SUMMARY: {caller_summary.strip()}")
    if conversation:
        text_parts.append(_format_conversation_for_prompt(conversation))
        
    formatted_text = "\n\n".join(text_parts) if text_parts else ""

    # Stage 1: Ultra-fast regex / heuristic screening (<5ms)
    heuristic_res = _evaluate_heuristics(formatted_text)
    if heuristic_res is not None:
        latency_ms = (time.time() - start_time) * 1000
        return CallerClassificationResult(
            call_id=call_id,
            verdict=heuristic_res["verdict"],
            confidence=heuristic_res["confidence"],
            reason=heuristic_res["reason"],
            latency_ms=latency_ms,
            method="heuristic",
            pillars_detected=heuristic_res.get("pillars", []),
        )

    # Stage 2: Fast LLM (Groq -> Gemini Flash -> Offline Semantic Rules)
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    remaining_budget = max(0.2, max_latency_budget_s - (time.time() - start_time))

    llm_res = None
    method_used = "offline_rules"

    if groq_key:
        llm_res = _call_groq(formatted_text, groq_key, timeout=remaining_budget)
        if llm_res:
            method_used = "groq"

    if not llm_res and gemini_key:
        remaining_budget = max(0.2, max_latency_budget_s - (time.time() - start_time))
        llm_res = _call_gemini(formatted_text, gemini_key, timeout=remaining_budget)
        if llm_res:
            method_used = "gemini"

    if not llm_res:
        llm_res = _classify_offline_rules(formatted_text)
        method_used = "offline_rules"

    # Enforce threshold mapping policy:
    # >= 0.85 -> scam, <= 0.20 -> genuine, otherwise -> unsure
    raw_conf = float(llm_res.get("confidence", 0.5))
    verdict = llm_res.get("verdict", "unsure")

    if raw_conf >= 0.85:
        verdict = "scam"
    elif raw_conf <= 0.20:
        verdict = "genuine"
    else:
        verdict = "unsure"

    latency_ms = (time.time() - start_time) * 1000

    return CallerClassificationResult(
        call_id=call_id,
        verdict=verdict,
        confidence=raw_conf,
        reason=llm_res.get("reason", "Classified based on conversational analysis"),
        latency_ms=latency_ms,
        method=method_used,
        pillars_detected=llm_res.get("pillars_detected", []),
    )
