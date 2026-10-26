#!/usr/bin/env python3
"""
scripts/seed_honeypot.py - Mock Telegram Honeypot Number Seeder (Rakshak v2).

Posts the inbound Bolna/Plivo DID honeypot number with realistic elderly-support lures
into test Telegram groups (mock mode by default) so scammer dialers pick up the DID.
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_TEST_GROUPS = [
    "@sbi_kyc_helpdesk_test_mock",
    "@electricity_bill_support_mock",
    "@fedex_customs_clearance_mock",
    "@pension_life_certificate_mock",
]

LURE_TEMPLATES = [
    "Hello sir, my father Ramesh Sharma (72, retired) got an SMS that his SBI YONO KYC is blocked. Please call his number {did} to help update.",
    "Need urgent help with PNB pension account OTP issue, senior citizen alone at home. Contact number: {did}",
    "Received parcel customs hold notice from Mumbai airport, please call my grandfather on {did} and explain in Hindi.",
    "Canara Bank netbanking locked for retired professor, please call {did} to assist with IFSC / UPI verification.",
]


def seed_honeypot_to_telegram(
    inbound_did: str = "+918045681190",
    groups: Optional[List[str]] = None,
    mock: bool = True,
) -> Dict[str, Any]:
    """
    Post the inbound honeypot DID number to test Telegram groups in mock mode.
    Returns a structured receipt of all seeded posts.
    """
    target_groups = groups or list(DEFAULT_TEST_GROUPS)
    posts: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, group in enumerate(target_groups):
        template = LURE_TEMPLATES[idx % len(LURE_TEMPLATES)]
        text = template.format(did=inbound_did)
        msg_hash = hashlib.sha256(f"{group}:{inbound_did}:{idx}".encode("utf-8")).hexdigest()[:12]
        posts.append(
            {
                "group": group,
                "inbound_did": inbound_did,
                "message_text": text,
                "mock_delivery": mock,
                "status": "MOCK_POSTED" if mock else "QUEUED",
                "telegram_message_id": f"tg_mock_{msg_hash}",
                "timestamp": now_iso,
            }
        )

    return {
        "inbound_did": inbound_did,
        "mock_mode": mock,
        "groups_seeded": len(posts),
        "posts": posts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed inbound honeypot DID to test Telegram groups (mock)")
    parser.add_argument(
        "--did",
        default=os.getenv("BOLNA_INBOUND_DID", "+918045681190"),
        help="Inbound Bolna/Plivo honeypot DID number",
    )
    parser.add_argument(
        "--groups",
        nargs="*",
        default=None,
        help="Optional list of test Telegram group handles",
    )
    args = parser.parse_args()

    receipt = seed_honeypot_to_telegram(inbound_did=args.did, groups=args.groups, mock=True)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
