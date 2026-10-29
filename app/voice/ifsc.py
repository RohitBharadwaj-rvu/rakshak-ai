"""
app/voice/ifsc.py - Real-Time Indian Financial System Code (IFSC) Resolver.

Queries the public Razorpay IFSC API (GET https://ifsc.razorpay.com/{ifsc_code})
with hardcoded offline fallbacks for high-profile cybercrime hubs (Jamtara, Mewat, Koderma)
and major metros (Mumbai, Lucknow) to guarantee 100% demo uptime and sub-millisecond offline tests.
"""

import logging
import re
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)

# Valid Indian IFSC format: 4 letters + 0 + 6 alphanumeric characters
IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$", re.IGNORECASE)

# Offline demo and fallback cache for critical demonstration corridors
OFFLINE_IFSC_DIRECTORY: Dict[str, Dict[str, str]] = {
    "SBIN0004821": {
        "BANK": "State Bank of India",
        "BRANCH": "Koderma",
        "CITY": "Koderma",
        "STATE": "Jharkhand",
        "CENTRE": "Koderma",
        "DISTRICT": "Koderma",
    },
    "ICIC0000104": {
        "BANK": "ICICI Bank",
        "BRANCH": "Jamtara",
        "CITY": "Jamtara",
        "STATE": "Jharkhand",
        "CENTRE": "Jamtara",
        "DISTRICT": "Jamtara",
    },
    "PUNB0112200": {
        "BANK": "Punjab National Bank",
        "BRANCH": "Nuh",
        "CITY": "Nuh",
        "STATE": "Haryana",
        "CENTRE": "Mewat",
        "DISTRICT": "Mewat",
    },
    "HDFC0000001": {
        "BANK": "HDFC Bank",
        "BRANCH": "Nariman Point",
        "CITY": "Mumbai",
        "STATE": "Maharashtra",
        "CENTRE": "Mumbai",
        "DISTRICT": "Greater Mumbai",
    },
    "SBIN0001234": {
        "BANK": "State Bank of India",
        "BRANCH": "Lucknow Main",
        "CITY": "Lucknow",
        "STATE": "Uttar Pradesh",
        "CENTRE": "Lucknow",
        "DISTRICT": "Lucknow",
    },
    "BARB0ALIGAN": {
        "BANK": "Bank of Baroda",
        "BRANCH": "Aliganj",
        "CITY": "Lucknow",
        "STATE": "Uttar Pradesh",
        "CENTRE": "Lucknow",
        "DISTRICT": "Lucknow",
    },
}


def is_valid_ifsc(code: Optional[str]) -> bool:
    """Check if string matches standard Indian IFSC format."""
    if not code:
        return False
    clean = code.strip().upper()
    return bool(IFSC_REGEX.match(clean))


async def resolve_ifsc(ifsc_code: str) -> Dict[str, Any]:
    """
    Resolve an IFSC code to Bank, Branch, City, and State.
    Checks offline dictionary first, then falls back to https://ifsc.razorpay.com.
    Guarantees non-raising execution with a fallback dictionary.
    """
    clean_code = (ifsc_code or "").strip().upper()
    if not clean_code:
        return {
            "valid": False,
            "ifsc": clean_code,
            "bank": "Unknown Bank",
            "branch": "Unknown Branch",
            "city": "Unknown City",
            "state": "Unknown State",
            "source": "empty",
        }

    # 1. Check offline dictionary cache (0ms latency, 100% demo reliability)
    if clean_code in OFFLINE_IFSC_DIRECTORY:
        cached = OFFLINE_IFSC_DIRECTORY[clean_code]
        return {
            "valid": True,
            "ifsc": clean_code,
            "bank": cached.get("BANK", "Unknown Bank"),
            "branch": cached.get("BRANCH", "Unknown Branch"),
            "city": cached.get("CITY", "Unknown City"),
            "state": cached.get("STATE", "Unknown State"),
            "source": "offline_cache",
        }

    # 2. Query Razorpay IFSC public API with strict 1.8s timeout
    try:
        async with httpx.AsyncClient(timeout=1.8) as client:
            resp = await client.get(f"https://ifsc.razorpay.com/{clean_code}")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "valid": True,
                    "ifsc": clean_code,
                    "bank": data.get("BANK", "Unknown Bank"),
                    "branch": data.get("BRANCH", "Unknown Branch"),
                    "city": data.get("CITY", "Unknown City"),
                    "state": data.get("STATE", "Unknown State"),
                    "source": "razorpay_api",
                }
            logger.warning("Razorpay IFSC lookup HTTP %d for %s", resp.status_code, clean_code)
    except Exception as exc:
        logger.warning("Razorpay IFSC lookup failed for %s: %s", clean_code, exc)

    # 3. Fallback heuristic from 4-letter prefix
    bank_name = "Scheduled Commercial Bank"
    prefix = clean_code[:4]
    from app.voice.syndicate import BANK_IFSC_DIRECTORY
    if prefix in BANK_IFSC_DIRECTORY:
        bank_name = BANK_IFSC_DIRECTORY[prefix]

    return {
        "valid": bool(IFSC_REGEX.match(clean_code)),
        "ifsc": clean_code,
        "bank": bank_name,
        "branch": "Branch Office",
        "city": "National Clearing Hub",
        "state": "India",
        "source": "heuristic_fallback",
    }


def generate_ifsc_spoken_hint(ifsc_details: Dict[str, Any], claimed_identity: Optional[str] = None) -> str:
    """Generate natural Devanagari spoken hint for Ramesh to confront scammer."""
    bank = ifsc_details.get("bank", "बैंक")
    branch = ifsc_details.get("branch", "")
    city = ifsc_details.get("city", "")
    state = ifsc_details.get("state", "")

    loc_str = f"{city}, {state}".strip(", ")
    branch_str = f"{bank}, {branch} ब्रांच".strip(", ")

    if claimed_identity:
        return f"भैया, आप तो {claimed_identity} बोल रहे हैं, पर ये IFSC कोड तो {loc_str} ({branch_str}) का दिखा रहा है! ये चक्कर क्या है?"
    return f"भैया, ये IFSC कोड तो {loc_str} ({branch_str}) का दिखा रहा है! ये खाता किसका है?"
