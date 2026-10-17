"""
tests/llm/test_cleanup.py - Post-Call LLM Cleanup & Grounded Summary Suite (T-CLEAN).

Verifies across 30 hard transcripts (3 runs each = 90 runs):
  - 6 split-digit transcripts (digits split across turns)
  - 6 mid-call correction transcripts ("no, the last digit is seven")
  - 6 speech-to-text slip transcripts ("okay axis", "pay t m")
  - 6 disagreeing `log_intel` transcripts (`log_intel` disagrees with transcript)
  - 6 zero-intel transcripts (calls with no intel produce empty intel)
  - Output validates against the CallRecord `extracted_intel` schema
  - Zero ungrounded values across all 90 runs (cites turn indices that contain the value)
  - 100% format check pass (UPI, IFSC, phone, bank account, PAN, link)
  - Corrections come out right in >= 90% of correction runs
  - Summary is <= 80 words, states verdict and scam_type, and contains no ungrounded detail
"""

import json
import os
import re
import sys
import pytest
from jsonschema import validate

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.voice.cleanup import (
    cleanup_call_intel,
    validate_entity_format,
    verify_value_grounded,
)

CALL_RECORD_SCHEMA_PATH = os.path.join(ROOT_DIR, "contracts", "call_record.schema.json")


@pytest.fixture(scope="module")
def intel_schema():
    with open(CALL_RECORD_SCHEMA_PATH, "r", encoding="utf-8") as f:
        full_schema = json.load(f)
    return full_schema["properties"]["extracted_intel"]


def build_30_hard_transcripts():
    return [
        # ======================================================================
        # Category 1: Digits split across turns (6 cases)
        # ======================================================================
        {
            "id": "split_01_phone_en",
            "category": "split",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Write down my supervisor number: nine eight seven six five"},
                {"role": "assistant", "content": "Okay beta, 98765... go ahead."},
                {"role": "user", "content": "four three two one zero"},
            ],
            "mid_call_logs": [],
            "expected": {"phone_numbers": ["9876543210"]},
        },
        {
            "id": "split_02_phone_hi",
            "category": "split",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "नंबर लिखो नौ एक दो तीन चार"},
                {"role": "assistant", "content": "हाँ बेटा आगे बोलो"},
                {"role": "user", "content": "पाँच छह सात आठ नौ"},
            ],
            "mid_call_logs": [],
            "expected": {"phone_numbers": ["9123456789"]},
        },
        {
            "id": "split_03_account_en",
            "category": "split",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Account first part is five zero one zero zero four"},
                {"role": "assistant", "content": "501004, noted."},
                {"role": "user", "content": "three two eight nine one two"},
            ],
            "mid_call_logs": [],
            "expected": {"bank_accounts": ["501004328912"]},
        },
        {
            "id": "split_04_account_hi",
            "category": "split",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "खाता संख्या लिखिए तीन शून्य दो शून्य एक एक"},
                {"role": "assistant", "content": "लिख लिया बेटा"},
                {"role": "user", "content": "दो दो तीन तीन चार चार"},
            ],
            "mid_call_logs": [],
            "expected": {"bank_accounts": ["302011223344"]},
        },
        {
            "id": "split_05_phone_mixed",
            "category": "split",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "My whatsapp number starts with eight आठ सात छह पांच"},
                {"role": "assistant", "content": "Ji beta"},
                {"role": "user", "content": "four three two one zero"},
            ],
            "mid_call_logs": [],
            "expected": {"phone_numbers": ["8876543210"]},
        },
        {
            "id": "split_06_account_11digits",
            "category": "split",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "SBI account starts with 109876"},
                {"role": "assistant", "content": "Okay"},
                {"role": "user", "content": "and ends with 54321"},
            ],
            "mid_call_logs": [],
            "expected": {"bank_accounts": ["10987654321"]},
        },

        # ======================================================================
        # Category 2: Number corrected mid-call (6 cases)
        # ======================================================================
        {
            "id": "corr_01_last_digit_seven",
            "category": "correction",
            "verdict": "scam",
            "transcript": [
                {
                    "role": "user",
                    "content": "Call me at 9876543219... no, the last digit is seven",
                }
            ],
            "mid_call_logs": [],
            "expected": {"phone_numbers": ["9876543217"]},
            "forbidden": ["9876543219"],
        },
        {
            "id": "corr_02_last_digit_hindi",
            "category": "correction",
            "verdict": "scam",
            "transcript": [
                {
                    "role": "user",
                    "content": "खाता नंबर है 50100432891235... नहीं आखिरी अंक चार है",
                }
            ],
            "mid_call_logs": [],
            "expected": {"bank_accounts": ["50100432891234"]},
            "forbidden": ["50100432891235"],
        },
        {
            "id": "corr_03_cross_turn_last_digit",
            "category": "correction",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "My phone number is 9811223349"},
                {"role": "assistant", "content": "9811223349?"},
                {"role": "user", "content": "Sorry mistake, the last digit is 4"},
            ],
            "mid_call_logs": [],
            "expected": {"phone_numbers": ["9811223344"]},
            "forbidden": ["9811223349"],
        },
        {
            "id": "corr_04_upi_replacement_inline",
            "category": "correction",
            "verdict": "scam",
            "transcript": [
                {
                    "role": "user",
                    "content": "Send to wrong.id@okaxis... wait no sorry, send to right.id@paytm",
                }
            ],
            "mid_call_logs": [],
            "expected": {"upi_ids": ["right.id@paytm"]},
            "forbidden": ["wrong.id@okaxis"],
        },
        {
            "id": "corr_05_account_replacement_inline",
            "category": "correction",
            "verdict": "scam",
            "transcript": [
                {
                    "role": "user",
                    "content": "Account is 400011112222... no sorry, instead use 400099998888",
                }
            ],
            "mid_call_logs": [],
            "expected": {"bank_accounts": ["400099998888"]},
            "forbidden": ["400011112222"],
        },
        {
            "id": "corr_06_last_two_digits",
            "category": "correction",
            "verdict": "scam",
            "transcript": [
                {
                    "role": "user",
                    "content": "Number is 9765432100... wait, the last two digits are 89",
                }
            ],
            "mid_call_logs": [],
            "expected": {"phone_numbers": ["9765432189"]},
            "forbidden": ["9765432100"],
        },

        # ======================================================================
        # Category 3: Speech-to-text slips (6 cases)
        # ======================================================================
        {
            "id": "slip_01_okay_axis",
            "category": "stt_slip",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Send money to cbi dot officer at the rate okay axis"}
            ],
            "mid_call_logs": [],
            "expected": {"upi_ids": ["cbi.officer@okaxis"]},
        },
        {
            "id": "slip_02_okay_hdfc_bank",
            "category": "stt_slip",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Pay ramesh dot tax at rate okay hdfc bank"}
            ],
            "mid_call_logs": [],
            "expected": {"upi_ids": ["ramesh.tax@okhdfcbank"]},
        },
        {
            "id": "slip_03_pay_t_m",
            "category": "stt_slip",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Transfer to 9884567890 at the rate pay t m"}
            ],
            "mid_call_logs": [],
            "expected": {"upi_ids": ["9884567890@paytm"]},
        },
        {
            "id": "slip_04_y_b_l",
            "category": "stt_slip",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "UPI ID is customs dot cell at the rate y b l"}
            ],
            "mid_call_logs": [],
            "expected": {"upi_ids": ["customs.cell@ybl"]},
        },
        {
            "id": "slip_05_okay_icici",
            "category": "stt_slip",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Send deposit to court dot treasury at the rate okay icici"}
            ],
            "mid_call_logs": [],
            "expected": {"upi_ids": ["court.treasury@okicici"]},
        },
        {
            "id": "slip_06_okay_sbi",
            "category": "stt_slip",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Pay penalty to challan dot desk at the rate okay sbi"}
            ],
            "mid_call_logs": [],
            "expected": {"upi_ids": ["challan.desk@oksbi"]},
        },

        # ======================================================================
        # Category 4: `log_intel` values that disagree with transcript (6 cases)
        # ======================================================================
        {
            "id": "disagree_01_upi_typo_in_log",
            "category": "disagree",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Transfer to real.scammer@okaxis immediately"}
            ],
            "mid_call_logs": [
                {
                    "type": "upi",
                    "value_as_heard": "hallucinated.scammer@okaxis",
                    "normalized_value": "hallucinated.scammer@okaxis",
                    "unparseable": False,
                }
            ],
            "expected": {"upi_ids": ["real.scammer@okaxis"]},
            "forbidden": ["hallucinated.scammer@okaxis"],
        },
        {
            "id": "disagree_02_phone_typo_in_log",
            "category": "disagree",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Call my supervisor on 9876543210 right now"}
            ],
            "mid_call_logs": [
                {
                    "type": "phone",
                    "value_as_heard": "9999988888",
                    "normalized_value": "9999988888",
                    "unparseable": False,
                }
            ],
            "expected": {"phone_numbers": ["9876543210"]},
            "forbidden": ["9999988888"],
        },
        {
            "id": "disagree_03_account_typo_in_log",
            "category": "disagree",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Deposit in account 50100432891234"}
            ],
            "mid_call_logs": [
                {
                    "type": "account",
                    "value_as_heard": "11112222333344",
                    "normalized_value": "11112222333344",
                    "unparseable": False,
                }
            ],
            "expected": {"bank_accounts": ["50100432891234"]},
            "forbidden": ["11112222333344"],
        },
        {
            "id": "disagree_04_ifsc_typo_in_log",
            "category": "disagree",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "IFSC code is HDFC0001234"}
            ],
            "mid_call_logs": [
                {
                    "type": "ifsc",
                    "value_as_heard": "SBIN0009999",
                    "normalized_value": "SBIN0009999",
                    "unparseable": False,
                }
            ],
            "expected": {"ifsc_codes": ["HDFC0001234"]},
            "forbidden": ["SBIN0009999"],
        },
        {
            "id": "disagree_05_pan_typo_in_log",
            "category": "disagree",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Enter PAN card ABCDE1234F on the form"}
            ],
            "mid_call_logs": [
                {
                    "type": "pan",
                    "value_as_heard": "ZZZZZ9999Z",
                    "normalized_value": "ZZZZZ9999Z",
                    "unparseable": False,
                }
            ],
            "expected": {"pan_numbers": ["ABCDE1234F"]},
            "forbidden": ["ZZZZZ9999Z"],
        },
        {
            "id": "disagree_06_link_typo_in_log",
            "category": "disagree",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Open https://rbi-verify.xyz/pay on your phone"}
            ],
            "mid_call_logs": [
                {
                    "type": "link",
                    "value_as_heard": "https://fake-ungrounded.xyz/pay",
                    "normalized_value": "https://fake-ungrounded.xyz/pay",
                    "unparseable": False,
                }
            ],
            "expected": {"links": ["https://rbi-verify.xyz/pay"]},
            "forbidden": ["https://fake-ungrounded.xyz/pay"],
        },

        # ======================================================================
        # Category 5: Calls with no intel at all (6 cases)
        # ======================================================================
        {
            "id": "empty_01_courier",
            "category": "no_intel",
            "verdict": "genuine",
            "transcript": [
                {"role": "user", "content": "Bhaiya main Blue Dart courier se bol raha hoon, parcel gate par hai."}
            ],
            "mid_call_logs": [],
            "expected": {},
        },
        {
            "id": "empty_02_clinic",
            "category": "no_intel",
            "verdict": "genuine",
            "transcript": [
                {"role": "user", "content": "Good morning, calling from Apollo Clinic to confirm tomorrow's 11:30 AM checkup."}
            ],
            "mid_call_logs": [],
            "expected": {},
        },
        {
            "id": "empty_03_wrong_number",
            "category": "no_intel",
            "verdict": "unsure",
            "transcript": [
                {"role": "user", "content": "Hello, is this Rajesh? Oh sorry, wrong number."}
            ],
            "mid_call_logs": [],
            "expected": {},
        },
        {
            "id": "empty_04_society_guard",
            "category": "no_intel",
            "verdict": "genuine",
            "transcript": [
                {"role": "user", "content": "Sahab main gate se guard bol raha hoon, doodhwala aaya hai."}
            ],
            "mid_call_logs": [],
            "expected": {},
        },
        {
            "id": "empty_05_otp_scam_without_account",
            "category": "no_intel",
            "verdict": "scam",
            "transcript": [
                {"role": "user", "content": "Tell me the 6 digit OTP sent to your phone right now or your card will block!"}
            ],
            "mid_call_logs": [],
            "expected": {},
        },
        {
            "id": "empty_06_school_teacher",
            "category": "no_intel",
            "verdict": "genuine",
            "transcript": [
                {"role": "user", "content": "Namaste, main school se class teacher bol rahi hoon, kal PTM hai."}
            ],
            "mid_call_logs": [],
            "expected": {},
        },
    ]


def test_30_hard_transcripts_present():
    cases = build_30_hard_transcripts()
    assert len(cases) == 30


def test_90_runs_zero_ungrounded_schema_format_summary_and_corrections(intel_schema):
    cases = build_30_hard_transcripts()
    entity_keys = ["upi_ids", "phone_numbers", "bank_accounts", "ifsc_codes", "pan_numbers", "links"]

    ungrounded_count = 0
    total_runs = 0
    correction_runs = 0
    correction_successes = 0

    for case in cases:
        for _run in range(3):
            total_runs += 1
            res = cleanup_call_intel(
                transcript=case["transcript"],
                verdict=case["verdict"],
                mid_call_logs=case["mid_call_logs"],
            )
            intel = res["extracted_intel"]
            summary = res["summary"]
            scam_type = res["scam_type"]

            # 1. Schema validation
            validate(instance=intel, schema=intel_schema)

            # 2. Grounding & format check for every extracted value
            citations = intel.get("citations", {})
            for k in entity_keys:
                for val in intel[k]:
                    assert validate_entity_format(k, val), f"Format check failed for {k}={val}"
                    cites = citations.get(val, [])
                    if not verify_value_grounded(k, val, cites, case["transcript"]):
                        ungrounded_count += 1

            # 3. Summary checks: <= 80 words, states verdict & scam_type, no missing details
            words = summary.split()
            assert len(words) <= 80, f"Summary exceeded 80 words ({len(words)} words)"
            assert case["verdict"] in summary.lower()
            expected_scam_label = "none" if (case["verdict"] == "genuine" and scam_type == "general_telephony") else scam_type
            assert expected_scam_label.lower() in summary.lower()

            # Check no forbidden / retracted value appears in intel or summary
            for bad in case.get("forbidden", []):
                for k in entity_keys:
                    assert bad.lower() not in {x.lower() for x in intel[k]}
                assert bad.lower() not in summary.lower()

            # 4. Check expected values for every category
            if case["category"] == "no_intel":
                for k in entity_keys:
                    assert intel[k] == [], f"Expected empty {k} on {case['id']}, got {intel[k]}"
            else:
                case_ok = True
                for k, exp_vals in case["expected"].items():
                    if {x.lower() for x in intel[k]} != {x.lower() for x in exp_vals}:
                        case_ok = False
                if case["category"] == "correction":
                    correction_runs += 1
                    if case_ok:
                        correction_successes += 1
                else:
                    assert case_ok, f"Case {case['id']} mismatch: got {intel}, expected {case['expected']}"

    assert total_runs == 90
    assert ungrounded_count == 0, f"Found {ungrounded_count} ungrounded values across 90 runs!"
    assert correction_runs == 18
    correction_rate = correction_successes / correction_runs
    assert correction_rate >= 0.90, f"Correction accuracy {correction_rate:.2%} < 90%"
