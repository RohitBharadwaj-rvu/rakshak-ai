"""
app/voice/webhook.py - Bolna Post-Call Webhook & Authenticated CallRecord Read API
(T-HOOK, T-CLEAN, T-API, T-RPT, T-POST).
"""

import json
import logging
import os
from typing import Any, Callable, Dict, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

import app.voice.classifier as _classifier_mod
from app.agent.nodes.reflection import run_post_call_reflection
from app.core.enrichment import run_post_call_enrichment
from app.voice.cleanup import cleanup_call_intel
from app.voice.extractor import extract_from_transcript
from app.voice.report import generate_1930_report
from app.voice.store import (
    export_all_raw_rows,
    export_call_records_to_csv_string,
    finalize_call_record_from_webhook,
    get_call_record,
    list_call_records,
    mask_phone,
    resolve_and_merge_pending_mid_call_record,
    restore_raw_rows,
    save_post_call_enrichment_and_reflection,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bolna Post-Call Webhook & CallRecords"])

# Optional custom hooks for failure-injection testing (T-HOOK, T-POST)
_CLEANUP_FN: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
_REFLECTION_FN: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
_ENRICHMENT_FN: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

REQUIRED_WEBHOOK_FIELDS = {"call_id", "agent_id", "call_duration", "call_status", "transcript"}
VALID_CALL_STATUSES = {"completed", "failed", "busy", "no-answer", "in-progress", "canceled"}


def set_cleanup_hook(fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]) -> None:
    """Register or clear a custom post-call LLM cleanup override."""
    global _CLEANUP_FN
    _CLEANUP_FN = fn


def set_reflection_hook(fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]) -> None:
    """Register or clear a custom post-call reflection override (for T-POST testing)."""
    global _REFLECTION_FN
    _REFLECTION_FN = fn


def set_enrichment_hook(fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]) -> None:
    """Register or clear a custom post-call enrichment override (for T-POST testing)."""
    global _ENRICHMENT_FN
    _ENRICHMENT_FN = fn


def execute_post_call_tasks(record: Dict[str, Any]) -> None:
    """
    Execute post-call reflection and intelligence enrichment AFTER the CallRecord
    is saved and `call.finalized` has been emitted (T-POST).
    Never delays the webhook response or the family alert.
    Any failure in either task is logged with `call_id` and leaves the saved CallRecord intact.
    """
    call_id = str(record.get("call_id") or "unknown")
    reflection_out: Optional[Dict[str, Any]] = None
    enrichment_out: Optional[Dict[str, Any]] = None

    try:
        fn_ref = _REFLECTION_FN or run_post_call_reflection
        reflection_out = fn_ref(record)
    except Exception as exc:
        logger.error("Post-call reflection failed for call_id=%s: %s", call_id, exc)

    try:
        fn_enr = _ENRICHMENT_FN or run_post_call_enrichment
        enrichment_out = fn_enr(record)
    except Exception as exc:
        logger.error("Post-call enrichment failed for call_id=%s: %s", call_id, exc)

    if reflection_out is not None or enrichment_out is not None:
        try:
            save_post_call_enrichment_and_reflection(
                call_id=call_id,
                reflection=reflection_out,
                enrichment=enrichment_out,
            )
        except Exception as exc:
            logger.error(
                "Saving post-call reflection/enrichment failed for call_id=%s: %s",
                call_id,
                exc,
            )


import secrets


def get_expected_api_token() -> str:
    return os.getenv("GUARDIANLINE_API_TOKEN", "local_api_token_123")


def get_expected_webhook_secret() -> str:
    return os.getenv("BOLNA_WEBHOOK_SECRET", "").strip()


def verify_webhook_secret(request: Request) -> Optional[JSONResponse]:
    """
    Enforce `BOLNA_WEBHOOK_SECRET` on `POST /webhook` when configured (or in Render production).
    Accepts `Authorization: Bearer <secret>`, `X-Webhook-Secret: <secret>`, or `X-Bolna-Secret: <secret>`.
    Returns a 401 JSONResponse if unauthorized, or None if authorized.
    """
    expected = get_expected_webhook_secret()
    is_render = os.getenv("RENDER", "").lower() == "true"

    if not expected and not is_render:
        # Local/test mode with no BOLNA_WEBHOOK_SECRET set
        return None

    if not expected and is_render:
        logger.error("BOLNA_WEBHOOK_SECRET is not set in Render environment; rejecting /webhook request")
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid webhook secret"},
        )

    auth_header = (request.headers.get("authorization") or "").strip()
    provided: Optional[str] = None
    if auth_header.lower().startswith("bearer "):
        provided = auth_header[7:].strip()
    elif auth_header:
        provided = auth_header
    elif request.headers.get("x-webhook-secret"):
        provided = request.headers.get("x-webhook-secret", "").strip()
    elif request.headers.get("x-bolna-secret"):
        provided = request.headers.get("x-bolna-secret", "").strip()

    if not provided or not secrets.compare_digest(provided, expected):
        logger.warning("Unauthorized /webhook attempt (missing or invalid BOLNA_WEBHOOK_SECRET)")
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid webhook secret"},
        )
    return None


def require_api_token(
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> str:
    """
    Verify Bearer / API token on read routes (`/api/calls`, `/api/calls/{id}`, `/api/calls/{id}/report`).
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

    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid API token")
    return provided


import re

VALID_CALL_STATUSES = {
    "completed",
    "call-disconnected",
    "ended",
    "terminated",
    "failed",
    "busy",
    "no-answer",
    "in-progress",
    "canceled",
    "cancelled",
    "queued",
    "ringing",
    "initiated",
    "balance-low",
}

_SPEAKER_LINE_RE = re.compile(
    r"^\s*(assistant|agent|bot|user|caller|scammer|system)\s*:\s*(.*)$",
    re.IGNORECASE,
)


def _parse_bolna_transcript(raw_transcript: Any) -> Optional[list]:
    """
    Convert Bolna's `transcript` field into a list of `{"role": ..., "content": ...}` turn objects.
    Supports:
      1. Native Bolna multi-line string: "assistant: हैलो जी?\\nuser: मैं CBI से बोल रहा हूँ..."
      2. List of turn dicts: [{"role": "user", "content": "..."}]
      3. None / empty string (e.g., on early drop / no-answer calls) -> []
    Returns None if `raw_transcript` is an invalid type or contains malformed turn objects.
    """
    if raw_transcript is None:
        return []
    if isinstance(raw_transcript, str):
        turns = []
        for raw_line in raw_transcript.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m = _SPEAKER_LINE_RE.match(line)
            if m:
                raw_role = m.group(1).lower()
                content = m.group(2).strip()
                if raw_role in ("assistant", "agent", "bot"):
                    role = "assistant"
                elif raw_role in ("user", "caller", "scammer"):
                    role = "user"
                else:
                    role = "system"
                turns.append({"role": role, "content": content})
            elif turns:
                turns[-1]["content"] = f"{turns[-1]['content']} {line}".strip()
            else:
                turns.append({"role": "user", "content": line})
        return turns
    if isinstance(raw_transcript, list):
        normalized_turns = []
        for idx, turn in enumerate(raw_transcript):
            if not isinstance(turn, dict):
                return None
            role = turn.get("role") or turn.get("sender")
            content = turn.get("content") if "content" in turn else turn.get("text")
            if not isinstance(role, str) or not isinstance(content, str):
                return None
            entry: Dict[str, Any] = {"role": role, "content": content}
            if "timestamp" in turn and isinstance(turn["timestamp"], (int, float)):
                entry["timestamp"] = turn["timestamp"]
            normalized_turns.append(entry)
        return normalized_turns
    return None


def _normalize_and_validate_webhook_payload(data: Any) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Normalize a raw Bolna post-call webhook payload (supporting both native Bolna keys
    `id`, `conversation_duration`, `status`, `user_number`, `telephony_data.recording_url`,
    `telephony_data.provider_call_id` and legacy fixture keys `call_id`, `call_duration`,
    `call_status`, `caller_number`, `call_recording_url`).
    Returns `(normalized_payload, error_message)`.
    """
    if not isinstance(data, dict):
        return None, "Webhook payload must be a JSON object"

    is_native_bolna = "id" in data or "status" in data or "conversation_duration" in data or "telephony_data" in data
    telephony = data.get("telephony_data") if isinstance(data.get("telephony_data"), dict) else {}

    # 1. Call ID (`id` or `call_id` or `telephony_data.provider_call_id`)
    raw_call_id = data.get("id") or data.get("call_id") or telephony.get("provider_call_id")
    if not isinstance(raw_call_id, str) or not raw_call_id.strip():
        return None, "Missing or invalid required field 'id' / 'call_id'"
    call_id = raw_call_id.strip()

    # 2. Agent ID
    raw_agent_id = data.get("agent_id")
    if not isinstance(raw_agent_id, str) or not raw_agent_id.strip():
        return None, "Missing or invalid required field 'agent_id'"
    agent_id = raw_agent_id.strip()

    # 3. Call Status (`status` or `call_status`)
    raw_status = data.get("status") or data.get("call_status")
    if not isinstance(raw_status, str) or raw_status not in VALID_CALL_STATUSES:
        return None, f"Missing or invalid 'status' / 'call_status' (got {raw_status!r})"

    # 4. Duration (`conversation_duration`, `conversation_time`, `call_duration`, `telephony_data.duration`)
    raw_dur = (
        data.get("conversation_duration")
        if data.get("conversation_duration") is not None
        else (
            data.get("conversation_time")
            if data.get("conversation_time") is not None
            else (
                data.get("call_duration")
                if data.get("call_duration") is not None
                else telephony.get("duration")
            )
        )
    )
    if raw_dur is None:
        if is_native_bolna:
            call_duration = 0.0
        else:
            return None, "Missing required webhook field: call_duration"
    else:
        try:
            call_duration = float(raw_dur)
        except (TypeError, ValueError):
            return None, "Field 'conversation_duration' / 'call_duration' must be a number"
        if call_duration < 0:
            return None, "Field 'conversation_duration' / 'call_duration' must be non-negative"

    # 5. Transcript
    if "transcript" not in data and not is_native_bolna:
        return None, "Missing required webhook field: transcript"
    parsed_transcript = _parse_bolna_transcript(data.get("transcript"))
    if parsed_transcript is None:
        return None, "Field 'transcript' must be a speaker-prefixed string or list of turn objects with 'role' and 'content'"

    # 6. Caller number (`user_number`, `caller_number`, or `telephony_data.from_number` on inbound)
    raw_caller = data.get("user_number")
    if raw_caller is None:
        raw_caller = data.get("caller_number")
    if not raw_caller and telephony.get("call_type") == "inbound":
        raw_caller = telephony.get("from_number")
    caller_number = str(raw_caller or "").strip()

    # 7. Recording URL & Provider Call ID (`telephony_data.recording_url`, `telephony_data.provider_call_id`)
    recording_url = str(
        telephony.get("recording_url") or data.get("call_recording_url") or ""
    ).strip()
    provider_call_id = str(
        telephony.get("provider_call_id") or data.get("provider_call_id") or ""
    ).strip()

    metadata = dict(data.get("metadata") or {})
    if provider_call_id and "provider_call_id" not in metadata:
        metadata["provider_call_id"] = provider_call_id
    if telephony.get("provider") and "telephony_provider" not in metadata:
        metadata["telephony_provider"] = telephony.get("provider")

    normalized = {
        **data,
        "id": call_id,
        "call_id": call_id,
        "agent_id": agent_id,
        "user_number": caller_number,
        "caller_number": caller_number,
        "conversation_duration": call_duration,
        "call_duration": call_duration,
        "status": raw_status,
        "call_status": raw_status,
        "call_recording_url": recording_url,
        "provider_call_id": provider_call_id,
        "transcript": parsed_transcript,
        "metadata": metadata,
    }
    return normalized, None


@router.post("/webhook")
async def bolna_post_call_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive Bolna's post-call webhook payload (native Bolna format or fixture format),
    merge any mid-call `log_intel` captures, run rule-based transcript extraction +
    grounded post-call cleanup, store a finalized `CallRecord` in SQLite, fire
    `call.finalized` once, and schedule post-call reflection and enrichment in the background.
    """
    auth_err = verify_webhook_secret(request)
    if auth_err is not None:
        return auth_err

    try:
        raw_body = await request.body()
        raw_payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.warning("Malformed JSON on /webhook: %s", exc)
        return JSONResponse(
            status_code=400,
            content={"detail": "Malformed JSON payload", "call_id": None},
        )

    call_id_hint = (
        (raw_payload.get("id") or raw_payload.get("call_id"))
        if isinstance(raw_payload, dict)
        else None
    )
    payload, err = _normalize_and_validate_webhook_payload(raw_payload)
    if err or payload is None:
        logger.warning("Invalid webhook payload call_id=%s error=%s", call_id_hint, err)
        return JSONResponse(
            status_code=400,
            content={"detail": err, "call_id": call_id_hint},
        )

    call_id = payload["call_id"]
    caller_number = payload["caller_number"]
    transcript = payload["transcript"]
    metadata = payload["metadata"]
    language = str(metadata.get("language") or "hi")

    logger.info(
        "Webhook received call_id=%s provider_call_id=%s caller=%s turns=%d duration=%ss",
        call_id,
        payload.get("provider_call_id") or "<none>",
        mask_phone(caller_number),
        len(transcript),
        payload.get("call_duration", 0),
    )

    existing = resolve_and_merge_pending_mid_call_record(
        call_id=call_id,
        provider_call_id=payload.get("provider_call_id"),
    )
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

    # Step 4: Schedule post-call reflection & enrichment in the background (T-POST)
    # Runs AFTER the CallRecord is saved and `call.finalized` has been emitted.
    background_tasks.add_task(execute_post_call_tasks, record)

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


@router.get("/api/calls/export.csv")
async def api_export_calls_csv(
    _token: str = Depends(require_api_token),
):
    """
    Export all CallRecords as a CSV file for the Sprint 3/4 metrics script (T-MET).
    Requires valid API token.
    """
    csv_text = export_call_records_to_csv_string()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="call_records.csv"'},
    )


@router.get("/api/calls/backup.json")
async def api_backup_calls_json(
    _token: str = Depends(require_api_token),
):
    """
    Export a full raw SQLite snapshot of all CallRecords as JSON so they can be
    backed up before or restored after a stateless container redeploy.
    """
    rows = export_all_raw_rows()
    return {"count": len(rows), "rows": rows}


@router.post("/api/calls/restore.json")
async def api_restore_calls_json(
    request: Request,
    _token: str = Depends(require_api_token),
):
    """
    Restore raw CallRecord rows from a backup snapshot produced by `/api/calls/backup.json`.
    """
    data = await request.json()
    rows = data.get("rows", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="Expected JSON list of rows or {'rows': [...]}")
    restored = restore_raw_rows(rows)
    return {"restored": restored}


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


@router.get("/api/calls/{call_id}/report")
async def api_get_call_report(
    call_id: str,
    format: str = Query(default="text", pattern="^(text|json)$"),
    _token: str = Depends(require_api_token),
):
    """
    Generate and return the pre-filled 1930 cybercrime report for `call_id` (T-RPT).
    Linked directly from the family alert (`report_link`). Requires valid API token.
    """
    record = get_call_record(call_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"CallRecord '{call_id}' not found")
    report_text = generate_1930_report(record)
    if format == "json":
        return {"call_id": call_id, "report": report_text}
    return PlainTextResponse(content=report_text)
