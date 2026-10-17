"""
tests/unit/test_extractor.py - Rule-Based Transcript Extractor Unit Suite (T-EXT).

Verifies:
  - Labeled set of >= 60 transcripts with speaker turns (fixtures + scenario transcripts + hand-labeled cases)
  - UPI handles (name@okaxis, 9876543210@ybl, name@paytm)
  - Phone numbers (+91 98765 43210, 098765 43210, 9876543210; 10-digit starting 0-5 rejected)
  - Account numbers (9 to 18 digits), IFSC, PAN, links
  - Negatives: 4-6 digit OTP, currency amount, date
  - Speaker attribution: assistant/agent turns (including approved bait) are NEVER extracted
  - Repeats merge: a UPI ID said 3 times becomes 1 entity with count=3 in `entity_counts`
  - Precision >= 0.95 and Recall >= 0.90 per entity type, zero bait values extracted
"""

import glob
import json
import os
import re
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.rules import APPROVED_BAIT_VALUES
from app.voice.extractor import extract_from_transcript
from app.voice.normalizer import normalize_spoken_text

FIXTURES_DIR = os.path.join(ROOT_DIR, "tests", "fixtures")
SCENARIOS_DIR = os.path.join(ROOT_DIR, "evaluation", "scenarios")


def _build_labeled_transcript_dataset():
    """
    Build a hand-labeled dataset of >= 60 transcripts combining:
      1. The 6 official Bolna webhook fixtures in tests/fixtures/
      2. All 36 scenario files in evaluation/scenarios/ (with speaker turns + injected agent bait turns),
         labeled with the planted entities that are actually spoken in the caller script
      3. 22 hand-labeled transcripts covering all entity types, spoken numbers, negatives, and bait checks
    """
    dataset = []

    # 1. Official 6 fixtures
    for fpath in sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json"))):
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        planted = data.get("metadata", {}).get("planted_intel", {})
        dataset.append(
            {
                "id": data["call_id"],
                "transcript": data["transcript"],
                "expected": {
                    "upi_ids": [planted["upi_id"].lower()] if "upi_id" in planted else [],
                    "phone_numbers": [planted["phone_number"]] if "phone_number" in planted else [],
                    "bank_accounts": [planted["account_number"]] if "account_number" in planted else [],
                    "ifsc_codes": [planted["ifsc_code"].upper()] if "ifsc_code" in planted else [],
                    "pan_numbers": [],
                    "links": [],
                },
            }
        )

    # 2. All 36 scenarios in evaluation/scenarios/
    for spath in sorted(glob.glob(os.path.join(SCENARIOS_DIR, "*.json"))):
        with open(spath, "r", encoding="utf-8") as f:
            sc = json.load(f)
        turns = []
        caller_texts = []
        for idx, turn_obj in enumerate(sc.get("caller_script", [])):
            text = turn_obj.get("text", "") if isinstance(turn_obj, dict) else str(turn_obj)
            caller_texts.append(text)
            turns.append({"role": "user", "content": text, "timestamp": float(idx * 5 + 1)})
            # Inject an assistant turn with approved bait to test speaker attribution
            turns.append(
                {
                    "role": "assistant",
                    "content": (
                        "Beta mera UPI ramesh.elderly@okhdfc hai aur account 9999000011112222 "
                        "IFSC HDFC0009999 phone 9000011111 hai."
                    ),
                    "timestamp": float(idx * 5 + 3),
                }
            )

        norm_joined = normalize_spoken_text(" ".join(caller_texts)).lower()
        planted = sc.get("planted_details", {})

        # Only expect planted items that are actually spoken in the caller script turns
        exp_upis = [
            u.lower()
            for u in planted.get("upi_ids", [])
            if u.lower() in norm_joined
        ]
        exp_phones = []
        norm_without_upi = re.sub(r"[a-zA-Z0-9._-]+@[a-zA-Z0-9]+", "", norm_joined)
        for p in planted.get("phone_numbers", []):
            clean_p = p.lstrip("+")
            if clean_p.startswith("91") and len(clean_p) == 12:
                clean_p = clean_p[2:]
            if clean_p in norm_without_upi:
                exp_phones.append(clean_p)

        raw_accounts = planted.get("account_numbers", []) or planted.get("bank_accounts", [])
        exp_accounts = [a for a in raw_accounts if a.lower() in norm_joined]
        exp_ifscs = [i.upper() for i in planted.get("ifsc_codes", []) if i.lower() in norm_joined]
        exp_links = [lnk for lnk in planted.get("links", []) if lnk.lower() in norm_joined]

        dataset.append(
            {
                "id": f"scenario_{sc['id']}",
                "transcript": turns,
                "expected": {
                    "upi_ids": exp_upis,
                    "phone_numbers": exp_phones,
                    "bank_accounts": exp_accounts,
                    "ifsc_codes": exp_ifscs,
                    "pan_numbers": [],
                    "links": exp_links,
                },
            }
        )

    # 3. 22 hand-labeled transcripts covering all formats, negatives, PAN, links, IFSC, repeats
    synthetic = [
        {
            "id": "syn_01_phone_formats",
            "transcript": [
                {"role": "user", "content": "Call me on +91 98765 43210 or 091234 56789 or 8765432109."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": ["9876543210", "9123456789", "8765432109"],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_02_invalid_phone_0_to_5_rejected",
            "transcript": [
                {"role": "user", "content": "My reference account is 1234567890 and 5432167890."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": ["1234567890", "5432167890"],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_03_upi_variants",
            "transcript": [
                {"role": "user", "content": "Send to ramesh.scam@okaxis or 9876543210@ybl or verify_kyc@paytm."}
            ],
            "expected": {
                "upi_ids": ["ramesh.scam@okaxis", "9876543210@ybl", "verify_kyc@paytm"],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_04_account_ifsc_pan_link",
            "transcript": [
                {
                    "role": "user",
                    "content": (
                        "Deposit into account 123456789012, IFSC SBIN0004321, "
                        "PAN ABCDE1234F, and click https://kyc-sbi-update.xyz/login"
                    ),
                }
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": ["123456789012"],
                "ifsc_codes": ["SBIN0004321"],
                "pan_numbers": ["ABCDE1234F"],
                "links": ["https://kyc-sbi-update.xyz/login"],
            },
        },
        {
            "id": "syn_05_negative_otp_amount_date",
            "transcript": [
                {
                    "role": "user",
                    "content": "The OTP is 482910, send 50000 rupees by 17/10/2026 at 11:30 am.",
                }
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_06_speaker_attribution_assistant_ignored",
            "transcript": [
                {
                    "role": "assistant",
                    "content": (
                        "My UPI is ramesh.elderly@okhdfc, sunita.pension@okicici, prof.iyer@sbi, "
                        "account 9999000011112222, phone 9876500001, IFSC HDFC0009999, PAN ZZZZZ9999Z."
                    ),
                },
                {"role": "user", "content": "Okay, just wait on the line."},
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_07_spoken_hindi_account_and_ifsc",
            "transcript": [
                {
                    "role": "user",
                    "content": (
                        "खाता नंबर है तीन शून्य दो शून्य एक एक दो दो तीन तीन चार और आईएफएससी एस बी आई एन शून्य शून्य शून्य एक एक दो दो"
                    ),
                }
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": ["30201122334"],
                "ifsc_codes": ["SBIN0001122"],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_08_pan_and_link_2",
            "transcript": [
                {
                    "role": "user",
                    "content": "Verify PAN PQRSX5678K at www.rbi-safe-verify.in/form immediately.",
                }
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": ["PQRSX5678K"],
                "links": ["www.rbi-safe-verify.in/form"],
            },
        },
        {
            "id": "syn_09_pan_3",
            "transcript": [
                {"role": "user", "content": "Tax officer PAN is LMNOP9012Q and IFSC is ICIC0002233."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": ["ICIC0002233"],
                "pan_numbers": ["LMNOP9012Q"],
                "links": [],
            },
        },
        {
            "id": "syn_10_18_digit_account",
            "transcript": [
                {"role": "user", "content": "Transfer to 18-digit account 100020003000400050 right now."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": ["100020003000400050"],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_11_9_digit_account",
            "transcript": [
                {"role": "user", "content": "Old co-op account is 450011223 and IFSC UBIN0554433."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": ["450011223"],
                "ifsc_codes": ["UBIN0554433"],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_12_email_excluded_from_upi",
            "transcript": [
                {"role": "user", "content": "Email us at support@gmail.com or help@yahoo.com."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_13_spoken_upi_english",
            "transcript": [
                {"role": "user", "content": "Pay to customs dot duty at the rate ok icici"}
            ],
            "expected": {
                "upi_ids": ["customs.duty@okicici"],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_14_spoken_phone_repeats",
            "transcript": [
                {"role": "user", "content": "Call nine double eight triple seven double six five four"}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": ["9887776654"],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_15_apk_link",
            "transcript": [
                {"role": "user", "content": "Download https://sbi-reward-update.top/app.apk now."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": ["https://sbi-reward-update.top/app.apk"],
            },
        },
        {
            "id": "syn_16_genuine_hospital_no_intel",
            "transcript": [
                {"role": "user", "content": "Please bring the patient's reports by 4:30 pm to Counter 4."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_17_genuine_school_no_intel",
            "transcript": [
                {"role": "user", "content": "Parent teacher meeting is on 24-10-2026 in Room 102."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_18_bait_spoken_by_scammer_echo_filtered",
            "transcript": [
                {
                    "role": "user",
                    "content": "Okay I see your UPI is ramesh.elderly@okhdfc, now send to my UPI arrest.fund@okaxis",
                }
            ],
            "expected": {
                "upi_ids": ["arrest.fund@okaxis"],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": [],
            },
        },
        {
            "id": "syn_19_pan_4",
            "transcript": [
                {"role": "user", "content": "Quote PAN BDFGH2345M on the challan form."}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": ["BDFGH2345M"],
                "links": [],
            },
        },
        {
            "id": "syn_20_link_4",
            "transcript": [
                {"role": "user", "content": "Pay challan at https://echallan-parivahan-pay.click/pay"}
            ],
            "expected": {
                "upi_ids": [],
                "phone_numbers": [],
                "bank_accounts": [],
                "ifsc_codes": [],
                "pan_numbers": [],
                "links": ["https://echallan-parivahan-pay.click/pay"],
            },
        },
    ]

    dataset.extend(synthetic)
    return dataset


def test_labeled_set_has_at_least_60_transcripts():
    ds = _build_labeled_transcript_dataset()
    assert len(ds) >= 60, f"Expected >= 60 labeled transcripts, got {len(ds)}"


def test_repeats_merge_with_count_of_3():
    transcript = [
        {"role": "user", "content": "Send money to scammer.boss@okaxis"},
        {"role": "assistant", "content": "Please repeat slowly beta."},
        {"role": "user", "content": "It is scammer dot boss at the rate ok axis"},
        {"role": "assistant", "content": "Let me confirm."},
        {"role": "user", "content": "Yes, scammer.boss@okaxis right now!"},
    ]
    res = extract_from_transcript(transcript)
    assert res["upi_ids"] == ["scammer.boss@okaxis"]
    assert res["entity_counts"]["scammer.boss@okaxis"] == 3


def test_precision_recall_and_zero_bait_leaks_across_60_plus_transcripts():
    ds = _build_labeled_transcript_dataset()
    entity_keys = ["upi_ids", "phone_numbers", "bank_accounts", "ifsc_codes", "pan_numbers", "links"]

    tp = {k: 0 for k in entity_keys}
    fp = {k: 0 for k in entity_keys}
    fn = {k: 0 for k in entity_keys}
    bait_leaks = 0

    for item in ds:
        actual = extract_from_transcript(item["transcript"])
        expected = item["expected"]

        for k in entity_keys:
            act_set = {x.lower() for x in actual[k]}
            exp_set = {x.lower() for x in expected[k]}

            for val in act_set:
                if val in APPROVED_BAIT_VALUES:
                    bait_leaks += 1

            tp[k] += len(act_set & exp_set)
            fp[k] += len(act_set - exp_set)
            fn[k] += len(exp_set - act_set)

    assert bait_leaks == 0, f"Extracted {bait_leaks} bait values as scammer intel!"

    for k in entity_keys:
        precision = tp[k] / (tp[k] + fp[k]) if (tp[k] + fp[k]) > 0 else 1.0
        recall = tp[k] / (tp[k] + fn[k]) if (tp[k] + fn[k]) > 0 else 1.0
        assert precision >= 0.95, f"{k} precision {precision:.3f} < 0.95 (TP={tp[k]}, FP={fp[k]})"
        assert recall >= 0.90, f"{k} recall {recall:.3f} < 0.90 (TP={tp[k]}, FN={fn[k]})"
