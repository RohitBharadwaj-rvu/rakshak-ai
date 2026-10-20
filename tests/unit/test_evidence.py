"""
tests/unit/test_evidence.py - Unit tests for Chakshu & Report Suspect Evidence Packets (Addition 2).
"""

import pytest
from app.voice.evidence import (
    build_chakshu_packet,
    build_report_suspect_packets,
    compute_evidence_hash,
)


@pytest.fixture
def sample_call_record():
    return {
        "call_id": "call_test_evidence_101",
        "caller_number": "+919876543210",
        "start_time": "2026-10-20T10:00:00Z",
        "duration": 420,
        "transcript": "Caller: Transfer 25000 to fraud@upi or police warrant issued. Assistant: Let me find my glasses beta.",
        "summary": "Suspect posing as cyber police officer demanding UPI payment.",
        "recording_url": "https://storage.googleapis.com/guardianline-recordings/call_101.wav",
        "verdict": "scam",
        "extracted_intel": {
            "upi_ids": ["fraud@upi", "mule@okaxis"],
            "account_numbers": ["918273645019"],
            "ifsc_codes": ["SBIN0001234"],
            "phone_numbers": ["+919876543210", "+919123456789"],
            "links": ["https://pay-fine-portal.in"],
        },
    }


def test_compute_evidence_hash_deterministic(sample_call_record):
    h1 = compute_evidence_hash(
        sample_call_record["transcript"],
        sample_call_record["recording_url"],
        sample_call_record["caller_number"],
    )
    h2 = compute_evidence_hash(
        sample_call_record["transcript"],
        sample_call_record["recording_url"],
        sample_call_record["caller_number"],
    )
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length


def test_build_chakshu_packet(sample_call_record):
    packet = build_chakshu_packet(sample_call_record)
    assert packet.call_id == "call_test_evidence_101"
    assert packet.portal == "DoT Sanchar Saathi (Chakshu)"
    assert packet.money_lost is False
    assert len(packet.evidence_hash_sha256) == 64
    assert len(packet.suspect_identifiers) >= 5
    # Category should identify impersonation / digital arrest
    assert "Digital Arrest" in packet.category or "Police" in packet.category


def test_build_report_suspect_packets(sample_call_record):
    packets = build_report_suspect_packets(sample_call_record)
    assert len(packets) >= 5
    kinds = {p.identifier_type for p in packets}
    assert "upi" in kinds
    assert "account" in kinds
    assert "ifsc" in kinds
    for p in packets:
        assert p.associated_call_id == "call_test_evidence_101"
        assert p.caller_phone == "+919876543210"
        assert len(p.evidence_hash_sha256) == 64
