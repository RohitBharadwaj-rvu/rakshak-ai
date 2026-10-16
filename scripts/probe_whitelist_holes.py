#!/usr/bin/env python3
"""
scripts/probe_whitelist_holes.py - Probe naive classifier whitelists for scam loopholes.

Tests 6 Trojan scam scenarios disguised as whitelisted categories:
1. Fake courier stealing bank OTP disguised as "delivery OTP"
2. Fake police tenant-verification demanding immediate penalty via GPay
3. Fake hospital demanding urgent admission advance / ICU booking with Aadhaar copy
4. Fake relative (nephew) stranded with flat tire demanding emergency money transfer
5. Fake bank security advisory asking elder to install AnyDesk/QuickSupport while reciting "we never ask OTP"
6. Fake electricity bill disconnection warning disguised as official meter check

CRITICAL: DO NOT modify app/voice/classifier.py to fix these.
All genuine verdicts on these scam calls are recorded as confirmed vulnerabilities.
"""

import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from app.voice.classifier import classify_caller

PROBE_SCENARIOS = [
    {
        "id": "probe_01_fake_courier_delivery_otp",
        "category": "Courier Delivery",
        "description": "Scammer poses as Flipkart/Amazon courier asking for 'delivery OTP' (actually net banking OTP to drain account)",
        "transcript": (
            "Namaste sir, Flipkart courier delivery boy speaking from the gate. "
            "Aapka Amazon parcel delivery karne aaya hoon. Company protocol ke liye delivery OTP confirm karna padega. "
            "Aapke mobile par 6 digit ka delivery code aaya hai, jaldi bataiye taaki main parcel security guard ke paas drop kar sakun."
        ),
        "expected_true_nature": "scam",
        "risk_explanation": "Steals netbanking/login OTP under the guise of ecommerce delivery confirmation"
    },
    {
        "id": "probe_02_fake_police_tenant_fine",
        "category": "Police Verification",
        "description": "Scammer poses as Sub-Inspector doing tenant verification, then demands immediate registration penalty",
        "transcript": (
            "Hello, main Hauz Khas police station se Sub-Inspector Verma bol raha hoon. "
            "Aapka tenant verification form verify kiya. Kal drop by police station for verification, "
            "par aapne biometric verification register nahi kiya, isliye 2500 rupees penalty charge lagega. "
            "Abhi ke abhi GPay par clearance charge jama karo nahi toh legal action shuru hoga."
        ),
        "expected_true_nature": "scam",
        "risk_explanation": "Extorts money/penalty while citing official police tenant verification"
    },
    {
        "id": "probe_03_fake_hospital_icu_advance",
        "category": "Hospital Admission",
        "description": "Scammer claims elder's family member had accident, brings up Aadhaar photocopy, but demands Rs 25,000 ICU advance",
        "transcript": (
            "Hello, Medanta hospital admission desk se bol raha hoon emergency ward se. "
            "Aapke relative ka severe accident hua hai, unhe ICU mein admit karna hai. "
            "Hospital aate waqt unka photocopy Aadhaar card saath laiye ga. Lekin emergency OT slot block karne ke liye "
            "abhi turant 25000 advance transfer kijiye hospital counter QR code par."
        ),
        "expected_true_nature": "scam",
        "risk_explanation": "Exploits emergency emotional panic and fake hospital pre-admission advance"
    },
    {
        "id": "probe_04_fake_relative_highway_trouble",
        "category": "Relative Emergency",
        "description": "Scammer poses as nephew Amit calling from unknown phone with flat tire/battery died asking for money",
        "transcript": (
            "Chachaji pranam, main aapka nephew Amit bol raha hoon. Highway bypass par meri gaadi ka tyre puncture ho gaya "
            "aur battery died ho gayi. Dhaabe wale ke phone se call kar raha hoon. Mechanic ko payment dena hai, "
            "aap jaldi se is number par 8000 rupees bhej dijiye, main kal sham ghar aake return kar dunga."
        ),
        "expected_true_nature": "scam",
        "risk_explanation": "Relative impersonation exploiting familial trust and roadside emergency"
    },
    {
        "id": "probe_05_fake_bank_advisory_remote_access",
        "category": "Bank Advisory / Tech Support",
        "description": "Scammer recites bank fraud disclaimer ('we never ask OTP') while instructing victim to install QuickSupport",
        "transcript": (
            "This is SBI risk prevention and security advisory division. As per RBI guidelines, we never ask OTP, PIN or password. "
            "We detected unauthorized login attempts on your pension account. To safeguard your savings, "
            "please install the official security verification tool QuickSupport or AnyDesk from Play Store immediately."
        ),
        "expected_true_nature": "scam",
        "risk_explanation": "Bypasses OTP warnings by asking for remote screen access software"
    },
    {
        "id": "probe_06_fake_challan_traffic_authority",
        "category": "Traffic / E-Challan",
        "description": "Fake traffic police e-challan with threat to impound vehicle unless fine paid immediately",
        "transcript": (
            "Delhi traffic police headquarters. Aapki gaadi par court order e-challan pending hai. "
            "Immediately right now 1200 rupees ka chalaan pay kijiye, nahi toh gaadi seize aur impound kar li jayegi."
        ),
        "expected_true_nature": "scam",
        "risk_explanation": "Impersonates traffic authority with immediate vehicle seizure threat"
    }
]


def run_whitelist_probes():
    print("=" * 75)
    print("        AUDIT: PROBING NAIVE WHITELISTS FOR SCAM LOOPHOLES")
    print("  [Note: Frozen classifier.py - Recording vulnerabilities objectively]")
    print("=" * 75 + "\n")

    results = []
    vulnerability_count = 0

    for idx, probe in enumerate(PROBE_SCENARIOS, 1):
        print(f"[{idx}/{len(PROBE_SCENARIOS)}] Probing: {probe['id']}")
        print(f"     Category: {probe['category']}")
        print(f"     Attack Vector: {probe['description']}")

        res = classify_caller(
            call_id=probe["id"],
            caller_number="+919876543210",
            conversation=[{"role": "caller", "text": probe["transcript"]}],
            language="hi" if "hi" in probe["id"] or "chachaji" in probe["transcript"].lower() else "en",
        )

        verdict = res.verdict
        confidence = res.confidence
        reason = res.reason
        method = res.method
        latency_ms = res.latency_ms

        is_vulnerable = (verdict == "genuine")
        if is_vulnerable:
            vulnerability_count += 1
            status_tag = "[CRITICAL VULNERABILITY: FALSE NEGATIVE (SCAM LABELED GENUINE)]"
        elif verdict == "scam":
            status_tag = "[BLOCKED AS SCAM]"
        else:
            status_tag = "[FLAGGED UNSURE / ESCALATED]"

        print(f"     Result: Verdict={verdict.upper()} (Confidence={confidence:.2f}, Method={method}, Latency={latency_ms:.1f}ms)")
        print(f"     Reason: {reason}")
        print(f"     Status: {status_tag}\n")

        results.append({
            "probe_id": probe["id"],
            "category": probe["category"],
            "description": probe["description"],
            "expected": probe["expected_true_nature"],
            "actual_verdict": verdict,
            "confidence": confidence,
            "method": method,
            "latency_ms": latency_ms,
            "reason": reason,
            "is_vulnerability": is_vulnerable,
            "risk_explanation": probe["risk_explanation"]
        })

    print("=" * 75)
    print(f"AUDIT SUMMARY: {vulnerability_count}/{len(PROBE_SCENARIOS)} probe scenarios successfully exploited whitelist loopholes!")
    print("=" * 75)

    output_path = os.path.join(ROOT_DIR, "evaluation", "whitelist_probe_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "audit_date": "2026-10-17T01:00:00Z",
            "total_probes": len(PROBE_SCENARIOS),
            "loopholes_detected": vulnerability_count,
            "probes": results
        }, f, indent=2)
    print(f"Saved detailed audit findings to {output_path}")
    return results


if __name__ == "__main__":
    run_whitelist_probes()
