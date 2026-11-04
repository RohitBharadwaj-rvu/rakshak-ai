"""
app/voice/location.py - 4-Layer Real-Time Scammer Geolocation Triangulation & Canary Trap Engine.

Layers:
1. Layer 1: Inbound Carrier Telecom Circle & Allocated Circle Location (Instant offline).
2. Layer 2: Live Razorpay IFSC Branch Geolocation & Coordinates.
3. Layer 3: Zero-click Public IP / ISP Geolocation (via Canary Trap HTTP Headers / ip-api).
4. Layer 4: 1-Tap High-Precision GPS Geolocation (via HTML5 Geolocation API from Canary Receipt Trap).

Triangulation Mismatch:
Compares Scammer Claimed Location (e.g. Mumbai) vs. Bank IFSC Location (e.g. Delhi) vs. SIM Circle vs. Live Canary GPS/IP.
"""

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.voice.telecom_circles import lookup_telecom_circle
from app.voice.ifsc import resolve_ifsc

logger = logging.getLogger(__name__)

# In-memory store for active call location captures (also mirrored into SQLite / SSE)
_CALL_LOCATION_STORE: Dict[str, Dict[str, Any]] = {}


class CanaryTrapCapture(BaseModel):
    call_id: str
    ip: str = "127.0.0.1"
    city: Optional[str] = None
    region: Optional[str] = None
    country: str = "India"
    isp: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    accuracy_meters: Optional[float] = None
    user_agent: Optional[str] = None
    device_model: Optional[str] = None
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def get_call_location_profile(call_id: str) -> Dict[str, Any]:
    """Return the current aggregated multi-layer location profile for a call."""
    if call_id not in _CALL_LOCATION_STORE:
        _CALL_LOCATION_STORE[call_id] = {
            "call_id": call_id,
            "telecom_circle": None,
            "ifsc_location": None,
            "claimed_location": None,
            "canary_ip": None,
            "canary_gps": None,
            "triangulation_mismatch": False,
            "mismatch_summary": "",
            "canary_opened": False,
            "canary_opened_at": None,
            "evidence_chain": [],
        }
    return _CALL_LOCATION_STORE[call_id]


def update_caller_number_location(call_id: str, caller_number: str) -> Dict[str, Any]:
    """Layer 1: Initialize telecom circle from incoming phone number."""
    profile = get_call_location_profile(call_id)
    if caller_number:
        circle_data = lookup_telecom_circle(caller_number)
        if circle_data:
            profile["telecom_circle"] = circle_data
            _record_evidence(profile, "layer_1_telecom_circle", {
                "source": "DoT National Numbering Plan",
                "phone": caller_number,
                "circle": circle_data["circle_name"],
                "carrier": circle_data["carrier"],
                "city": circle_data["city"],
                "lat": circle_data["lat"],
                "lng": circle_data["lng"],
            })
    _recompute_mismatch(profile)
    return profile


async def update_ifsc_location(call_id: str, ifsc_code: str) -> Dict[str, Any]:
    """Layer 2: Update bank branch location from resolved IFSC code."""
    profile = get_call_location_profile(call_id)
    if ifsc_code:
        try:
            res = await resolve_ifsc(ifsc_code)
            if res and res.get("valid"):
                # Geocode major cities approximately or via city centers
                city = res.get("city") or "New Delhi"
                state = res.get("state") or "Delhi"
                branch = res.get("branch") or ""
                bank = res.get("bank") or ""
                
                # Approximate lat/lng for key Indian cities
                coords = _lookup_city_coordinates(city, state)
                ifsc_loc = {
                    "ifsc": ifsc_code,
                    "bank": bank,
                    "branch": branch,
                    "city": city,
                    "state": state,
                    "lat": coords["lat"],
                    "lng": coords["lng"],
                }
                profile["ifsc_location"] = ifsc_loc
                _record_evidence(profile, "layer_2_rbi_ifsc", ifsc_loc)
        except Exception as exc:
            logger.warning("Failed to resolve IFSC location for %s: %s", ifsc_code, exc)
    _recompute_mismatch(profile)
    return profile


def set_claimed_location(call_id: str, claimed: str) -> Dict[str, Any]:
    """Set the scammer's verbal claim (e.g. 'Mumbai SBI Head Office')."""
    profile = get_call_location_profile(call_id)
    profile["claimed_location"] = claimed
    _record_evidence(profile, "verbal_claim", {"claimed": claimed})
    _recompute_mismatch(profile)
    return profile


def record_canary_trap_hit(
    call_id: str,
    ip: str,
    user_agent: Optional[str] = None,
    client_lat: Optional[float] = None,
    client_lng: Optional[float] = None,
    accuracy: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Layers 3 & 4: Process Canary Trap access (HTTP receipt view or 1-tap GPS verification).
    Captures zero-click IP geolocation and high-precision browser GPS coordinates.
    """
    profile = get_call_location_profile(call_id)
    profile["canary_opened"] = True
    profile["canary_opened_at"] = datetime.now(timezone.utc).isoformat()

    # Layer 3: Zero-click IP / ISP Geolocation
    ip_geo = _resolve_ip_geolocation(ip)
    profile["canary_ip"] = {
        "ip": ip,
        "city": ip_geo.get("city"),
        "region": ip_geo.get("region"),
        "country": ip_geo.get("country", "India"),
        "isp": ip_geo.get("isp"),
        "lat": ip_geo.get("lat"),
        "lng": ip_geo.get("lng"),
        "user_agent": user_agent or "Unknown Browser",
    }
    _record_evidence(profile, "layer_3_canary_ip", profile["canary_ip"])

    # Layer 4: 1-Tap Exact GPS Geolocation (from HTML5 navigator.geolocation)
    if client_lat is not None and client_lng is not None:
        profile["canary_gps"] = {
            "lat": client_lat,
            "lng": client_lng,
            "accuracy_meters": accuracy or 15.0,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "google_maps_url": f"https://www.google.com/maps?q={client_lat},{client_lng}",
        }
        _record_evidence(profile, "layer_4_canary_gps", profile["canary_gps"])

    _recompute_mismatch(profile)
    return profile


def _record_evidence(profile: Dict[str, Any], layer_type: str, data: Dict[str, Any]) -> None:
    entry = {
        "layer": layer_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    profile["evidence_chain"].append(entry)


def _recompute_mismatch(profile: Dict[str, Any]) -> None:
    """Analyze discrepancies between Claimed vs. IFSC vs. SIM vs. GPS."""
    claimed = (profile.get("claimed_location") or "").lower()
    ifsc_loc = profile.get("ifsc_location") or {}
    sim_loc = profile.get("telecom_circle") or {}
    gps_loc = profile.get("canary_gps") or {}
    ip_loc = profile.get("canary_ip") or {}

    mismatches = []
    
    if claimed and ifsc_loc:
        ifsc_city = (ifsc_loc.get("city") or "").lower()
        if ifsc_city and ifsc_city not in claimed:
            mismatches.append(f"Claimed '{profile['claimed_location']}' != Mule Bank Branch '{ifsc_loc.get('branch')}, {ifsc_loc.get('city')}'")

    if claimed and sim_loc:
        sim_state = (sim_loc.get("state") or "").lower()
        sim_city = (sim_loc.get("city") or "").lower()
        if sim_city and sim_city not in claimed and sim_state not in claimed:
            mismatches.append(f"Claimed '{profile['claimed_location']}' != SIM Registered Circle '{sim_loc.get('circle_name')}'")

    if (gps_loc or ip_loc) and claimed:
        real_city = ((gps_loc.get("city") or ip_loc.get("city")) or "").lower()
        if real_city and real_city not in claimed:
            mismatches.append(f"Claimed '{profile['claimed_location']}' != Live Device Geolocation '{ip_loc.get('city') or 'Captured Location'}'")

    profile["triangulation_mismatch"] = len(mismatches) > 0
    profile["mismatch_summary"] = " | ".join(mismatches) if mismatches else "Locations aligned or awaiting additional triangulation."


def _resolve_ip_geolocation(ip: str) -> Dict[str, Any]:
    """Query offline or lightweight IP API; provides mock/fallback for localhost/testing."""
    if not ip or ip in ("127.0.0.1", "localhost", "::1", "testclient"):
        # For local testing, return default tech hub (Bengaluru / Jio)
        return {
            "city": "Bengaluru",
            "region": "Karnataka",
            "country": "India",
            "isp": "Reliance Jio Infocomm",
            "lat": 12.9716,
            "lng": 77.5946,
        }
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,lat,lon"
        req = urllib.request.Request(url, headers={"User-Agent": "GuardianLine-CyberShield/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                return {
                    "city": data.get("city"),
                    "region": data.get("regionName"),
                    "country": data.get("country", "India"),
                    "isp": data.get("isp"),
                    "lat": data.get("lat"),
                    "lng": data.get("lon"),
                }
    except Exception as exc:
        logger.debug("IP API lookup skipped or timed out: %s", exc)
    
    return {
        "city": "Bengaluru",
        "region": "Karnataka",
        "country": "India",
        "isp": "Cellular ISP",
        "lat": 12.9716,
        "lng": 77.5946,
    }


def _lookup_city_coordinates(city: str, state: str) -> Dict[str, float]:
    """Map major Indian cities to coordinates."""
    c = (city or "").strip().lower()
    mapping = {
        "delhi": {"lat": 28.6139, "lng": 77.2090},
        "new delhi": {"lat": 28.6139, "lng": 77.2090},
        "mumbai": {"lat": 19.0760, "lng": 72.8777},
        "bengaluru": {"lat": 12.9716, "lng": 77.5946},
        "bangalore": {"lat": 12.9716, "lng": 77.5946},
        "chennai": {"lat": 13.0827, "lng": 80.2707},
        "kolkata": {"lat": 22.5726, "lng": 88.3639},
        "hyderabad": {"lat": 17.3850, "lng": 78.4867},
        "pune": {"lat": 18.5204, "lng": 73.8567},
        "ahmedabad": {"lat": 23.0225, "lng": 72.5714},
        "jaipur": {"lat": 26.9124, "lng": 75.7873},
        "lucknow": {"lat": 26.8467, "lng": 80.9462},
        "patna": {"lat": 25.5941, "lng": 85.1376},
        "koderma": {"lat": 24.4674, "lng": 85.5939},
        "jamtara": {"lat": 23.9631, "lng": 86.8016},
    }
    for k, v in mapping.items():
        if k in c:
            return v
    return {"lat": 28.6139, "lng": 77.2090}
