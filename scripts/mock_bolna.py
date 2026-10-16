#!/usr/bin/env python3
"""
mock_bolna.py - Replay test fixtures into the GuardianLine webhook.

Enables Lane B (Backend) and Lane C (Family/Phone) to develop and test
without needing live Bolna telephone credits or active carrier numbers.
"""

import argparse
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, Any, List


def load_fixture(filepath: str) -> Dict[str, Any]:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def send_webhook(
    url: str,
    payload: Dict[str, Any],
    token: str = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Send payload to webhook URL using urllib (no external dependencies needed)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("X-Bolna-Secret", token)

    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            latency = time.time() - start_time
            body = response.read().decode("utf-8")
            status = response.status
            return {
                "success": True,
                "status_code": status,
                "latency_s": round(latency, 3),
                "response": body,
            }
    except urllib.error.HTTPError as e:
        latency = time.time() - start_time
        body = e.read().decode("utf-8")
        return {
            "success": False,
            "status_code": e.code,
            "latency_s": round(latency, 3),
            "error": str(e),
            "response": body,
        }
    except Exception as e:
        latency = time.time() - start_time
        return {
            "success": False,
            "status_code": 0,
            "latency_s": round(latency, 3),
            "error": str(e),
            "response": None,
        }


def replay_fixtures(
    url: str,
    fixtures: List[str],
    token: str = None,
    delay: float = 0.5,
) -> bool:
    all_passed = True
    print(f"\n[MockBolna] Starting replay to: {url}")
    print(f"[MockBolna] Loaded {len(fixtures)} fixture(s)\n")

    for idx, fpath in enumerate(fixtures, 1):
        filename = os.path.basename(fpath)
        payload = load_fixture(fpath)
        call_id = payload.get("call_id", "unknown")
        caller = payload.get("caller_number", "<withheld>")
        duration = payload.get("call_duration", 0)

        print(f"[{idx}/{len(fixtures)}] Sending {filename} (call_id: {call_id}, caller: {caller}, dur: {duration}s)...")
        res = send_webhook(url, payload, token=token)

        if res["success"]:
            print(f"       [PASS] Status: {res['status_code']} in {res['latency_s']}s")
            if res["response"]:
                print(f"          Response: {res['response'][:120]}")
        else:
            print(f"       [FAIL] Status: {res.get('status_code', 'ERR')} - {res.get('error')}")
            if res.get("response"):
                print(f"          Detail: {res['response'][:120]}")
            all_passed = False

        if idx < len(fixtures) and delay > 0:
            time.sleep(delay)

    print(f"\n[MockBolna] Replay complete. Success: {all_passed}\n")
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Replay Bolna webhook fixtures to GuardianLine backend")
    parser.add_argument(
        "--url",
        default="http://localhost:8000/webhook",
        help="Target webhook URL (default: http://localhost:8000/webhook)",
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help="Path to specific fixture JSON. If omitted, all fixtures in tests/fixtures/ are sent.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("BOLNA_WEBHOOK_SECRET", None),
        help="Bearer or shared secret token",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between calls (default: 0.5s)",
    )
    args = parser.parse_args()

    if args.fixture:
        fixtures = [args.fixture]
    else:
        fixtures_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")
        fixtures = sorted(glob.glob(os.path.join(fixtures_dir, "*.json")))

    if not fixtures:
        print("[MockBolna] Error: No fixtures found!", file=sys.stderr)
        sys.exit(1)

    success = replay_fixtures(args.url, fixtures, token=args.token, delay=args.delay)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
