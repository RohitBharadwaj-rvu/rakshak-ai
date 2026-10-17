"""
app/core/enrichment.py - Post-Call Intelligence Enrichment Module (T-POST).

Enriches extracted scammer entities after the CallRecord is saved:
  - Maps UPI handles (@okaxis, @paytm, @ybl, @okhdfcbank, @okicici, @oksbi, etc.) to PSP & sponsor bank
  - Maps IFSC 4-letter bank codes (HDFC, SBIN, ICIC, AXIS, PUNB, BARB, etc.) to bank names
  - Annotates phone numbers (10-digit Indian mobile series) and suspicious links (domain extraction)
  - Never blocks the live call or webhook response
"""

import logging
from typing import Any, Dict, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

UPI_HANDLE_BANKS: Dict[str, Dict[str, str]] = {
    "okaxis": {"psp": "Google Pay", "bank": "Axis Bank"},
    "okhdfcbank": {"psp": "Google Pay", "bank": "HDFC Bank"},
    "okicici": {"psp": "Google Pay", "bank": "ICICI Bank"},
    "oksbi": {"psp": "Google Pay", "bank": "State Bank of India"},
    "paytm": {"psp": "Paytm", "bank": "Paytm Payments Bank / Axis / HDFC / SBI / Yes Bank"},
    "ybl": {"psp": "PhonePe", "bank": "Yes Bank"},
    "ibl": {"psp": "PhonePe", "bank": "ICICI Bank"},
    "axl": {"psp": "PhonePe", "bank": "Axis Bank"},
    "apl": {"psp": "Amazon Pay", "bank": "Axis Bank"},
    "upi": {"psp": "BHIM", "bank": "NPCI"},
    "sbi": {"psp": "YONO SBI", "bank": "State Bank of India"},
    "hdfcbank": {"psp": "HDFC PayZapp", "bank": "HDFC Bank"},
    "icici": {"psp": "iMobile Pay", "bank": "ICICI Bank"},
    "axisbank": {"psp": "Axis Mobile", "bank": "Axis Bank"},
    "kotak": {"psp": "Kotak 811", "bank": "Kotak Mahindra Bank"},
}

IFSC_BANK_PREFIXES: Dict[str, str] = {
    "SBIN": "State Bank of India",
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "UTIB": "Axis Bank",
    "AXIS": "Axis Bank",
    "PUNB": "Punjab National Bank",
    "BARB": "Bank of Baroda",
    "CNRB": "Canara Bank",
    "UBIN": "Union Bank of India",
    "KKBK": "Kotak Mahindra Bank",
    "IDIB": "Indian Bank",
    "BKID": "Bank of India",
    "YESB": "Yes Bank",
    "PYTM": "Paytm Payments Bank",
}


def enrich_extracted_intel(extracted_intel: Dict[str, Any], call_id: str = "unknown") -> Dict[str, Any]:
    """
    Produce structured enrichment metadata for a CallRecord's `extracted_intel`.
    Runs strictly post-call (T-POST).
    """
    intel = extracted_intel or {}

    upi_details: List[Dict[str, str]] = []
    for upi in intel.get("upi_ids") or []:
        handle = upi.split("@", 1)[1].lower() if "@" in upi else ""
        meta = UPI_HANDLE_BANKS.get(handle, {"psp": "Unknown PSP", "bank": "Unknown Bank"})
        upi_details.append(
            {
                "upi_id": upi,
                "handle": handle,
                "psp": meta["psp"],
                "bank": meta["bank"],
            }
        )

    ifsc_details: List[Dict[str, str]] = []
    for code in intel.get("ifsc_codes") or []:
        prefix = code[:4].upper() if len(code) >= 4 else ""
        bank_name = IFSC_BANK_PREFIXES.get(prefix, "Unknown Bank")
        ifsc_details.append(
            {
                "ifsc": code,
                "bank_prefix": prefix,
                "bank_name": bank_name,
                "branch_code": code[5:] if len(code) == 11 else "",
            }
        )

    phone_details: List[Dict[str, str]] = []
    for ph in intel.get("phone_numbers") or []:
        phone_details.append(
            {
                "phone": ph,
                "country_code": "+91",
                "series": f"{ph[0]}xxx-mobile" if ph else "unknown",
            }
        )

    link_details: List[Dict[str, str]] = []
    for lnk in intel.get("links") or []:
        normalized_url = lnk if "://" in lnk else f"http://{lnk}"
        parsed = urlparse(normalized_url)
        link_details.append(
            {
                "url": lnk,
                "domain": parsed.netloc or lnk.split("/")[0],
                "scheme": parsed.scheme or "http",
            }
        )

    enrichment = {
        "call_id": call_id,
        "upi_enrichment": upi_details,
        "ifsc_enrichment": ifsc_details,
        "phone_enrichment": phone_details,
        "link_enrichment": link_details,
    }
    logger.info(
        "Post-call enrichment completed call_id=%s upis=%d ifscs=%d phones=%d links=%d",
        call_id,
        len(upi_details),
        len(ifsc_details),
        len(phone_details),
        len(link_details),
    )
    return enrichment


def run_post_call_enrichment(record: Dict[str, Any]) -> Dict[str, Any]:
    """Run enrichment on a full CallRecord dict."""
    call_id = str(record.get("call_id") or "unknown")
    intel = record.get("extracted_intel") or {}
    return enrich_extracted_intel(intel, call_id=call_id)
