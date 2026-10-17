"""
app/voice/tools.py - Mid-Call Bolna Custom Function Tool Endpoints (T-TOOLS).

Implements:
  - POST /tools/switch_to_honeypot
  - POST /tools/log_intel
"""

import logging
from typing import Dict, List, Literal, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agent.state import get_persona_bundle
from app.voice.extractor import normalize_and_validate_single_intel
from app.voice.store import append_mid_call_intel, get_or_assign_honeypot_persona

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["Bolna Mid-Call Tools"])


class SwitchToHoneypotRequest(BaseModel):
    call_id: str = Field(..., min_length=1, description="Unique identifier for the active call")
    language: Optional[str] = Field(default="hi", description="Requested persona language (hi, en, hinglish)")
    persona_id: Optional[str] = Field(default=None, description="Optional preferred persona key")


class FakeBaitModel(BaseModel):
    upi_id: str
    account_number: str
    ifsc_code: str
    phone_number: str


class SwitchToHoneypotResponse(BaseModel):
    call_id: str
    language: str
    persona_id: str
    persona_name: str
    persona_age: int
    persona_city: str
    persona_lines: List[str]
    fake_bait: FakeBaitModel


class LogIntelRequest(BaseModel):
    call_id: str = Field(..., min_length=1, description="Unique identifier for the active call")
    type: Literal["upi", "phone", "account", "ifsc", "link", "pan", "other"] = Field(
        ..., description="Category of intelligence heard mid-call"
    )
    value_as_heard: str = Field(..., min_length=1, description="Raw string heard by the agent")


class LogIntelResponse(BaseModel):
    status: Literal["logged"]
    call_id: str
    type: str
    value_as_heard: str
    normalized_value: str
    unparseable: bool


@router.post("/switch_to_honeypot", response_model=SwitchToHoneypotResponse)
async def api_switch_to_honeypot(req: SwitchToHoneypotRequest) -> SwitchToHoneypotResponse:
    """
    Switch the voice agent from screening receptionist mode to an elderly honeypot persona.
    Idempotent per `call_id`; unknown language falls back to Hindi (`hi`).
    """
    bundle = get_or_assign_honeypot_persona(
        call_id=req.call_id,
        bundle_factory=lambda: get_persona_bundle(
            call_id=req.call_id,
            language=req.language,
            preferred_persona=req.persona_id,
        ),
    )
    logger.info(
        "switch_to_honeypot call_id=%s persona=%s language=%s",
        req.call_id,
        bundle["persona_id"],
        bundle["language"],
    )
    return SwitchToHoneypotResponse(**bundle)


@router.post("/log_intel", response_model=LogIntelResponse)
async def api_log_intel(req: LogIntelRequest) -> LogIntelResponse:
    """
    Log scammer intelligence heard mid-call, storing both raw and normalized forms.
    Unparseable values are stored with `unparseable=True` so no evidence is ever lost.
    Creates a pending CallRecord if `call_id` does not exist yet.
    """
    norm_val, unparseable = normalize_and_validate_single_intel(req.type, req.value_as_heard)
    entry = append_mid_call_intel(
        call_id=req.call_id,
        intel_type=req.type,
        value_as_heard=req.value_as_heard,
        normalized_value=norm_val,
        unparseable=unparseable,
    )
    logger.info(
        "log_intel call_id=%s type=%s normalized=%s unparseable=%s",
        req.call_id,
        req.type,
        norm_val,
        unparseable,
    )
    return LogIntelResponse(
        status="logged",
        call_id=req.call_id,
        type=entry["type"],
        value_as_heard=entry["value_as_heard"],
        normalized_value=entry["normalized_value"],
        unparseable=entry["unparseable"],
    )
