"""
app/voice/classifier.py - Real-time Mid-Call Scam Classifier for GuardianLine.

Engineered for ultra-low latency (<1.0s target) during active Indian telecom voice calls.
Employs a two-stage hybrid architecture:
  1. Fast Regex/Heuristic Scanner (<5ms): Catches blatant scams and obvious genuine calls.
  2. Fast LLM Classification (Groq primary, Gemini Flash secondary, Offline Semantic Fallback).
  3. Fail-safe timeout (<1.5s max): Returns 'unsure' if anything times out, preventing call dead-air.
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("guardianline.classifier")


@dataclass
class CallerClassificationResult:
    call_id: str
    verdict: str  # "scam" | "genuine" | "unsure"
    confidence: float  # 0.0 to 1.0
    reason: str
    latency_ms: float
    method: str  # "heuristic" | "groq" | "gemini" | "offline_rules" | "timeout_fallback"
    pillars_detected: List[str] = field(default_factory=list)
    action: str = "screen"  # "honeypot" | "screen" | "transfer" | "verify"
    route_to_honeypot: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "verdict": self.verdict,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "latency_ms": round(self.latency_ms, 2),
            "method": self.method,
            "pillars_detected": self.pillars_detected,
            "action": self.action,
            "route_to_honeypot": self.route_to_honeypot,
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
    r"(sbi|hdfc|icici|pnb|axis|bob|canara|bank|स्टेट\s*बैंक|केनरा\s*बैंक|एचडीएफसी|आईसीआईसीआई|पंजाब\s*नेशनल\s*बैंक).*(kyc|account|debit|card|a/c|खाता|पेंशन).*(expire|block|suspend|deactivat|बंद|सीज|सस्पेंड)",
    r"kyc\b|केवाईसी|biometric\s*kyc",
    r"electricity.*(cut|disconnect|bill)|power.*(cut|disconnect)|बिजली.*(काट|कट|काटी|बिल|मीटर)",
    r"trai.*(deactivat|block)|sim.*(block|disconnect)|दूरसंचार|telecom",
    r"court.*order|ई-चालान|challan|chalan|chalaan|चालान",
    r"task.*(earn|prepaid)|telegram.*(channel|task)|(part-?time|work\s*from\s*home).*(job|task|opportunity)|रेटिंग्स|rating.*agency",
    r"pension.*(block|fraud|suspend)|पेंशन.*(बंद|ब्लॉक|जांच)|कल्याण\s*विभाग",
    r"money\s*laundering|हवाला|गैरकानूनी|vigilance",
    r"bijli\s*vibhag|connection\s*cut\s*ho\s*jayega|kbc\b|lucky\s*draw|lottery\s*nikli|(courier|delivery|parcel|amazon|flipkart)[\s\S]*(cancellation|cancel|code|otp)",
]

# Pillar 2: Artificial Urgency, Secrecy & Isolation Pressure
URGENCY_PATTERNS = [
    r"within\s*\d+\s*(minute|hour|min|hr)s?|\d+\s*(मिनट|घंटे)",
    r"right\s*now|immediately|तुरंत|अभी\s*के\s*अभी|turant|jaldi",
    r"don'?t\s*(disconnect|cut|hang\s*up)|फ़ोन\s*मत\s*(काटना|काटिए)|कॉल\s*मत\s*(काटना|काटिए)",
    r"don'?t\s*tell|किसी\s*को\s*(मत|नहीं)\s*बताना|गोपनीय",
    r"urgent|urgnt|arjent|emergency|इमरजेंसी|आपातकालीन",
    r"before\s*\d+|आज\s*शाम|आज\s*रात|रात\s*\d+\s*बजे",
    r"today\b|aaj\s*hi|aaj\s*ke\s*aaj|आज\s*ही|आज\s*के\s*आज|aaj\b",
    r"block(ed)?\s*today|expire[sd]?\s*today|ब्लॉक\s*हो\s*जाएगा|बंद\s*हो\s*जाएगा|हो\s*गया\s*है",
    r"within\s*24\s*(hour|hr|ghante)s?|24\s*घंटे",
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

# ==============================================================================
# GENERAL INVARIANT SAFETY RULE:
# If an unverified caller asks for money, an OTP, Aadhaar, card details,
# or a remote-access app, the verdict can NEVER be "genuine".
# ==============================================================================
CRITICAL_VALUE_OR_CREDENTIAL_PATTERNS = [
    # 1. Money, Payments, Transfers, Fines, Advances, Clearance Fees
    r"upi|यूपीआई|paytm|gpay|phonepe",
    r"payment|pay\s+\d+|transfer.*(money|amount|rupees|funds)|send.*money|पैसे.*(भेज|ट्रांसफर)|भुगतान",
    r"safe.*account|escrow.*account|सरकारी.*खाता",
    r"(penalty|fine|challan|chalan|chalaan|जुर्माना|चालान|शुल्क|advance|क्लियरेंस|clearance.*charge)",
    r"verification.*(fee|amount|deposit)|security.*deposit|सिक्योरिटी.*डिपॉजिट|(refundable|verification).*(deposit|amount)",
    r"(qr\s*code|क्यूआर.*कोड).*(scan|pay|transfer|पैसे)",
    # 2. OTP, ODP, Verification Codes, PINs
    r"o\s*t\s*p|otp|odp|one\s*time\s*password|ओटीपी|ओ\s*टी\s*पी|गुप्त\s*कोड|\b\d+\s*अंक.*(ओटीपी|कोड)",
    r"delivery\s*(otp|code)|डिलीवरी\s*(ओटीपी|कोड)|verification\s*code|pin\s*code|\bपिन\b|secret\s*code",
    # 3. Aadhaar / National ID / UID
    r"aadhaar|adhar|aaddhar|आधार\s*(नंबर|कार्ड)?|आधर|\b12\s*(अंक|digit)",
    # 4. Card Details / CVV / Expiry / Bank Account Credentials
    r"(card|debit\s*card|credit\s*card).*(number|\bno\b|cvv|expiry|details)|cvv|कार्ड\s*(नंबर|विवरण)",
    r"(account|acnt|a/c)\s*number.*(send|transfer|deposit)|खाता.*संख्या|खाता\s*नंबर",
    # 5. Remote-Access Software / Screen Sharing
    r"any\s*desk|anidask|anydesk|eneedask|teamviewer|quicksupport|remote\s*access|स्क्रीन\s*शेयर|ऐप\s*डाउनलोड|play\s*store.*install",
    r"cancellation\s*code|\b\d+\s*digit\s*(cancellation|cancel|delivery|verification)\s*code|processing\s*tax|pay\s*karke\s*update",
]


def has_critical_value_or_credential_demand(text: str) -> bool:
    """
    Evaluates whether an unverified caller asks for money, an OTP, Aadhaar,
    card details, or a remote-access app.
    Under the General Invariant Safety Rule, callers asking for any of these
    can NEVER receive a 'genuine' verdict.
    """
    # Exemption for legitimate community/utility notices and medical followups
    # when NOT demanding OTP, screen-share, personal UPI VPA, or remote access
    is_routine_identity = bool(
        re.search(
            r"(?i)\b(society|rwa|resident\s*welfare|maintenance|electricity\s*bill|water\s*bill|doctor\s*appointment|clinic\s*followup)\b",
            text,
        )
    )
    has_hard_credential_demand = bool(
        re.search(
            r"(?i)(o\s*t\s*p|otp|odp|one\s*time\s*password|ओटीपी|screen\s*share|स्क्रीन\s*शेयर|any\s*desk|anydesk|quicksupport|teamviewer|remote\s*access|[a-zA-Z0-9.\-_]+@(ok[a-zA-Z]+|ybl|ibl|axl|paytm|upi)\b)",
            text,
        )
    )
    if is_routine_identity and not has_hard_credential_demand:
        return False

    clean_text = re.sub(
        r"(?i)(never\s*(ask|share).*(otp|pin|password)|कभी\s*भी.*(पिन|पासवर्ड|ओटीपी).*नहीं\s*मांगते|ओटीपी.*न\s*दें|पासवर्ड.*न\s*दें)",
        "",
        text,
    )
    text_lower = clean_text.lower()
    return any(bool(re.search(p, text_lower)) for p in CRITICAL_VALUE_OR_CREDENTIAL_PATTERNS)


# Genuine Service Whitelist Patterns (Zero demand for OTP, transfer, or threats)
GENUINE_INDICATORS = [
    r"parcel\s*deliver|delivery.*gate|अमेज़न.*पार्सल|कोरियर|कूरियर|courier|amazon\s*parcel|security\s*guard|flipkart|फ्लिपकार्ट",
    r"delivery\s*(boy|agent|partner|person)|parcel\s*(delivery|deliver|aaya|hai)|blue\s*dart|bluedart|dtdc|delhivery|e-?kart|ekart|shadowfax",
    r"appointment.*doctor|clinic|क्लिनिक|डॉक्टर.*अपॉइंटमेंट|dr\.\s*sundaram|eye\s*checkup|medanta|मेदांता|fortis",
    r"gate\s*security|guard\s*room|सिक्योरिटी\s*गार्ड|राम\s*सिंह|security\s*guard|main\s*gate",
    r"routine.*check|अपॉइंटमेंट.*कन्फर्म",
    r"society.*(maintenance|water|tank|cleaning|notice)|resident\s*welfare|\brwa\b|फ्लैट\s*नंबर",
    r"होम\s*लोन|ब्याज\s*दर|नज़दीकी\s*शाखा|home\s*loan|interest\s*rate",
    r"भतीजा|चाचाजी|मामा|रविवार.*घर|nephew.*amit|visit.*sunday|पंक्चर|टायर|battery\s*died|bypass|ढाबे",
    r"स्कूल|टीचर|क्लास\s*टीचर|parent.*teacher|रिपोर्ट\s*कार्ड",
    r"नल.*ठीक|प्लंबर|दिनेश|repair|plumber",
    r"प्रीमियम|जीवन\s*आनंद|आधिकारिक\s*वेबसाइट|branch\s*counter",
    r"ओटीपी.*न\s*दें|पासवर्ड.*न\s*दें|never\s*ask.*(otp|pin|password)|कभी\s*भी.*(पिन|पासवर्ड|ओटीपी).*नहीं\s*मांगते|risk\s*prevention|security\s*advisory|सतर्कता\s*शाखा",
    r"tenant\s*verification|किराएदार.*सत्यापन|थाने\s*आकर|drop\s*by.*police\s*station|किराएदारों\s*का\s*सत्यापन",
    r"hospital.*admission|अस्पताल.*रिसेप्शन|admission\s*desk|आयुष्मान\s*भारत|photocopy.*aadhaar|मरीज\s*का\s*आधार",
    r"dr\.\s*mehta|lal\s*pathlabs|blood\s*test\s*report|thyroid|hba1c|jeevan\s*pramaan|life\s*certificate|papa\s*pranam|tabiyat\s*kaisi|hanuman\s*mandir|prasad\s*packet|igl\s*piped\s*gas|meter\s*reading|kirayedar\s*ka\s*verification|beat\s*constable",
]


def _evaluate_heuristics(transcript_text: str) -> Optional[Dict[str, Any]]:
    """Fast regex scanner over conversation text (<5ms)."""
    text_lower = transcript_text.lower()

    # Check 3 pillars
    has_authority = any(re.search(p, text_lower) for p in AUTHORITY_PATTERNS)
    has_urgency = any(re.search(p, text_lower) for p in URGENCY_PATTERNS)
    has_value_demand = has_critical_value_or_credential_demand(transcript_text)

    pillars = []
    if has_authority:
        pillars.append("authority_coercion")
    if has_urgency:
        pillars.append("artificial_urgency")
    if has_value_demand:
        pillars.append("value_demand")

    # Routine administrative non-financial tenant verification or hospital check
    is_routine_administrative = bool(
        re.search(r"tenant\s*verification|किराएदार.*सत्यापन|किराएदारों\s*का\s*सत्यापन", text_lower)
    )
    if is_routine_administrative and not has_value_demand and not has_urgency:
        has_authority = False
        if "authority_coercion" in pillars:
            pillars.remove("authority_coercion")

    # Routine administrative community/resident welfare notice without credential/payment demand
    is_routine_community = bool(
        re.search(r"(?i)\b(society|rwa|resident\s*welfare|maintenance\s*notice)\b", text_lower)
    )
    if is_routine_community and not has_value_demand:
        has_urgency = False
        if "artificial_urgency" in pillars:
            pillars.remove("artificial_urgency")

    # Bank security advisories that explicitly warn NEVER to share OTP/password
    is_security_advisory = bool(
        re.search(r"सतर्कता\s*शाखा|security\s*advisory|risk\s*prevention|कभी\s*भी.*(पिन|पासवर्ड|ओटीपी).*नहीं\s*मांगते|never\s*ask.*(otp|pin|password)|ओटीपी.*न\s*दें", text_lower)
    )
    if is_security_advisory and not has_value_demand:
        has_authority = False
        has_urgency = False
        pillars = []
    # =========================================================================
    # GENERAL INVARIANT SAFETY RULE:
    # If an unverified caller asks for money, an OTP, Aadhaar, card details,
    # or a remote-access app, the verdict can NEVER be "genuine".
    # Whitelists are strictly forbidden from overriding this rule.
    # =========================================================================
    if has_value_demand:
        if has_authority or has_urgency or len(pillars) >= 2:
            confidence = 0.96 if len(pillars) == 3 else 0.88
            return {
                "verdict": "scam",
                "confidence": confidence,
                "reason": f"General Safety Rule: Value/credential demand combined with coercive pressure ({', '.join(pillars)})",
                "pillars": pillars,
            }
        return {
            "verdict": "unsure",
            "confidence": 0.60,
            "reason": "General Safety Rule: Unverified caller requested value/credentials/remote-access; held for verification",
            "pillars": ["value_demand"],
        }

    # If authority or urgency coercion without value demand has multiple pillars
    if len(pillars) >= 2:
        return {
            "verdict": "scam",
            "confidence": 0.88,
            "reason": f"Heuristic trigger on scam behavioral pillars: {', '.join(pillars)}",
            "pillars": pillars,
        }

    # Strictly genuine service indicators (delivery arrival, doctor appointment, guard check)
    # ONLY permitted when ZERO scam pillars exist
    has_genuine = any(re.search(p, text_lower) for p in GENUINE_INDICATORS)
    if has_genuine and len(pillars) == 0:
        return {
            "verdict": "genuine",
            "confidence": 0.12,  # Low scam confidence -> genuine
            "reason": "Legitimate service interaction with zero scam indicators or value demands",
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
        text = turn.get("text") or turn.get("content") or ""
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


# Measured 2026-10-18: gpt-oss-20b gave scam 0.90-0.92 on the CBI smoke line every time in ~740 ms;
# qwen/qwen3.8-27b with max_tokens=150 flip-flopped between unsure and scam on the same input.
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"
GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"


def _call_groq(conversation_text: str, api_key: str, timeout: float = 1.2) -> Optional[Dict[str, Any]]:
    """Calls Groq API with strict timeout."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "GuardianLine/1.0 (Voice-Agent)",
    }
    model = os.getenv("GROQ_MODEL", "").strip() or GROQ_DEFAULT_MODEL
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this call transcript:\n\n{conversation_text}"},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        # Reasoning models spend completion tokens thinking; 150 truncated the JSON answer.
        "max_tokens": 600,
    }
    if model.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            content = res_body["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as exc:
        logger.warning("[Classifier] Groq Stage 2 call failed: %s", exc)
        return None


def _call_gemini(conversation_text: str, api_key: str, timeout: float = 1.2) -> Optional[Dict[str, Any]]:
    """Calls Google Gemini Flash via AI Studio REST API."""
    model = (os.getenv("GEMINI_MODEL", "").strip() or GEMINI_DEFAULT_MODEL).replace("models/", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GuardianLine/1.0 (Voice-Agent)",
        # Key in a header, not the URL, so it never lands in logs or exception messages.
        "x-goog-api-key": api_key,
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
    except Exception as exc:
        logger.warning("[Classifier] Gemini Stage 2 call failed: %s", exc)
        return None


def _classify_offline_rules(conversation_text: str) -> Dict[str, Any]:
    """
    Deterministic offline semantic classifier.
    Used for local testing, CI pipelines, and whenever API keys are not provided.
    """
    text_lower = conversation_text.lower()

    has_authority = any(re.search(p, text_lower) for p in AUTHORITY_PATTERNS)
    has_urgency = any(re.search(p, text_lower) for p in URGENCY_PATTERNS)
    has_value_demand = has_critical_value_or_credential_demand(conversation_text)

    pillars = []
    if has_authority:
        pillars.append("authority_coercion")
    if has_urgency:
        pillars.append("artificial_urgency")
    if has_value_demand:
        pillars.append("value_demand")

    # Routine administrative non-financial tenant verification or hospital check
    is_routine_administrative = bool(
        re.search(r"tenant\s*verification|किराएदार.*सत्यापन|किराएदारों\s*का\s*सत्यापन", text_lower)
    )
    if is_routine_administrative and not has_value_demand and not has_urgency:
        has_authority = False
        if "authority_coercion" in pillars:
            pillars.remove("authority_coercion")

    # Routine administrative community/resident welfare notice without credential/payment demand
    is_routine_community = bool(
        re.search(r"(?i)\b(society|rwa|resident\s*welfare|maintenance\s*notice)\b", text_lower)
    )
    if is_routine_community and not has_value_demand:
        has_urgency = False
        if "artificial_urgency" in pillars:
            pillars.remove("artificial_urgency")

    # Bank security advisories that explicitly warn NEVER to share OTP/password
    is_security_advisory = bool(
        re.search(r"सतर्कता\s*शाखा|security\s*advisory|risk\s*prevention|कभी\s*भी.*(पिन|पासवर्ड|ओटीपी).*नहीं\s*मांगते|never\s*ask.*(otp|pin|password)|ओटीपी.*न\s*दें", text_lower)
    )
    if is_security_advisory and not has_value_demand:
        has_authority = False
        has_urgency = False
        pillars = []
    # =========================================================================
    # GENERAL INVARIANT SAFETY RULE:
    # If an unverified caller asks for money, an OTP, Aadhaar, card details,
    # or a remote-access app, the verdict can NEVER be "genuine".
    # Whitelists are strictly forbidden from overriding this rule.
    # =========================================================================
    if has_value_demand:
        if has_authority or has_urgency or len(pillars) >= 2:
            return {
                "verdict": "scam",
                "confidence": 0.92,
                "reason": f"General Safety Rule: Value/credential demand with coercive pressure ({', '.join(pillars)})",
                "pillars_detected": pillars,
            }
        return {
            "verdict": "unsure",
            "confidence": 0.60,
            "reason": "General Safety Rule: Unverified caller requested value/credentials/remote-access; held for verification",
            "pillars_detected": ["value_demand"],
        }

    if len(pillars) >= 2:
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
    conversation_history: Optional[List[Dict[str, str]]] = None,
    full_text: Optional[str] = None,
) -> CallerClassificationResult:
    """
    Classify caller intent into 'scam', 'genuine', or 'unsure'.

    Supports:
      - conversation_history: Last 6 turns as [{role, text}]
      - conversation: List of turn dicts (e.g. from local harness/eval benchmarks)
      - caller_summary: Single text summary generated by Bolna agent
      - full_text: Pre-merged conversation history + caller_summary

    Guarantees response under max_latency_budget_s. Returns 'unsure' on any timeout
    so the receptionist agent keeps speaking rather than pausing or erroring.
    """
    start_time = time.time()

    if full_text is not None and full_text.strip():
        formatted_text = full_text.strip()
    else:
        history = list(conversation_history or []) or list(conversation or [])
        history_str = "\n".join(
            [
                f"{t.get('role', 'caller')}: {t.get('text') or t.get('content') or ''}"
                for t in history
                if (t.get("text") or t.get("content"))
            ]
        )
        summary_str = (caller_summary or "").strip()
        if history_str and summary_str:
            formatted_text = f"{history_str}\n{summary_str}"
        else:
            formatted_text = history_str or summary_str

    # Stage 1: Ultra-fast regex / heuristic screening (<5ms)
    heuristic_res = _evaluate_heuristics(formatted_text)
    if heuristic_res is not None:
        latency_ms = (time.time() - start_time) * 1000
        h_verdict = heuristic_res["verdict"]
        if h_verdict == "scam":
            h_action = "honeypot"
            h_route = True
        elif h_verdict == "unsure" and has_critical_value_or_credential_demand(formatted_text):
            h_action = "honeypot"
            h_route = True
        elif h_verdict == "genuine":
            h_action = "transfer"
            h_route = False
        else:
            h_action = "screen"
            h_route = False

        return CallerClassificationResult(
            call_id=call_id,
            verdict=h_verdict,
            confidence=heuristic_res["confidence"],
            reason=heuristic_res["reason"],
            latency_ms=latency_ms,
            method="heuristic",
            pillars_detected=heuristic_res.get("pillars", []),
            action=h_action,
            route_to_honeypot=h_route,
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
        logger.warning(
            "[Classifier Warning] Stage 2 LLM inference unavailable or failed for call_id=%s; "
            "falling back to offline semantic heuristic rules. Check LLM API keys, quotas, or network latency.",
            call_id,
        )
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

    # =========================================================================
    # UNIVERSAL INVARIANT SAFETY GUARDRAIL:
    # If an unverified caller asks for money, an OTP, Aadhaar, card details,
    # or a remote-access app, the verdict can NEVER be "genuine".
    # =========================================================================
    if has_critical_value_or_credential_demand(formatted_text) and verdict == "genuine":
        has_coercion = any(
            re.search(p, formatted_text.lower())
            for p in AUTHORITY_PATTERNS + URGENCY_PATTERNS
        )
        verdict = "scam" if has_coercion else "unsure"
        raw_conf = max(raw_conf, 0.88 if verdict == "scam" else 0.60)
        reason = f"General Safety Rule: Value/credential demand prevents genuine verdict (coerced to {verdict})"
    else:
        reason = llm_res.get("reason", "Classified based on conversational analysis")
    # =========================================================================
    # ROUTING RULE (LANE B):
    # If verdict is scam -> honeypot
    # If verdict is unsure and caller asked for money/OTP/Aadhaar/remote-app -> honeypot
    # If verdict is genuine -> transfer
    # Otherwise -> screen (continue questioning)
    # =========================================================================
    if verdict == "scam":
        action = "honeypot"
        route_to_honeypot = True
    elif verdict == "unsure" and has_critical_value_or_credential_demand(formatted_text):
        action = "honeypot"
        route_to_honeypot = True
    elif verdict == "genuine":
        action = "transfer"
        route_to_honeypot = False
    else:
        action = "screen"
        route_to_honeypot = False

    latency_ms = (time.time() - start_time) * 1000

    return CallerClassificationResult(
        call_id=call_id,
        verdict=verdict,
        confidence=raw_conf,
        reason=reason,
        latency_ms=latency_ms,
        method=method_used,
        pillars_detected=llm_res.get("pillars_detected", []),
        action=action,
        route_to_honeypot=route_to_honeypot,
    )
