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
from app.voice.store import (
    append_mid_call_intel,
    get_or_assign_honeypot_persona,
    resolve_effective_tool_call_id,
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
    return SwitchToHoneypotResponse(**bundle)


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
    if not entry["unparseable"] and not entry.get("is_bait", False) and entry.get("normalized_value"):
        try:
            syn_res = ingest_scam_identifier(
                call_id=effective_id,
                identifier_type=entry["type"],
                normalized_value=entry["normalized_value"],
            )
            pd = (syn_res or {}).get("penny_drop") or {}
            beneficiary_name = pd.get("beneficiary_name")
            bank_name = pd.get("bank_name")
        except Exception as exc:
            logger.warning("Syndicate ingestion warning for call %s: %s", effective_id, exc)
    logger.info(
        "log_intel effective_id=%s raw_call_id=%s raw_execution_id=%s type=%s normalized=%s unparseable=%s",
        effective_id,
        req.call_id,
        req.execution_id,
        kind,
        norm_val,
        unparseable,
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
    )
