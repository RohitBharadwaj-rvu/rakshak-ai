"""
app/voice/webhook.py - Bolna Post-Call Webhook & Authenticated CallRecord Read API (T-HOOK, T-CLEAN, T-API).
"""

import json
import logging
import os
from typing import Any, Callable, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

import app.voice.classifier as _classifier_mod
from app.voice.cleanup import cleanup_call_intel
from app.voice.extractor import extract_from_transcript
from app.voice.store import (
    finalize_call_record_from_webhook,
    get_call_record,
    list_call_records,
    mask_phone,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bolna Post-Call Webhook & CallRecords"])

# Optional custom cleanup override for failure-injection testing (T-HOOK)
_CLEANUP_FN: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

REQUIRED_WEBHOOK_FIELDS = {"call_id", "agent_id", "call_duration", "call_status", "transcript"}
VALID_CALL_STATUSES = {"completed", "failed", "busy", "no-answer", "in-progress", "canceled"}


def set_cleanup_hook(fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]) -> None:
    """Register or clear a custom post-call LLM cleanup override."""
    global _CLEANUP_FN
    _CLEANUP_FN = fn


def get_expected_api_token() -> str:
    return os.getenv("GUARDIANLINE_API_TOKEN", "local_api_token_123")


def require_api_token(
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> str:
    """
    Verify Bearer / API token on read routes (`/api/calls`, `/api/calls/{id}`).
    Returns HTTP 401 on missing or invalid token (T-API, T-PRIV).
    """
    expected = get_expected_api_token()
    provided: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_api_token:
        provided = x_api_token.strip()
    elif token:
        provided = token.strip()

    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid API token")
    return provided


def _validate_webhook_payload(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return "Webhook payload must be a JSON object"
    missing = [f for f in REQUIRED_WEBHOOK_FIELDS if f not in data]
    if missing:
        return f"Missing required webhook field(s): {', '.join(sorted(missing))}"
    if not isinstance(data.get("call_id"), str) or not data["call_id"].strip():
        return "Field 'call_id' must be a non-empty string"
    if not isinstance(data.get("agent_id"), str) or not data["agent_id"].strip():
        return "Field 'agent_id' must be a non-empty string"
    if not isinstance(data.get("call_duration"), (int, float)) or data["call_duration"] < 0:
        return "Field 'call_duration' must be a non-negative number"
    if data.get("call_status") not in VALID_CALL_STATUSES:
        return f"Field 'call_status' must be one of {sorted(VALID_CALL_STATUSES)}"
    if not isinstance(data.get("transcript"), list):
        return "Field 'transcript' must be a list of turn objects"
    for idx, turn in enumerate(data["transcript"]):
        if not isinstance(turn, dict) or "role" not in turn or "content" not in turn:
            return f"Transcript turn at index {idx} must be an object with 'role' and 'content'"
    return None


@router.post("/webhook")
async def bolna_post_call_webhook(request: Request):
    """
    Receive Bolna's post-call webhook payload, merge any mid-call `log_intel` captures,
    run rule-based transcript extraction + grounded post-call cleanup, store a finalized
    `CallRecord` in SQLite, and fire `call.finalized` once.
    """
    try:
        raw_body = await request.body()
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.warning("Malformed JSON on /webhook: %s", exc)
        return JSONResponse(
            status_code=400,
            content={"detail": "Malformed JSON payload", "call_id": None},
        )

    call_id_hint = payload.get("call_id") if isinstance(payload, dict) else None
    err = _validate_webhook_payload(payload)
    if err:
        logger.warning("Invalid webhook payload call_id=%s error=%s", call_id_hint, err)
        return JSONResponse(
            status_code=400,
            content={"detail": err, "call_id": call_id_hint},
        )

    call_id = str(payload["call_id"]).strip()
    caller_number = str(payload.get("caller_number") or "").strip()
    transcript = payload.get("transcript") or []
    metadata = payload.get("metadata") or {}
    language = str(metadata.get("language") or "hi")

    logger.info(
        "Webhook received call_id=%s caller=%s turns=%d duration=%ss",
        call_id,
        mask_phone(caller_number),
        len(transcript),
        payload.get("call_duration", 0),
    )

    existing = get_call_record(call_id)
    if existing and existing.get("status") == "finalized":
        record = finalize_call_record_from_webhook(
            payload=payload,
            extracted_intel=existing["extracted_intel"],
            verdict=existing["verdict"],
            confidence=existing.get("confidence", 0.9),
            summary=existing["summary"],
            status_value=existing["status"],
        )
        return record

    existing_mid_logs = (
        existing.get("extracted_intel", {}).get("mid_call_logs", []) if existing else []
    )

    # Step 1: Rule-based extraction + mid-call log merge
    extracted_intel = extract_from_transcript(
        transcript=transcript,
        mid_call_logs=existing_mid_logs,
    )

    # Step 2: Verdict classification
    cls_res = _classifier_mod.classify_caller(
        call_id=call_id,
        caller_number=caller_number,
        conversation=transcript,
        language=language,
    )
    verdict = cls_res.verdict
    confidence = cls_res.confidence

    has_scam_intel = bool(
        extracted_intel["upi_ids"]
        or extracted_intel["bank_accounts"]
        or extracted_intel["ifsc_codes"]
        or extracted_intel["links"]
    )
    if existing and existing.get("verdict") == "scam":
        verdict = "scam"
        confidence = max(confidence, 0.95)
    elif has_scam_intel and verdict != "genuine":
        verdict = "scam"
        confidence = max(confidence, 0.92)

    status_value = "finalized"
    summary = ""

    # Step 3: Post-call cleanup & grounded summary (T-CLEAN)
    try:
        if _CLEANUP_FN is not None:
            cleanup_out = _CLEANUP_FN(
                {
                    "call_id": call_id,
                    "transcript": transcript,
                    "extracted_intel": extracted_intel,
                    "verdict": verdict,
                }
            )
        else:
            cleanup_out = cleanup_call_intel(
                transcript=transcript,
                verdict=verdict,
                mid_call_logs=extracted_intel.get("mid_call_logs", []),
                metadata=metadata,
            )
            # Preserve any valid pre-webhook mid_call_logs that were merged in Step 1
            for k in ("upi_ids", "phone_numbers", "bank_accounts", "ifsc_codes", "pan_numbers", "links"):
                for v in extracted_intel.get(k, []):
                    if v not in cleanup_out["extracted_intel"][k]:
                        cleanup_out["extracted_intel"][k].append(v)

        if isinstance(cleanup_out, dict):
            if "extracted_intel" in cleanup_out:
                extracted_intel = cleanup_out["extracted_intel"]
            if "summary" in cleanup_out and cleanup_out["summary"]:
                summary = cleanup_out["summary"]
    except Exception as exc:
        logger.error("Post-call cleanup failed for call_id=%s: %s", call_id, exc)
        status_value = "cleanup_pending"
        summary = f"Call verdict is {verdict}. Post-call cleanup pending retry."

    record = finalize_call_record_from_webhook(
        payload=payload,
        extracted_intel=extracted_intel,
        verdict=verdict,
        confidence=confidence,
        summary=summary,
        status_value=status_value,
    )
    return record


@router.get("/api/calls")
async def api_list_calls(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=50),
    verdict: Optional[str] = Query(default=None),
    _token: str = Depends(require_api_token),
):
    """
    List CallRecords newest-first, 50 per page, optionally filtered by verdict (T-API).
    Requires valid API token.
    """
    offset = (page - 1) * limit
    records = list_call_records(limit=limit, verdict=verdict, offset=offset)
    return {
        "calls": records,
        "page": page,
        "per_page": limit,
        "count": len(records),
    }


@router.get("/api/calls/{call_id}")
async def api_get_call(
    call_id: str,
    _token: str = Depends(require_api_token),
):
    """Retrieve a single CallRecord by ID (T-API). Requires valid API token."""
    record = get_call_record(call_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"CallRecord '{call_id}' not found")
    return record
