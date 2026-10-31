"""
app/api/upgrades_router.py - Endpoints for Hackathon Top-3 Upgrades:
1. Son-in-Trouble family verification webhooks & 1-click safe confirmations.
2. Cross-call syndicate graph endpoint.
3. Real-time Server-Sent Events (SSE) stream for live dashboard alerts.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.voice.family_loop import (
    confirm_son_safe,
    register_sse_queue,
    unregister_sse_queue,
    _FAMILY_VERIFICATION_STATE,
)
from app.voice.store import get_syndicate_graph, list_call_records

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Rakshak Upgrades"])


@router.post("/webhooks/family_verify")
async def webhook_family_verify(request: Request):
    """
    Inbound webhook for family verification (e.g. from Twilio WhatsApp, SMS, or direct JSON).
    Accepts Twilio form data (Body, From) or JSON payload ({"call_id": "...", "status": "SAFE"}).
    """
    call_id: Optional[str] = None
    status: str = "SAFE"
    body_text = ""
    from_number = ""

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = await request.json()
            call_id = data.get("call_id")
            status = data.get("status", "SAFE")
            from_number = data.get("from_number", "")
            body_text = data.get("body", "") or status
        except Exception:
            pass
    else:
        # Form-encoded (Twilio Webhook)
        try:
            form = await request.form()
            body_text = form.get("Body", "").strip()
            from_number = form.get("From", "").strip()
            call_id = form.get("call_id")
        except Exception:
            pass

    # Find target call_id if not explicitly provided
    if not call_id:
        # Look for most recent pending call in memory
        for cid, st in list(_FAMILY_VERIFICATION_STATE.items()):
            if st.get("status") == "PENDING":
                call_id = cid
                break
        
        # Fallback to recent calls in SQLite
        if not call_id:
            recent_calls = list_call_records(limit=10)
            for rec in recent_calls:
                if rec.get("family_verification_status") == "PENDING":
                    call_id = rec["call_id"]
                    break

    if not call_id:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "No active pending family verification call found"},
        )

    res = confirm_son_safe(call_id, source=f"webhook:{from_number or 'inbound'}")
    return {
        "status": "ok",
        "call_id": call_id,
        "family_verification_status": "CONFIRMED_SAFE",
        "verified_at": res.get("verified_at"),
    }


@router.post("/api/calls/{call_id}/verify_son_safe")
async def api_verify_son_safe(call_id: str):
    """1-Click stage demo / dashboard trigger to confirm Amit is safe in Pune."""
    res = confirm_son_safe(call_id, source="manual_dashboard_1click")
    return {
        "status": "ok",
        "call_id": call_id,
        "family_verification_status": "CONFIRMED_SAFE",
        "verified_at": res.get("verified_at"),
    }


@router.get("/api/syndicate/graph")
async def api_get_syndicate_graph():
    """Return cross-call syndicate cluster graph and repeat mule identifier tracking."""
    return get_syndicate_graph()


@router.get("/api/mobile/calls")
async def api_mobile_calls(limit: int = 50):
    """Read-only mobile Caretaker feed returning recent screened call records."""
    capped = max(1, min(100, limit))
    return list_call_records(limit=capped)


@router.get("/dashboard/sse")
@router.get("/api/events")
async def sse_event_stream(request: Request):
    """Server-Sent Events (SSE) stream for real-time dashboard updates."""
    q: asyncio.Queue = asyncio.Queue()
    register_sse_queue(q)

    async def event_generator():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            unregister_sse_queue(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
