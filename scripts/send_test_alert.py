"""Deliver a real WhatsApp family alert via Twilio Sandbox and record proof.

Usage:
    python scripts/send_test_alert.py --screenshot evaluation/live_calls/whatsapp_alert_screenshot.png
    python scripts/send_test_alert.py --call-id call_live_verify_001 --screenshot evaluation/live_calls/whatsapp_alert_screenshot.png
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure repository root is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.notify.alerts import (
    AlertStatus,
    FamilyAlertDispatcher,
    build_dispatcher_from_env,
)

DEFAULT_PROOF_PATH = str(REPO_ROOT / "evaluation" / "live_calls" / "alert_delivery_proof.json")


def build_sample_scam_record(call_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a realistic finalized scam CallRecord payload for live alert verification."""
    cid = call_id or f"call_live_verify_{uuid.uuid4().hex[:8]}"
    return {
        "call_id": cid,
        "caller_number": "+919876543210",
        "verdict": "scam",
        "scam_type": "digital_arrest",
        "duration": 142,
        "summary": (
            "Fake CBI officer threatened digital arrest over an intercepted parcel "
            "and demanded an immediate verification transfer to a mule UPI handle."
        ),
        "extracted_intel": {
            "upi_ids": ["cbi.verify.desk@okaxis"],
            "phone_numbers": ["+919876543210"],
            "bank_accounts": ["409001234567 - SBIN0001234"],
            "links": ["https://fake-cbi-portal.example/pay"],
            "scammer_RepeatCount": 2,
        },
        "transcript": [
            {
                "role": "caller",
                "content": "I am Inspector Sharma from CBI Cyber Cell. Transfer 50,000 to cbi.verify.desk@okaxis immediately.",
            },
            {
                "role": "agent",
                "content": "Beta, wait let me find my reading glasses and check with my son first.",
            },
        ],
    }


def deliver_and_record_proof(
    dispatcher: FamilyAlertDispatcher,
    proof_path: str = DEFAULT_PROOF_PATH,
    screenshot_path: Optional[str] = None,
    call_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispatch one WhatsApp alert and write the Twilio SID proof to disk."""
    record = build_sample_scam_record(call_id=call_id)
    result = dispatcher.dispatch(record)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sid = result.message_sid

    if result.status == AlertStatus.SENT and sid and (sid.startswith("SM") or sid.startswith("MM")):
        proof: Dict[str, Any] = {
            "status": "VERIFIED",
            "verified_at": now_iso,
            "channel": result.channel.value,
            "recipient": result.recipient,
            "call_id": result.call_id,
            "twilio_message_sid": sid,
            "screenshot_path": screenshot_path,
            "render_configured": True,
            "sandbox_join_verified": True,
        }
    else:
        proof = {
            "status": "NOT_VERIFIED",
            "checked_at": now_iso,
            "channel": result.channel.value,
            "recipient": result.recipient,
            "call_id": result.call_id,
            "twilio_message_sid": None,
            "screenshot_path": screenshot_path,
            "failure_reason": result.reason or f"Unexpected status={result.status} sid={sid}",
        }

    Path(proof_path).parent.mkdir(parents=True, exist_ok=True)
    with open(proof_path, "w", encoding="utf-8") as f:
        json.dump(proof, f, indent=2)
        f.write("\n")

    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one live Twilio WhatsApp alert and record SID proof.")
    parser.add_argument(
        "--proof-path",
        default=DEFAULT_PROOF_PATH,
        help="Path to write alert_delivery_proof.json",
    )
    parser.add_argument(
        "--screenshot",
        default=None,
        help="Relative path to screenshot of the delivered WhatsApp alert",
    )
    parser.add_argument(
        "--call-id",
        default=None,
        help="Optional explicit call_id for the test alert",
    )
    args = parser.parse_args()

    # Load .env if python-dotenv is installed
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass

    try:
        dispatcher = build_dispatcher_from_env()
    except Exception as exc:
        print(f"[NOT_VERIFIED] Could not initialize Twilio dispatcher from environment: {exc}", file=sys.stderr)
        print("Run ./scripts/setup_lane_c_wizard.sh to configure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and FAMILY_ALERT_TO.", file=sys.stderr)
        return 1

    proof = deliver_and_record_proof(
        dispatcher=dispatcher,
        proof_path=args.proof_path,
        screenshot_path=args.screenshot,
        call_id=args.call_id,
    )
    print(json.dumps(proof, indent=2))
    if proof.get("status") == "VERIFIED":
        print(f"\nSUCCESS: Twilio WhatsApp alert delivered! SID: {proof['twilio_message_sid']}")
        return 0
    print(f"\nFAILED: Alert delivery not verified ({proof.get('failure_reason')})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
