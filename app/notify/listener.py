"""
Event Listener for call.finalized (Lane C / T-ALERT).
File: app/notify/listener.py

Receives call.finalized events (from Bolna webhook or backend CallRecord finalization)
and triggers FamilyAlertDispatcher. Ensures failed alert sends never crash or corrupt
the webhook or caller.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel

from app.notify.alerts import (
    AlertResult,
    AlertStatus,
    FamilyAlertDispatcher,
    build_dispatcher_from_env,
)

logger = logging.getLogger("guardianline.listener")

router = APIRouter(prefix="/events", tags=["events"])

_DEFAULT_DISPATCHER: Optional[FamilyAlertDispatcher] = None


def get_default_dispatcher() -> FamilyAlertDispatcher:
    global _DEFAULT_DISPATCHER
    if _DEFAULT_DISPATCHER is None:
        try:
            _DEFAULT_DISPATCHER = build_dispatcher_from_env()
        except Exception as e:
            logger.warning("Could not build dispatcher from env, initializing mock: %s", e)
            from app.notify.alerts import AlertConfig, AlertChannel, PersistentAlertStore
            _DEFAULT_DISPATCHER = FamilyAlertDispatcher(
                config=AlertConfig(to_phone="+919876543210", channel=AlertChannel.WHATSAPP),
                store=PersistentAlertStore(":memory:"),
            )
    return _DEFAULT_DISPATCHER


def set_default_dispatcher(dispatcher: FamilyAlertDispatcher) -> None:
    global _DEFAULT_DISPATCHER
    _DEFAULT_DISPATCHER = dispatcher


def handle_call_finalized_event(
    event: Dict[str, Any],
    dispatcher: Optional[FamilyAlertDispatcher] = None,
) -> AlertResult:
    """
    Subscribes to 'call.finalized' event and dispatches family alert.
    Guarantees fail-safe execution: any exception is caught and logged,
    never propagating an unhandled error to the webhook processor.
    """
    event_type = event.get("event")
    call_id = str(event.get("call_id") or "unknown")

    if event_type != "call.finalized":
        logger.debug("Ignoring non-call.finalized event: %s", event_type)
        return AlertResult(
            status=AlertStatus.SKIPPED,
            call_id=call_id,
            reason=f"IGNORED_EVENT_{event_type}",
            recipient="",
            channel=get_default_dispatcher().config.channel,
        )

    record = event.get("record")
    if not isinstance(record, dict):
        logger.error("Invalid call.finalized event: missing or malformed 'record' dict for call %s", call_id)
        return AlertResult(
            status=AlertStatus.FAILED,
            call_id=call_id,
            reason="INVALID_EVENT_RECORD",
            recipient="",
            channel=get_default_dispatcher().config.channel,
        )

    # Ensure call_id is propagated in record
    if "call_id" not in record or not record["call_id"]:
        record["call_id"] = call_id

    d = dispatcher or get_default_dispatcher()
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


@router.post("/call_finalized", response_model=Dict[str, Any])
def on_call_finalized_endpoint(
    event: Dict[str, Any],
    background_tasks: BackgroundTasks,
):
    """
    HTTP endpoint to ingest call.finalized event and trigger async family dispatch.
    """
    call_id = event.get("call_id", "unknown")
    background_tasks.add_task(handle_call_finalized_event, event)
    return {"status": "accepted", "call_id": call_id}
