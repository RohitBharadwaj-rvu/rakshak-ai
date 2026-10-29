"""
app/voice/tools.py - Mid-Call Bolna Custom Function Tool Endpoints (T-TOOLS).

Implements:
  - POST /tools/switch_to_honeypot
  - POST /tools/log_intel
Supports both Bolna v1 prompt parameter names (`value`, `name`, `age`, `city`,
`short_backstory`, `bait_values`) and Sprint contract field names (`value_as_heard`,
`persona_name`, `persona_age`, `persona_city`, `persona_lines`, `fake_bait`).
"""

import logging
from typing import Dict, List, Literal, Optional
from fastapi import APIRouter
from pydantic import AliasChoices, BaseModel, Field, model_validator

from app.agent.state import get_persona_bundle
from app.voice.extractor import normalize_and_validate_single_intel
from datetime import datetime, timezone
from app.voice.ifsc import is_valid_ifsc, resolve_ifsc, generate_ifsc_spoken_hint
from app.voice.family_loop import broadcast_sse, get_family_intel_injection
from app.voice.store import (
    append_mid_call_intel,
    get_or_assign_honeypot_persona,
    resolve_effective_tool_call_id,
    update_call_verdict,
    upsert_mule_identifier,
)
from app.voice.syndicate import ingest_scam_identifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["Bolna Mid-Call Tools"])


class SwitchToHoneypotRequest(BaseModel):
    call_id: str = Field(..., min_length=1, description="Unique identifier for the active call (e.g., %(call_sid)s)")
    execution_id: Optional[str] = Field(default=None, description="Optional Bolna execution ID (e.g., %(execution_id)s)")
    language: Optional[str] = Field(default="hi", description="Requested persona language (hi, en, hinglish)")
    persona_id: Optional[str] = Field(default=None, description="Optional preferred persona key")


class FakeBaitModel(BaseModel):
    upi_id: str
    account_number: str
    ifsc_code: str
    phone_number: str
    otp: str = "000000"
    aadhaar: str = "0000 0000 0000"


class SwitchToHoneypotResponse(BaseModel):
    call_id: str
    language: str
    persona_id: str
    persona_name: str
    name: str
    persona_age: int
    age: int
    persona_city: str
    city: str
    short_backstory: str
    persona_lines: List[str]
    fake_bait: FakeBaitModel
    bait_values: FakeBaitModel
    system_intel: Optional[str] = None


class ApproveLegitimateCallerRequest(BaseModel):
    call_id: str = Field(..., min_length=1, description="Unique identifier for the active call (e.g., %(call_sid)s)")
    execution_id: Optional[str] = Field(default=None, description="Optional Bolna execution ID (e.g., %(execution_id)s)")
    caller_type: str = Field(default="delivery", description="Caller category: e.g. delivery, pharmacy, clinic, utility, ride")
    brand_or_person: str = Field(default="Delivery Partner", description="Entity name: e.g. Blinkit, Swiggy, Zomato, Apollo Pharmacy, BlueDart")
    delivery_details: str = Field(default="Package delivery at door", description="Delivery context or request summary heard from caller")


class ApproveLegitimateCallerResponse(BaseModel):
    status: Literal["approved", "rejected"]
    approved: bool
    call_id: str
    brand_or_person: str
    caller_type: str
    delivery_details: str
    reason: Optional[str] = None
    spoken_instruction: str


IntelKind = Literal["upi", "phone", "account", "ifsc", "link", "pan", "other"]

# Mule-rotation extraction playbook tactics (Addition 1). Free text is still accepted so a
# slightly-off label from the voice agent never loses evidence; known labels are canonicalised.
KNOWN_ELICITATIONS = {
    "initial_ask",
    "payment_failed",
    "name_mismatch",
    "ifsc_request",
    "callback",
    "repeat_back",
    "volunteered",
    "other",
}
QUOTE_MAX_CHARS = 120


def _canonical_elicitation(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    key = v.lower().replace("-", "_").replace(" ", "_")
    return key if key in KNOWN_ELICITATIONS else v[:64]


class LogIntelRequest(BaseModel):
    call_id: str = Field(..., min_length=1, description="Unique identifier for the active call (e.g., %(call_sid)s)")
    execution_id: Optional[str] = Field(default=None, description="Optional Bolna execution ID (e.g., %(execution_id)s)")
    kind: Optional[IntelKind] = Field(
        default=None,
        validation_alias=AliasChoices("kind", "type"),
        description="Category of identifier heard mid-call (accepts 'kind' or legacy 'type')",
    )
    value_raw: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("value_as_heard", "value_raw", "value"),
        description="Identifier exactly as heard (accepts 'value_raw', 'value_as_heard' or 'value')",
    )
    value_normalized: Optional[str] = Field(
        default=None,
        description="Optional agent-side canonical form; used only if the server normalizer cannot parse value_raw",
    )
    elicitation: Optional[str] = Field(
        default=None,
        description="Playbook tactic that drew this out: initial_ask, payment_failed, name_mismatch, "
        "ifsc_request, callback, repeat_back, volunteered, other",
    )
    quote: Optional[str] = Field(default=None, description="Caller's words around the identifier (truncated to 120 chars)")
    turn_index: Optional[int] = Field(default=None, ge=0, description="Transcript turn index where it was heard")
    seconds_from_start: Optional[float] = Field(default=None, ge=0, description="Seconds from call start")

    @model_validator(mode="after")
    def _require_kind(self) -> "LogIntelRequest":
        if self.kind is None:
            raise ValueError("Field required: kind (or legacy 'type')")
        return self


class LogIntelResponse(BaseModel):
    status: Literal["logged"]
    call_id: str
    kind: str
    type: str
    value: str
    value_raw: str
    value_as_heard: str
    value_normalized: str
    normalized_value: str
    unparseable: bool
    elicitation: Optional[str] = None
    quote: Optional[str] = None
    turn_index: Optional[int] = None
    seconds_from_start: Optional[float] = None
    identifier_status: Literal["suspected"] = "suspected"
    is_bait: bool = False
    duplicate: bool = False
    times_logged: int = 1
    identifiers_logged: int = Field(description="Distinct identifiers logged for this call so far")
    beneficiary_name: Optional[str] = Field(default=None, description="Resolved beneficiary/mule name from penny-drop lookup")
    bank_name: Optional[str] = Field(default=None, description="Resolved bank or PSP name from penny-drop lookup")
    bank_branch: Optional[str] = Field(default=None, description="Resolved branch name for IFSC")
    bank_city: Optional[str] = Field(default=None, description="Resolved city from Razorpay IFSC")
    bank_state: Optional[str] = Field(default=None, description="Resolved state from Razorpay IFSC")
    spoken_hint: Optional[str] = Field(default=None, description="Devanagari spoken hint for calling out scammer branch/city")
    syndicate_match: bool = Field(default=False, description="True if this mule identifier was seen in multiple calls")
    linked_call_ids: List[str] = Field(default_factory=list, description="Other call IDs linked to this mule identifier")
    system_intel: Optional[str] = Field(default=None, description="Ground-truth mid-call context injection")


@router.post("/switch_to_honeypot", response_model=SwitchToHoneypotResponse)
async def api_switch_to_honeypot(req: SwitchToHoneypotRequest) -> SwitchToHoneypotResponse:
    """
    Switch the voice agent from screening receptionist mode to an elderly honeypot persona.
    Idempotent per effective `call_id`; unknown language falls back to Hindi (`hi`).
    """
    effective_id = resolve_effective_tool_call_id(req.call_id, req.execution_id)
    bundle = get_or_assign_honeypot_persona(
        call_id=effective_id,
        bundle_factory=lambda: get_persona_bundle(
            call_id=effective_id,
            language=req.language,
            preferred_persona=req.persona_id,
        ),
    )
    logger.info(
        "switch_to_honeypot effective_id=%s raw_call_id=%s raw_execution_id=%s persona=%s language=%s",
        effective_id,
        req.call_id,
        req.execution_id,
        bundle["persona_id"],
        bundle["language"],
    )
    family_intel = get_family_intel_injection(effective_id)
    return SwitchToHoneypotResponse(
        **bundle,
        system_intel=family_intel,
    )


SCAM_INDICATORS = {
    "otp", "upi", "money", "fee", "arrest", "kyc", "anydesk", "code", "cvv",
    "pin", "password", "urgent", "transfer", "charge", "refund", "card number",
}


@router.post("/approve_legitimate_caller", response_model=ApproveLegitimateCallerResponse)
async def api_approve_legitimate_caller(req: ApproveLegitimateCallerRequest) -> ApproveLegitimateCallerResponse:
    """
    Bolna mid-call tool to verify legitimate delivery / service personnel (e.g. Swiggy, Blinkit, Apollo).
    Guarded by an instant scam indicator check. If OTP/money/KYC is requested, rejects and instructs bait/hangup.
    If clean: marks call as 'safe_delivery', notifies family, broadcasts SSE, and hands off gracefully.
    """
    effective_id = resolve_effective_tool_call_id(req.call_id, req.execution_id)
    combined_text = f"{req.caller_type} {req.brand_or_person} {req.delivery_details}".lower()
    
    # Safety guardrail: reject if high-risk scam indicators found
    has_scam_indicator = any(indicator in combined_text for indicator in SCAM_INDICATORS)
    if has_scam_indicator:
        logger.warning(
            "approve_legitimate_caller REJECTED for call_id=%s: scam indicator detected in '%s'",
            effective_id,
            req.delivery_details,
        )
        return ApproveLegitimateCallerResponse(
            status="rejected",
            approved=False,
            call_id=effective_id,
            brand_or_person=req.brand_or_person,
            caller_type=req.caller_type,
            delivery_details=req.delivery_details,
            reason="High-risk scam indicator (OTP/UPI/fee/code) detected in delivery details",
            spoken_instruction="यह डिलीवरी फर्जी लग रही है। डिलीवरी वाला पैसे या ओटीपी मांग रहा है। मना करें और फोन काटें या हनीपॉट पर स्विच करें।",
        )

    # 1. Update SQLite call verdict
    update_call_verdict(effective_id, "safe_delivery")

    # 2. Family notification
    notify_msg = f"✅ VERIFIED CALLER: {req.brand_or_person} ({req.caller_type}) — {req.delivery_details}. Safe to attend at gate/door."
    logger.info("Legitimate caller approved for call_id=%s: %s", effective_id, notify_msg)
    try:
        from app.notify.alerts import build_dispatcher_from_env
        dispatcher = build_dispatcher_from_env()
        if dispatcher and getattr(dispatcher, "twilio_client", None):
            from_num = os.getenv("TWILIO_PHONE_NUMBER") or os.getenv("TWILIO_WHATSAPP_NUMBER")
            to_num = os.getenv("SON_PHONE_NUMBER", "+919876543210")
            dispatcher.twilio_client.messages.create(body=notify_msg, from_=from_num, to=to_num)
    except Exception as e:
        logger.warning("Could not send legitimate delivery alert: %s", e)

    # 3. Broadcast SSE to dashboard
    broadcast_sse({
        "event": "legitimate_caller_approved",
        "call_id": effective_id,
        "brand": req.brand_or_person,
        "caller_type": req.caller_type,
        "details": req.delivery_details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # 4. Spoken response for Ramesh
    spoken = (
        f"हाँ बेटा, मैं गेट के गार्ड को बोल देता हूँ, पार्सल वहीं रख दो। थैंक यू। "
        f"[SYSTEM: Call verified legitimate {req.brand_or_person} delivery. Politely end call.]"
    )
    return ApproveLegitimateCallerResponse(
        status="approved",
        approved=True,
        call_id=effective_id,
        brand_or_person=req.brand_or_person,
        caller_type=req.caller_type,
        delivery_details=req.delivery_details,
        spoken_instruction=spoken,
    )


@router.post("/log_intel", response_model=LogIntelResponse)
async def api_log_intel(req: LogIntelRequest) -> LogIntelResponse:
    """
    Log scammer intelligence heard mid-call, storing both raw and normalized forms.
    Accepts either `value` (Bolna prompt) or `value_as_heard` (schema).
    Unparseable values are stored with `unparseable=True` so no evidence is ever lost.
    Creates a pending CallRecord if `call_id` does not exist yet.
    """
    effective_id = resolve_effective_tool_call_id(req.call_id, req.execution_id)
    kind = req.kind
    raw_val = req.value_raw
    norm_val, unparseable = normalize_and_validate_single_intel(kind, raw_val)
    if unparseable and req.value_normalized and req.value_normalized.strip():
        # Fall back to the agent's own canonical form, but only if it passes the same validator.
        hint_val, hint_unparseable = normalize_and_validate_single_intel(kind, req.value_normalized)
        if not hint_unparseable:
            norm_val, unparseable = hint_val, False
    quote = req.quote.strip()[:QUOTE_MAX_CHARS] if req.quote and req.quote.strip() else None
    entry = append_mid_call_intel(
        call_id=effective_id,
        intel_type=kind,
        value_as_heard=raw_val,
        normalized_value=norm_val,
        unparseable=unparseable,
        elicitation=_canonical_elicitation(req.elicitation),
        quote=quote,
        turn_index=req.turn_index,
        seconds_from_start=req.seconds_from_start,
    )
    beneficiary_name: Optional[str] = None
    bank_name: Optional[str] = None
    bank_branch: Optional[str] = None
    bank_city: Optional[str] = None
    bank_state: Optional[str] = None
    spoken_hint: Optional[str] = None
    syndicate_match: bool = False
    linked_call_ids: List[str] = []

    norm_val_final = entry.get("normalized_value") or norm_val

    # IFSC lookup via Razorpay API or offline fallback
    if (kind == "ifsc" or is_valid_ifsc(norm_val_final)) and not entry.get("is_bait", False):
        try:
            ifsc_res = await resolve_ifsc(norm_val_final)
            if ifsc_res:
                bank_name = ifsc_res.get("bank") or bank_name
                bank_branch = ifsc_res.get("branch")
                bank_city = ifsc_res.get("city")
                bank_state = ifsc_res.get("state")
                spoken_hint = generate_ifsc_spoken_hint(ifsc_res)
        except Exception as exc:
            logger.warning("IFSC resolution error: %s", exc)

    if not entry["unparseable"] and not entry.get("is_bait", False) and norm_val_final:
        try:
            syn_res = ingest_scam_identifier(
                call_id=effective_id,
                identifier_type=entry["type"],
                normalized_value=norm_val_final,
            )
            pd = (syn_res or {}).get("penny_drop") or {}
            beneficiary_name = beneficiary_name or pd.get("beneficiary_name")
            bank_name = bank_name or pd.get("bank_name")
        except Exception as exc:
            logger.warning("Syndicate ingestion warning for call %s: %s", effective_id, exc)

        # Cross-call mule tracking in mule_identifiers table
        try:
            mule_res = upsert_mule_identifier(
                identifier_type=entry["type"],
                identifier_value=norm_val_final,
                call_id=effective_id,
                bank_city=bank_city or "",
                bank_state=bank_state or "",
                bank_branch=bank_branch or "",
            )
            if mule_res.get("syndicate_match"):
                syndicate_match = True
                linked_call_ids = mule_res.get("linked_call_ids") or []
                broadcast_sse({
                    "event": "syndicate_match_detected",
                    "call_id": effective_id,
                    "identifier": norm_val_final,
                    "type": entry["type"],
                    "hit_count": mule_res.get("hit_count", 2),
                    "linked_calls": linked_call_ids,
                    "bank_city": bank_city or "",
                    "bank_state": bank_state or "",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as exc:
            logger.warning("Mule identifier upsert error: %s", exc)

    # Mid-call context injection (e.g. Amit confirmed safe)
    family_intel = get_family_intel_injection(effective_id)

    logger.info(
        "log_intel effective_id=%s raw_call_id=%s raw_execution_id=%s type=%s normalized=%s unparseable=%s ifsc_city=%s syn_match=%s",
        effective_id,
        req.call_id,
        req.execution_id,
        kind,
        norm_val,
        unparseable,
        bank_city,
        syndicate_match,
    )
    return LogIntelResponse(
        status="logged",
        call_id=effective_id,
        kind=entry["kind"],
        type=entry["type"],
        value=entry["value_as_heard"],
        value_raw=entry["value_raw"],
        value_as_heard=entry["value_as_heard"],
        value_normalized=entry["normalized_value"],
        normalized_value=entry["normalized_value"],
        unparseable=entry["unparseable"],
        elicitation=entry.get("elicitation"),
        quote=entry.get("quote"),
        turn_index=entry.get("turn_index"),
        seconds_from_start=entry.get("seconds_from_start"),
        is_bait=entry.get("is_bait", False),
        duplicate=entry["duplicate"],
        times_logged=entry["times_logged"],
        identifiers_logged=entry["identifiers_logged"],
        beneficiary_name=beneficiary_name,
        bank_name=bank_name,
        bank_branch=bank_branch,
        bank_city=bank_city,
        bank_state=bank_state,
        spoken_hint=spoken_hint,
        syndicate_match=syndicate_match,
        linked_call_ids=linked_call_ids,
        system_intel=family_intel,
    )
