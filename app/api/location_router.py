"""
app/api/location_router.py - FastAPI Router for 4-Layer Location Triangulation & Canary Trap.

Endpoints:
1. GET  /receipt/{call_id}        - Deceptive Canary Trap Landing Page (Fake NPCI / SBI UPI ₹5000 Transfer Receipt)
2. POST /api/canary/telemetry     - Captures 1-tap exact GPS + Client IP & User-Agent
3. GET  /api/calls/{call_id}/location - Returns current 4-layer location profile & triangulation verdict
"""

import html
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.voice.location import (
    get_call_location_profile,
    record_canary_trap_hit,
)
from app.voice.family_loop import broadcast_sse
from app.voice.store import append_mid_call_intel, resolve_effective_tool_call_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Location Triangulation & Canary Trap"])


class CanaryTelemetryPayload(BaseModel):
    call_id: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    accuracy: Optional[float] = None
    user_agent: Optional[str] = None


@router.get("/receipt/{call_id}", response_class=HTMLResponse)
async def canary_receipt_page(call_id: str, request: Request):
    """
    Canary Trap Receipt: Scammer opens this URL expecting to claim/verify ₹5,000 payment.
    Instantly logs zero-click IP/ISP telemetry and requests 1-tap HTML5 GPS verification.
    """
    effective_id = resolve_effective_tool_call_id(call_id)
    client_ip = request.client.host if request.client else "127.0.0.1"
    # Check for reverse proxy forwarded header
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    user_agent = request.headers.get("user-agent", "Unknown Device")

    # Record Layer 3 (Zero-click IP Telemetry)
    profile = record_canary_trap_hit(
        call_id=effective_id,
        ip=client_ip,
        user_agent=user_agent,
    )

    # Broadcast real-time SSE event to Caretaker Dashboard & Android App
    broadcast_sse({
        "event": "canary_trap_opened",
        "call_id": effective_id,
        "ip": client_ip,
        "city": profile.get("canary_ip", {}).get("city") or "India",
        "isp": profile.get("canary_ip", {}).get("isp") or "Cellular ISP",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": "Scammer accessed Canary Payment Receipt. Awaiting GPS verification...",
    })

    safe_call_id = html.escape(effective_id)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SBI e-Payment Verification | ₹5,000.00</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 16px; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 20px; max-width: 440px; width: 100%; padding: 28px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }}
    .logo-row {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 20px; }}
    .bank-name {{ font-size: 1.15rem; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 8px; }}
    .badge {{ background: #0369a1; color: #e0f2fe; padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
    .amount-box {{ text-align: center; margin: 24px 0; background: #0f172a; border-radius: 16px; padding: 20px; border: 1px dashed #0284c7; }}
    .amount-label {{ font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
    .amount-val {{ font-size: 2.25rem; font-weight: 800; color: #38bdf8; margin: 8px 0; }}
    .status-text {{ font-size: 0.9rem; color: #fbbf24; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 6px; }}
    .details-table {{ width: 100%; margin-bottom: 24px; font-size: 0.875rem; }}
    .details-table td {{ padding: 8px 0; border-bottom: 1px solid #293548; }}
    .details-table td:first-child {{ color: #94a3b8; }}
    .details-table td:last-child {{ text-align: right; font-weight: 600; color: #e2e8f0; }}
    .btn {{ display: block; width: 100%; background: #0284c7; hover: #0369a1; color: #ffffff; padding: 14px; border-radius: 12px; font-size: 1rem; font-weight: 700; border: none; cursor: pointer; transition: all 0.2s; text-align: center; }}
    .btn:hover {{ background: #0369a1; }}
    .security-note {{ font-size: 0.75rem; color: #64748b; text-align: center; margin-top: 16px; line-height: 1.4; }}
    .success-box {{ display: none; background: #064e3b; border: 1px solid #059669; color: #a7f3d0; padding: 14px; border-radius: 12px; font-size: 0.9rem; text-align: center; margin-top: 16px; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo-row">
      <div class="bank-name">
        <span>🏛️</span> State Bank of India
      </div>
      <div class="badge">UPI 2.0 Secure</div>
    </div>

    <div class="amount-box">
      <div class="amount-label">Pending Transfer Voucher</div>
      <div class="amount-val">₹5,000.00</div>
      <div class="status-text">⏳ Awaiting Recipient Verification</div>
    </div>

    <table class="details-table">
      <tr>
        <td>Payer Account</td>
        <td>Ramesh Chandra Sharma (***3210)</td>
      </tr>
      <tr>
        <td>Reference ID</td>
        <td>UPI/{safe_call_id[:10].upper()}</td>
      </tr>
      <tr>
        <td>Transfer Type</td>
        <td>Instant IMPS / UPI Fast-Track</td>
      </tr>
      <tr>
        <td>Status</td>
        <td>Action Required: Tap to Release</td>
      </tr>
    </table>

    <button class="btn" id="claimBtn" onclick="requestVerification()">
      ⚡ Verify Location & Claim ₹5,000
    </button>

    <div id="successBox" class="success-box">
      ✅ Transfer Authorized! Bank settlement reference generated.
    </div>

    <div class="security-note">
      🔒 Protected by RBI Cyber Security Guidelines & NPCI UPI Fraud Prevention Switch. Location verification ensures compliance with geo-fenced merchant regulations.
    </div>
  </div>

  <script>
    const CALL_ID = "{safe_call_id}";

    // Auto-capture on page load if browser allows
    window.addEventListener("DOMContentLoaded", () => {{
      triggerSilentGeo();
    }});

    function triggerSilentGeo() {{
      if ("geolocation" in navigator) {{
        navigator.geolocation.getCurrentPosition(
          (pos) => sendTelemetry(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy),
          (err) => console.log("Silent geo wait:", err.message),
          {{ timeout: 6000, enableHighAccuracy: true }}
        );
      }}
    }}

    function requestVerification() {{
      const btn = document.getElementById("claimBtn");
      btn.innerText = "Verifying with Telecom Gateway...";
      btn.disabled = true;

      if ("geolocation" in navigator) {{
        navigator.geolocation.getCurrentPosition(
          (pos) => {{
            sendTelemetry(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy);
            showSuccess();
          }},
          (err) => {{
            // Still send what we have
            sendTelemetry(null, null, null);
            showSuccess();
          }},
          {{ timeout: 10000, enableHighAccuracy: true }}
        );
      }} else {{
        sendTelemetry(null, null, null);
        showSuccess();
      }}
    }}

    function sendTelemetry(lat, lng, accuracy) {{
      fetch("/api/canary/telemetry", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          call_id: CALL_ID,
          lat: lat,
          lng: lng,
          accuracy: accuracy,
          user_agent: navigator.userAgent
        }})
      }}).catch(e => console.error("Telemetry report err:", e));
    }}

    function showSuccess() {{
      document.getElementById("claimBtn").style.display = "none";
      document.getElementById("successBox").style.display = "block";
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@router.post("/api/canary/telemetry")
async def receive_canary_telemetry(payload: CanaryTelemetryPayload, request: Request):
    """
    Receives exact GPS coordinates (Layer 4) + device info from Canary Receipt interaction.
    """
    effective_id = resolve_effective_tool_call_id(payload.call_id)
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    profile = record_canary_trap_hit(
        call_id=effective_id,
        ip=client_ip,
        user_agent=payload.user_agent or request.headers.get("user-agent"),
        client_lat=payload.lat,
        client_lng=payload.lng,
        accuracy=payload.accuracy,
    )

    # Log into call record's mid-call intelligence
    gps_info = profile.get("canary_gps") or {}
    if gps_info:
        lat = gps_info.get("lat")
        lng = gps_info.get("lng")
        append_mid_call_intel(
            call_id=effective_id,
            intel_type="other",
            value_as_heard=f"GPS:{lat},{lng}",
            normalized_value=f"GPS:{lat},{lng}",
            unparseable=False,
            elicitation="canary_trap",
            quote=f"Exact GPS Pinpoint: {lat}, {lng} (±{gps_info.get('accuracy_meters', 10)}m)",
        )

    # Broadcast high-priority SSE event to Caretaker Dashboard
    broadcast_sse({
        "event": "scammer_location_triangulated",
        "call_id": effective_id,
        "lat": payload.lat,
        "lng": payload.lng,
        "accuracy": payload.accuracy,
        "ip": client_ip,
        "triangulation_mismatch": profile.get("triangulation_mismatch", False),
        "mismatch_summary": profile.get("mismatch_summary", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "status": "logged",
        "call_id": effective_id,
        "triangulation_mismatch": profile.get("triangulation_mismatch", False),
        "mismatch_summary": profile.get("mismatch_summary", ""),
    }


@router.get("/api/calls/{call_id}/location")
async def get_call_location(call_id: str):
    """Return the complete 4-layer location profile and triangulation status."""
    effective_id = resolve_effective_tool_call_id(call_id)
    return get_call_location_profile(effective_id)
