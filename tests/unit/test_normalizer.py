"""
tests/unit/test_normalizer.py - Unit Test Suite for Spoken-Number Normalizer (T-NORM).

Verifies:
  - Corpus has >= 150 cases (40+ English, 40+ Hindi, 40+ Tamil, 30+ unchanged)
  - 100% of corpus cases pass deterministically
  - Runs in < 50 ms on a 10-minute transcript
"""

import os
import sys
import time
import pytest
import yaml

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.voice.normalizer import normalize_spoken_text
CORPUS_PATH = os.path.join(ROOT_DIR, "tests", "data", "spoken_numbers.yaml")


def load_corpus():
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["cases"]


@pytest.fixture(scope="module")
def corpus_cases():
    return load_corpus()


def test_corpus_size_and_distribution(corpus_cases):
    assert len(corpus_cases) >= 150, f"Expected >= 150 cases, found {len(corpus_cases)}"
    en_cases = [c for c in corpus_cases if c["id"].startswith("en_")]
    hi_cases = [c for c in corpus_cases if c["id"].startswith("hi_")]
    ta_cases = [c for c in corpus_cases if c["id"].startswith("ta_")]
    un_cases = [c for c in corpus_cases if c["id"].startswith("un_")]
    assert len(en_cases) >= 40
    assert len(hi_cases) >= 40
    assert len(ta_cases) >= 40
    assert len(un_cases) >= 30


@pytest.mark.parametrize(
    "case",
    load_corpus(),
    ids=lambda c: f"{c['id']}_{c['group']}",
)
def test_spoken_number_corpus_case(case):
    actual = normalize_spoken_text(case["input"])
    assert actual == case["expected"], (
        f"Case {case['id']} ({case['group']}) failed:\n"
        f"  Input:    {case['input']!r}\n"
        f"  Expected: {case['expected']!r}\n"
        f"  Actual:   {actual!r}"
    )


def test_normalizer_speed_under_50ms_on_10min_transcript():
    # A 10-minute phone transcript is roughly 80 turns (~1,200 words)
    sample_turn = (
        "नोट करो यूपीआई आईडी cbi dot officer dot verma at the rate ok axis "
        "और नंबर है नौ आठ सात छह पाँच चार तीन दो एक शून्य। "
    )
    ten_minute_transcript = "\n".join([sample_turn] * 80)

    t0 = time.perf_counter()
    result = normalize_spoken_text(ten_minute_transcript)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert "cbi.officer.verma@okaxis" in result
    assert "9876543210" in result
    assert elapsed_ms < 50.0, f"Normalizer took {elapsed_ms:.2f} ms (bar: < 50 ms)"
