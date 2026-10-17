"""
Event Listener for call.finalized (Lane C / T-ALERT).
File: app/notify/listener.py

Lane B fires `call.finalized` in-process from `app.voice.store` (see
`register_call_finalized_listener`). The event is flat, per B's
`contracts/call_finalized.schema.json`:

    {"event", "call_id", "verdict", "caller_number", "timestamp", "report_link", "extracted_intel"}

It carries no summary or transcript, so the full CallRecord is loaded from B's store
when it is available. An older nested shape ({"event", "call_id", "record": {...}}) is
still accepted for replay tooling.

Failed alert sends never raise into the webhook that fired the event.
"""

import logging
import os
import secrets
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from app.notify.alerts import (
    AlertChannel,
    AlertResult,
    AlertStatus,
    FamilyAlertDispatcher,
    build_dispatcher_from_env,
)

logger = logging.getLogger("guardianline.listener")

router = APIRouter(prefix="/events", tags=["events"])

_DEFAULT_DISPATCHER: Optional[FamilyAlertDispatcher] = None

# Loads a full CallRecord by call_id. Set to Lane B's `get_call_record` by app.core.lane_c.install().
_RECORD_LOADER: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None


def get_default_dispatcher() -> Optional[FamilyAlertDispatcher]:
    """Builds the dispatcher from env once. Returns None when alerts are not configured."""
    global _DEFAULT_DISPATCHER
    if _DEFAULT_DISPATCHER is None:
        try:
            _DEFAULT_DISPATCHER = build_dispatcher_from_env()
        except ValueError as e:
            logger.error("Family alerts disabled: %s", e)
            return None
    return _DEFAULT_DISPATCHER


def set_default_dispatcher(dispatcher: Optional[FamilyAlertDispatcher]) -> None:
    global _DEFAULT_DISPATCHER
    _DEFAULT_DISPATCHER = dispatcher


def set_record_loader(loader: Optional[Callable[[str], Optional[Dict[str, Any]]]]) -> None:
    global _RECORD_LOADER
    _RECORD_LOADER = loader


def _record_from_event(event: Dict[str, Any], call_id: str) -> Optional[Dict[str, Any]]:
    """Returns the CallRecord to alert on: B's stored record, else the nested or flat event."""
    if _RECORD_LOADER is not None:
        try:
            stored = _RECORD_LOADER(call_id)
            if stored:
                return dict(stored)
        except Exception as e:
            logger.warning("Could not load CallRecord %s from store, using event payload: %s", call_id, e)

    nested = event.get("record")
    if isinstance(nested, dict):
        record = dict(nested)
        record.setdefault("call_id", call_id)
        return record

    if "verdict" in event:
        return {
            "call_id": call_id,
            "caller_number": event.get("caller_number"),
            "verdict": event.get("verdict"),
            "extracted_intel": event.get("extracted_intel") or {},
            "report_link": event.get("report_link"),
            "start_time": event.get("timestamp"),
        }
    return None


def handle_call_finalized_event(
    event: Dict[str, Any],
    dispatcher: Optional[FamilyAlertDispatcher] = None,
) -> AlertResult:
    """
    Subscribes to 'call.finalized' event and dispatches family alert.
    Never raises: any error is logged and returned as a FAILED result.
    """
    call_id = str(event.get("call_id") or "unknown")
    d = dispatcher or get_default_dispatcher()
    channel = d.config.channel if d else AlertChannel.WHATSAPP

    if event.get("event") != "call.finalized":
        logger.debug("Ignoring non-call.finalized event: %s", event.get("event"))
        return AlertResult(
            status=AlertStatus.SKIPPED,
            call_id=call_id,
            reason=f"IGNORED_EVENT_{event.get('event')}",
            recipient="",
            channel=channel,
        )

    if d is None:
        return AlertResult(
            status=AlertStatus.FAILED,
            call_id=call_id,
            reason="ALERTS_NOT_CONFIGURED",
            recipient="",
            channel=channel,
        )

    record = _record_from_event(event, call_id)
    if record is None:
        logger.error("Invalid call.finalized event for call %s: no verdict or record", call_id)
        return AlertResult(
            status=AlertStatus.FAILED,
            call_id=call_id,
            reason="INVALID_EVENT_RECORD",
            recipient="",
            channel=channel,
        )

    try:
        result = d.dispatch(record)
        logger.info("Processed call.finalized for call %s: status=%s", call_id, result.status)
        return result
    except Exception as e:
        logger.exception("Failed to dispatch alert for finalized call %s: %s", call_id, e)
        return AlertResult(
            status=AlertStatus.FAILED,
            call_id=call_id,
            reason=f"DISPATCHER_EXCEPTION: {e}",
            recipient=d.config.to_phone,
            channel=d.config.channel,
        )


def on_call_finalized(event: Dict[str, Any]) -> None:
    """
    In-process listener for Lane B's event bus. B calls listeners synchronously inside
    the webhook request, so the send runs on the dispatcher's thread pool.
    """
    d = get_default_dispatcher()
    if d is None:
        logger.error("call.finalized for %s dropped: family alerts not configured", event.get("call_id"))
        return
    try:
        from app.notify.alerts import _THREAD_POOL
        _THREAD_POOL.submit(handle_call_finalized_event, event, d)
    except Exception as e:
        logger.error("Could not queue family alert for %s: %s", event.get("call_id"), e)


def _require_events_token(
    authorization: Optional[str] = Header(None),
    x_events_token: Optional[str] = Header(None),
) -> None:
    expected = os.environ.get("GUARDIAN_EVENTS_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event ingestion is not configured (GUARDIAN_EVENTS_TOKEN unset)",
        )
    provided = None
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_events_token:
        provided = x_events_token.strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid events token")


@router.post("/call_finalized", response_model=Dict[str, Any])
def on_call_finalized_endpoint(
    event: Dict[str, Any],
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
    x_events_token: Optional[str] = Header(None),
):
    """
    HTTP ingestion of call.finalized, for replay tools and out-of-process backends.
    Requires GUARDIAN_EVENTS_TOKEN: an open endpoint would let anyone send the family
    a fake "scam alert" with attacker-chosen text.
    """
    _require_events_token(authorization, x_events_token)
    call_id = event.get("call_id", "unknown")
    background_tasks.add_task(handle_call_finalized_event, event)
    return {"status": "accepted", "call_id": call_id}
