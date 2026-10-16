#!/usr/bin/env python3
"""
scripts/test_noisy_stt.py - Stress-Test Classifier Against Telephony STT Noise & Script Divergence.

Simulates acoustic and telephony speech-to-text corruption:
  1. Phonetic misspellings & STT confusion (e.g. 'cbi' -> 'see bee eye', 'pulis', 'any desk', 'o t p')
  2. Word drop / packet loss (telephony jitter)
  3. Mixed script code-switching (Devanagari + Latin transliteration)

Evaluates whether GuardianLine maintains >= 85% scam recall under degraded audio STT conditions.
"""

import json
import os
import random
import re
import sys
from typing import Dict, List, Tuple

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from app.voice.classifier import classify_caller

BENCHMARK_PATH = os.path.join(ROOT_DIR, "evaluation", "classifier", "classifier_set.jsonl")
REPORT_PATH = os.path.join(ROOT_DIR, "evaluation", "classifier", "stt_robustness_report.json")

# Phonetic & acoustic replacement map mimicking Indian telephony STT engines
PHONETIC_CORRUPTIONS = {
    r"\bcbi\b": ["see bee eye", "c b i", "seebi"],
    r"\bpolice\b": ["pulis", "poles", "पुलिश"],
    r"\barrest\b": ["arest", "aarest", "रेस्ट"],
    r"\bcustoms\b": ["kustoms", "kastams"],
    r"\bnarcotics\b": ["narkotics", "narkotik"],
    r"\bchallan\b": ["chalan", "chalaan", "चालान"],
    r"\belectricity\b": ["electricty", "elektricity", "bijli"],
    r"\burgent\b": ["arjent", "urgnt", "इमरजेंसी"],
    r"\botp\b": ["o t p", "odp", "ओ टी पी"],
    r"\banydesk\b": ["anidask", "any desk", "eneedask"],
    r"\baadhaar\b": ["adhar", "aaddhar", "आधर"],
    r"\baccount\b": ["acnt", "a/c", "akkount", "खाता"],
    r"\bdigit\b": ["dijit", "नंबर"],
    r"पेंशन": ["pension", "पैनशन"],
    r"हवाला": ["hawala", "हवाला"],
}


def corrupt_stt_text(text: str, noise_level: float = 0.3) -> str:
    """Applies phonetic substitutions and telephony packet drops to text."""
    corrupted = text

    # Apply phonetic substitutions
    for pattern, replacements in PHONETIC_CORRUPTIONS.items():
        if re.search(pattern, corrupted, re.IGNORECASE):
            rep = random.choice(replacements)
            corrupted = re.sub(pattern, rep, corrupted, flags=re.IGNORECASE)

    # Telephony packet loss: randomly drop 5-10% of non-essential words
    words = corrupted.split()
    retained_words = []
    for w in words:
        if len(w) <= 3 and random.random() < 0.10:
            continue  # Dropped short word
        retained_words.append(w)

    return " ".join(retained_words)


def run_stt_noise_benchmark():
    random.seed(42)  # Deterministic test seed

    if not os.path.exists(BENCHMARK_PATH):
        from scripts.generate_classifier_benchmark import generate_cuts_from_scenarios
        generate_cuts_from_scenarios()

    cuts = []
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cuts.append(json.loads(line))

    scam_total = 0
    scam_detected = 0
    genuine_total = 0
    genuine_false_positives = 0

    print(f"\n[NoisySTT] Running robustness stress-test across {len(cuts)} degraded STT cuts...\n")

    for cut in cuts:
        expected = cut["expected_verdict"]
        original_turns = cut["conversation"]

        # Corrupt caller turns with STT noise
        noisy_turns = []
        for t in original_turns:
            corrupted_content = corrupt_stt_text(t["content"])
            noisy_turns.append({"role": t["role"], "content": corrupted_content})

        result = classify_caller(
            call_id=f"noisy_{cut['case_id']}",
            caller_number="+919876543210",
            conversation=noisy_turns,
            language=cut.get("language", "hi"),
        )

        if expected == "scam":
            scam_total += 1
            if result.verdict == "scam":
                scam_detected += 1
        elif expected == "genuine":
            genuine_total += 1
            if result.verdict == "scam":
                genuine_false_positives += 1

    recall = (scam_detected / scam_total * 100.0) if scam_total > 0 else 0.0
    fpr = (genuine_false_positives / genuine_total * 100.0) if genuine_total > 0 else 0.0

    print("=" * 65)
    print("      TELEPHONY STT NOISE & PHONETIC STRESS-TEST RESULTS")
    print("=" * 65)
    print(f"Total Degraded Cuts Evaluated : {len(cuts)}")
    print(f"Degraded Scam Recall (All)    : {scam_detected}/{scam_total} ({recall:.1f}%) [Bar: >= 85%]")
    print(f"Degraded False Positive Rate  : {genuine_false_positives}/{genuine_total} ({fpr:.1f}%) [Bar: <= 5%]")
    passed = recall >= 85.0 and fpr <= 5.0
    print("-" * 65)
    print(f"Robustness Verdict            : {'[PASS] ROBUST AGAINST TELEPHONY NOISE' if passed else '[FAIL]'}")
    print("=" * 65 + "\n")

    report = {
        "total_evaluated_cuts": len(cuts),
        "degraded_scam_recall_pct": round(recall, 2),
        "degraded_false_positive_rate_pct": round(fpr, 2),
        "pass_robustness_bar": passed,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)
    print(f"[NoisySTT] Saved robustness report to {REPORT_PATH}")

    return report


if __name__ == "__main__":
    run_stt_noise_benchmark()
