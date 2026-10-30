"""
app/voice/family_loop.py - Autonomous "Son-in-Trouble" Verification Loop (Anti-Kidnap Closed Loop).

When classify_caller detects a kidnap, accident, or extortion claim:
1. Marks call verification status as PENDING.
2. Dispatches an out-of-band verification alert to Amit (son in Pune) via WhatsApp/SMS.
3. Broadcasts real-time SSE event to the live dashboard.
4. If auto-simulation is enabled or when Amit/dashboard confirms, marks status as CONFIRMED_SAFE.
5. Injects ground-truth intelligence into the very next mid-call tool response for Ramesh AI.
"""

import asyncio
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

_LOOP_LOCK = threading.RLock()

# In-memory fast cache: call_id -> dict
_FAMILY_VERIFICATION_STATE: Dict[str, Dict[str, Any]] = {}

# Active SSE listeners or callbacks
_SSE_LISTENERS = []
_SSE_CLIENT_QUEUES: Set[asyncio.Queue] = set()


def register_sse_queue(q: asyncio.Queue) -> None:
    _SSE_CLIENT_QUEUES.add(q)


def unregister_sse_queue(q: asyncio.Queue) -> None:
    _SSE_CLIENT_QUEUES.discard(q)

KIDNAP_KEYWORDS = [
    "kidnap",
    "accident",
    "arrest",
    "son",
    "amit",
    "hospital",
    "police",
    "stealing",
    "captive",
    "hostage",
    "ransom",
    "shop",
    "theft",
    "chori",
    "choree",
    "beta",
    "beti",
    "bête",
    "bache",
    "दुकान",
    "बेटा",
    "चोरी",
    "पकड़ा",
    "बांध",
    "हादसा",
    "गिरफ्तार",
]


def register_sse_listener(callback):
    """Register listener for real-time dashboard SSE events."""
    if callback not in _SSE_LISTENERS:
        _SSE_LISTENERS.append(callback)


def broadcast_sse(event_data: Dict[str, Any]) -> None:
    """Broadcast an SSE event to all connected dashboard clients."""
    for listener in _SSE_LISTENERS:
        try:
            listener(event_data)
        except Exception as exc:
            logger.warning("Error broadcasting SSE event: %s", exc)
    
    # Forward to all connected browser SSE client queues
    payload = f"event: {event_data.get('event', 'message')}\ndata: {json.dumps(event_data)}\n\n"
    for q in list(_SSE_CLIENT_QUEUES):
        try:
            q.put_nowait(payload)
        except Exception:
            pass


def is_kidnap_scenario(text: Optional[str]) -> bool:
    """Check if caller summary or transcript implies a family kidnap, accident, or theft extortion."""
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in KIDNAP_KEYWORDS)


def get_call_family_status(call_id: str) -> Dict[str, Any]:
    """Retrieve the current family verification state for a call."""
    with _LOOP_LOCK:
        if call_id in _FAMILY_VERIFICATION_STATE:
            return dict(_FAMILY_VERIFICATION_STATE[call_id])
    
    # Check database fallback
    from app.voice.store import get_call_record
    rec = get_call_record(call_id)
    status = rec.get("family_verification_status", "NONE") if rec else "NONE"
    verified_at = rec.get("family_verified_at") if rec else None
    return {
        "call_id": call_id,
        "status": status,
        "verified_at": verified_at,
        "target": "Amit (Son - Pune)",
    }


def trigger_family_verification(
    call_id: str,
    caller_summary: Optional[str] = None,
    caller_number: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Trigger out-of-band verification to Amit in Pune.
    Sets status to PENDING, alerts guardian via Lane C, emits SSE, and starts auto-simulate if configured.
    """
    with _LOOP_LOCK:
        state = _FAMILY_VERIFICATION_STATE.get(call_id, {})
        # If already verified or pending, do not re-trigger
        if state.get("status") in ("PENDING", "CONFIRMED_SAFE"):
            return state

        now_iso = datetime.now(timezone.utc).isoformat()
        state = {
            "call_id": call_id,
            "status": "PENDING",
            "triggered_at": now_iso,
            "verified_at": None,
            "target": "Amit (Son - Pune)",
            "context_injected": False,
        }
        _FAMILY_VERIFICATION_STATE[call_id] = state

    # Update SQLite call_record
    try:
        from app.voice.store import update_call_family_verification
        update_call_family_verification(call_id, "PENDING", None)
    except Exception as exc:
        logger.warning("Could not persist family verification status to DB: %s", exc)

    # 1. Dispatch WhatsApp / SMS out-of-band alert to Amit
    msg = (
        "🚨 RAKSHAK URGENT ALERT: A caller on Papa's phone claims you (Amit) are in trouble/arrested "
        "and is demanding money. Reply '1' or 'SAFE' immediately to confirm you are safe."
    )
    logger.info("Out-of-band verification alert dispatched to Amit (Pune) for call_id=%s: %s", call_id, msg)

    try:
        from app.notify.alerts import build_dispatcher_from_env
        dispatcher = build_dispatcher_from_env()
        if dispatcher and getattr(dispatcher, "twilio_client", None):
            from_num = os.getenv("TWILIO_PHONE_NUMBER") or os.getenv("TWILIO_WHATSAPP_NUMBER")
            to_num = os.getenv("SON_PHONE_NUMBER", "+919876543210")
            dispatcher.twilio_client.messages.create(body=msg, from_=from_num, to=to_num)
    except Exception as e:
        logger.warning("Could not dispatch out-of-band alert message: %s", e)

    # 2. Broadcast SSE event
    broadcast_sse({
        "event": "family_verification_pending",
        "call_id": call_id,
        "target": "Amit (Son - Pune)",
        "timestamp": now_iso,
    })

    # 3. Check AUTO_SIMULATE_SON_SAFE_SECONDS for reliable demo execution
    auto_seconds_str = os.getenv("AUTO_SIMULATE_SON_SAFE_SECONDS", "").strip()
    if auto_seconds_str:
        try:
            delay = float(auto_seconds_str)
            if delay >= 0:
                async def _auto_sim():
                    if delay > 0:
                        await asyncio.sleep(delay)
                    confirm_son_safe(call_id, source="auto_simulation")

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_auto_sim())
                except RuntimeError:
                    # If outside running event loop, spawn thread
                    import threading
                    t = threading.Thread(target=lambda: (asyncio.run(_auto_sim())), daemon=True)
                    t.start()
        except ValueError:
            pass

    return state


def confirm_son_safe(call_id: str, source: str = "webhook") -> Dict[str, Any]:
    """
    Confirm Amit is safe in Pune.
    Marks status as CONFIRMED_SAFE, persists to DB, and broadcasts verified SSE event.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    with _LOOP_LOCK:
        state = _FAMILY_VERIFICATION_STATE.get(call_id, {})
        state["status"] = "CONFIRMED_SAFE"
        state["verified_at"] = now_iso
        state["source"] = source
        _FAMILY_VERIFICATION_STATE[call_id] = state

    # Update SQLite
    try:
        from app.voice.store import update_call_family_verification
        update_call_family_verification(call_id, "CONFIRMED_SAFE", now_iso)
    except Exception as exc:
        logger.warning("Could not persist family verification status to DB: %s", exc)

    logger.info("Family verification CONFIRMED SAFE for call_id=%s via %s", call_id, source)

    # Broadcast immediate green SSE event to dashboard
    broadcast_sse({
        "event": "family_verified_safe",
        "call_id": call_id,
        "message": "✅ AMIT CONFIRMED SAFE IN PUNE — KIDNAP CLAIM IS 100% FAKE",
        "verified_at": now_iso,
    })

    return state


def get_family_intel_injection(call_id: str) -> Optional[str]:
    """
    Return system intel injection message for the active call if son has confirmed safe.
    """
    with _LOOP_LOCK:
        state = _FAMILY_VERIFICATION_STATE.get(call_id)
        if not state:
            from app.voice.store import get_call_record
            rec = get_call_record(call_id)
            if rec and rec.get("family_verification_status") == "CONFIRMED_SAFE":
                return (
                    "[SYSTEM INTEL: Your son Amit just confirmed via Rakshak Family Verification "
                    "that he is 100% SAFE in his Pune office. Keep baiting the scammer for their "
                    "UPI/Bank details so we can report them, or call out their lie after getting their payment details!]"
                )
            return None

        if state.get("status") == "CONFIRMED_SAFE":
            state["context_injected"] = True
            return (
                "[SYSTEM INTEL: Your son Amit just confirmed via Rakshak Family Verification "
                "that he is 100% SAFE in his Pune office. Keep baiting the scammer for their "
                "UPI/Bank details so we can report them, or call out their lie after getting their payment details!]"
            )
    return None
