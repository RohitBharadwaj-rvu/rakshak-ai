"""
app/api/classifier_router.py - FastAPI Router for Real-Time Caller Classification.

Exposes the hybrid classify_caller engine as an HTTP service for:
  - Lane A: Bolna voice agent custom function tool call
  - Lane B: FastAPI backend router integration
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import logging
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

import app.voice.classifier as _classifier_mod
from app.voice.classifier import CallerClassificationResult
from app.voice.store import resolve_effective_tool_call_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["Classifier Tools"])

_EXECUTOR = ThreadPoolExecutor(max_workers=8)
HARD_TIMEOUT_SECONDS = 1.5


class ConversationTurn(BaseModel):
    role: str = Field(default="caller", description="Role: caller, user, assistant, system")
    content: Optional[str] = Field(default=None, description="Utterance text")
    text: Optional[str] = Field(default=None, description="Alternative key for utterance text")

    def get_text(self) -> str:
        return self.content or self.text or ""


class ClassifyCallerRequest(BaseModel):
    call_id: str = Field(..., min_length=1, description="Unique identifier for the active call (e.g., %(call_sid)s)")
    execution_id: Optional[str] = Field(default=None, description="Optional Bolna execution ID (e.g., %(execution_id)s)")
    caller_number: Optional[str] = Field(default="", description="Inbound caller phone number")
    caller_summary: Optional[str] = Field(
        default=None,
        description="Agent-written summary of caller statements (Bolna mid-call parameter)",
    )
    conversation: Optional[List[ConversationTurn]] = Field(
        default_factory=list, description="Ordered transcript turns of the conversation so far"
    )
    language: str = Field(default="hi", description="Primary conversation language (hi, en, hinglish)")
    max_latency_budget_s: float = Field(
        default=1.4, description="Maximum latency budget in seconds before returning 'unsure'"
    )


class ClassifyCallerResponse(BaseModel):
    call_id: str
    verdict: str = Field(description="Classification verdict: scam, genuine, or unsure")
    confidence: float = Field(description="Scam probability score from 0.0 to 1.0")
    reason: str = Field(description="Explanatory rationale for the verdict")
    latency_ms: float = Field(description="Processing latency in milliseconds")
    method: str = Field(description="Resolution engine: heuristic, groq, gemini, or offline_rules")
    pillars_detected: List[str] = Field(default_factory=list, description="Active scam pillars detected")


@router.post("/classify_caller", response_model=ClassifyCallerResponse)
async def api_classify_caller(req: ClassifyCallerRequest):
    """
    Real-time caller classification endpoint for Bolna agent function tool.
    Guarantees response within 1.5s. Returns 'unsure' on any exception or timeout
    so the live conversation never hangs.
    """
    effective_id = resolve_effective_tool_call_id(req.call_id, req.execution_id)
    try:
        conv_dicts = (
            [{"role": t.role, "content": t.get_text()} for t in req.conversation]
            if req.conversation
            else []
        )
        if req.caller_summary and req.caller_summary.strip():
            conv_dicts.append({"role": "caller", "content": req.caller_summary.strip()})
        budget = min(float(req.max_latency_budget_s or 1.4), HARD_TIMEOUT_SECONDS)

        future = _EXECUTOR.submit(
            _classifier_mod.classify_caller,
            call_id=effective_id,
            caller_number=req.caller_number or "",
            conversation=conv_dicts,
            caller_summary=req.caller_summary,
            language=req.language,
            max_latency_budget_s=budget,
        )
        result: CallerClassificationResult = future.result(timeout=HARD_TIMEOUT_SECONDS)

        logger.info(
            "classify_caller effective_id=%s raw_call_id=%s raw_execution_id=%s verdict=%s confidence=%.2f",
            effective_id,
            req.call_id,
            req.execution_id,
            result.verdict,
            result.confidence,
        )
        return ClassifyCallerResponse(
            call_id=result.call_id,
            verdict=result.verdict,
            confidence=result.confidence,
            reason=result.reason,
            latency_ms=round(result.latency_ms, 2),
            method=result.method,
            pillars_detected=result.pillars_detected,
        )
    except FuturesTimeoutError:
        return ClassifyCallerResponse(
            call_id=req.call_id,
            verdict="unsure",
            confidence=0.50,
            reason="Classifier exceeded 1.5s latency budget; defaulting to unsure so screening continues",
            latency_ms=1500.0,
            method="timeout_fallback",
            pillars_detected=[],
        )
    except Exception as e:
        return ClassifyCallerResponse(
            call_id=req.call_id,
            verdict="unsure",
            confidence=0.50,
            reason=f"Classifier fallback on error: {type(e).__name__}",
            latency_ms=0.0,
            method="error_fallback",
            pillars_detected=[],
        )


@router.get("/classify_caller/health")
async def classifier_health():
    """Health check endpoint for the classification engine."""
    return {
        "status": "healthy",
        "service": "guardianline-classifier",
        "hybrid_stages": ["heuristic_scanner", "llm_semantic_layer", "offline_rules"],
    }
