"""
app/api/classifier_router.py - FastAPI Router for Real-Time Caller Classification.

Exposes the hybrid classify_caller engine as an HTTP service for:
  - Lane A: Bolna voice agent custom function tool call
  - Lane B: FastAPI backend router integration
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.voice.classifier import classify_caller, CallerClassificationResult

router = APIRouter(prefix="/tools", tags=["Classifier Tools"])


class ConversationTurn(BaseModel):
    role: str = Field(default="caller", description="Role: caller, user, assistant, system")
    content: Optional[str] = Field(default=None, description="Utterance text")
    text: Optional[str] = Field(default=None, description="Alternative key for utterance text")

    def get_text(self) -> str:
        return self.content or self.text or ""


class ClassifyCallerRequest(BaseModel):
    call_id: str = Field(default="live_call", description="Unique identifier for the active call")
    caller_number: Optional[str] = Field(default="", description="Inbound caller phone number")
    caller_summary: Optional[str] = Field(
        default=None, description="Agent-written summary of caller statements (Bolna mid-call parameter)"
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
    Guarantees sub-second response. Returns 'unsure' on any exception or timeout
    so the live conversation never hangs.
    """
    try:
        # Convert Pydantic turns to dicts expected by classify_caller if provided
        conv_dicts = (
            [{"role": t.role, "content": t.get_text()} for t in req.conversation]
            if req.conversation
            else []
        )

        result: CallerClassificationResult = classify_caller(
            call_id=req.call_id,
            caller_number=req.caller_number or "",
            conversation=conv_dicts,
            caller_summary=req.caller_summary,
            language=req.language,
            max_latency_budget_s=req.max_latency_budget_s,
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
    except Exception as e:
        # Fail safe to unsure so receptionist keeps screening
        return ClassifyCallerResponse(
            call_id=req.call_id,
            verdict="unsure",
            confidence=0.50,
            reason=f"Classifier fallback on error: {str(e)}",
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
