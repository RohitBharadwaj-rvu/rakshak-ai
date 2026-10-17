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
from pydantic import AliasChoices, BaseModel, Field

from app.agent.state import get_persona_bundle
from app.voice.extractor import normalize_and_validate_single_intel
from app.voice.store import (
    append_mid_call_intel,
    get_or_assign_honeypot_persona,
    resolve_effective_tool_call_id,
)

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
    aadhaar: str = "9999 0000 1111"


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


class LogIntelRequest(BaseModel):
    call_id: str = Field(..., min_length=1, description="Unique identifier for the active call (e.g., %(call_sid)s)")
    execution_id: Optional[str] = Field(default=None, description="Optional Bolna execution ID (e.g., %(execution_id)s)")
    type: Literal["upi", "phone", "account", "ifsc", "link", "pan", "other"] = Field(
        ..., description="Category of intelligence heard mid-call"
    )
    value_as_heard: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("value_as_heard", "value"),
        description="Raw string heard by the agent (accepts 'value' or 'value_as_heard')",
    )


class LogIntelResponse(BaseModel):
    status: Literal["logged"]
    call_id: str
    type: str
    value: str
    value_as_heard: str
    normalized_value: str
    unparseable: bool


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
    raw_val = req.value_as_heard
    norm_val, unparseable = normalize_and_validate_single_intel(req.type, raw_val)
    entry = append_mid_call_intel(
        call_id=effective_id,
        intel_type=req.type,
        value_as_heard=raw_val,
        normalized_value=norm_val,
        unparseable=unparseable,
    )
    logger.info(
        "log_intel effective_id=%s raw_call_id=%s raw_execution_id=%s type=%s normalized=%s unparseable=%s",
        effective_id,
        req.call_id,
        req.execution_id,
        req.type,
        norm_val,
        unparseable,
    )
    return LogIntelResponse(
        status="logged",
        call_id=effective_id,
        type=entry["type"],
        value=entry["value_as_heard"],
        value_as_heard=entry["value_as_heard"],
        normalized_value=entry["normalized_value"],
        unparseable=entry["unparseable"],
    )

