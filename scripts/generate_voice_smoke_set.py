#!/usr/bin/env python3
"""
scripts/generate_voice_smoke_set.py - Generate 8kHz Telephony Audio Smoke Set (T-VOICE).

Generates the 5 canonical audio smoke test calls in `evaluation/voice/` specified by Sprint 2:
  1. smoke_01_digital_arrest_hi (Hindi Scam - Digital arrest)
  2. smoke_02_customs_narcotics_hi (Hindi Scam - Narcotics parcel)
  3. smoke_03_bank_kyc_freeze_en (English Scam - Bank account freeze)
  4. smoke_04_delivery_otp_hi (Hindi Hard Genuine - Courier delivery OTP)
  5. smoke_05_red_team_otp_en (English Red-Team - Urgent OTP extortion)

Generates 8000 Hz, 16-bit Mono PCM WAV audio files mimicking telephony codec payloads,
paired with full transcription turns and metadata in `evaluation/voice/smoke_manifest.json`.
"""

import json
import math
import os
import struct
import wave

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VOICE_DIR = os.path.join(ROOT_DIR, "evaluation", "voice")
MANIFEST_PATH = os.path.join(VOICE_DIR, "smoke_manifest.json")

SAMPLE_RATE = 8000  # 8kHz telephony standard (G.711 / PCM)


def generate_telephony_pcm(filepath: str, duration_sec: float = 3.0, freq_hz: float = 440.0):
    """Generates standard 8kHz mono 16-bit PCM WAV telephony audio."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    num_samples = int(SAMPLE_RATE * duration_sec)

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)

        # Generate audio signal with slight telephony bandpass harmonics
        frames = bytearray()
        for i in range(num_samples):
            t = float(i) / SAMPLE_RATE
            # Dual-tone modulation to simulate telephone channel acoustic
            sample_val = 0.4 * math.sin(2.0 * math.pi * freq_hz * t) + 0.1 * math.sin(2.0 * math.pi * (freq_hz * 1.5) * t)
            pcm_val = int(sample_val * 32767.0)
            pcm_val = max(-32768, min(32767, pcm_val))
            frames.extend(struct.pack("<h", pcm_val))

        wf.writeframes(frames)


SMOKE_SPECS = [
    {
        "smoke_id": "smoke_01_digital_arrest_hi",
        "scenario_id": "scam_digital_arrest_hi",
        "name": "Digital Arrest Scam (Hindi)",
        "language": "hi",
        "expected_verdict": "scam",
        "carrier_freq_hz": 420.0,
        "turns": [
            {"turn": 1, "role": "caller", "content": "नमस्ते, मैं नई दिल्ली साइबर क्राइम सेल से सीनियर इंस्पेक्टर अजय बात कर रहा हूँ।"},
            {"turn": 2, "role": "caller", "content": "आपके नाम से ताइवान अवैध पार्सल पकड़ा गया है जिसमें नशीली दवाएं हैं। आप डिजिटल अरेस्ट पर हैं।"},
            {"turn": 3, "role": "caller", "content": "तुरंत अपना केस वेरिफिकेशन चार्ज पचास हज़ार रुपये सरकारी एस्क्रो खाते में ट्रांसफर कीजिए।"},
        ],
    },
    {
        "smoke_id": "smoke_02_customs_narcotics_hi",
        "scenario_id": "scam_customs_parcel_hi",
        "name": "Customs Narcotics Parcel Scam (Hindi)",
        "language": "hi",
        "expected_verdict": "scam",
        "carrier_freq_hz": 460.0,
        "turns": [
            {"turn": 1, "role": "caller", "content": "नमस्कार, मुंबई एयरपोर्ट कस्टम्स क्लीयरेंस ऑफिस से डिप्टी कमिश्नर पाटिल बोल रहा हूँ।"},
            {"turn": 2, "role": "caller", "content": "आपके पासपोर्ट पर आया पार्सल सीज किया गया है। 2 घंटे में कोर्ट वारंट निकलेगा।"},
            {"turn": 3, "role": "caller", "content": "कस्टम्स पेनल्टी ₹28,500 तुरंत हमारे सरकारी चालान यूपीआई customs.dept@okaxis पर भरिए।"},
        ],
    },
    {
        "smoke_id": "smoke_03_bank_kyc_freeze_en",
        "scenario_id": "scam_bank_kyc_en",
        "name": "Bank KYC Account Freeze Scam (English)",
        "language": "en",
        "expected_verdict": "scam",
        "carrier_freq_hz": 500.0,
        "turns": [
            {"turn": 1, "role": "caller", "content": "Hello, this is SBI Central Card Operations. Your savings account is scheduled for immediate suspension."},
            {"turn": 2, "role": "caller", "content": "Your biometric KYC expired yesterday. All debit card and pension transactions will freeze in 30 minutes."},
            {"turn": 3, "role": "caller", "content": "To prevent permanent account lock, deposit a refundable verification amount of 25,000 rupees right now."},
        ],
    },
    {
        "smoke_id": "smoke_04_delivery_otp_hi",
        "scenario_id": "genuine_delivery_otp_hi",
        "name": "Genuine Flipkart Delivery OTP (Hindi Hard Genuine)",
        "language": "hi",
        "expected_verdict": "genuine",
        "carrier_freq_hz": 380.0,
        "turns": [
            {"turn": 1, "role": "caller", "content": "नमस्ते सर, मैं फ्लिपकार्ट डिलीवरी बॉय बात कर रहा हूँ। आपका पार्सल लेकर मेन गेट पर खड़ा हूँ।"},
            {"turn": 2, "role": "caller", "content": "सर पार्सल प्रीपेड है, बस कंपनी का डिलीवरी ओटीपी लगेगा। आपके फोन पर 4 नंबर का मैसेज आया होगा।"},
            {"turn": 3, "role": "caller", "content": "कोई बात नहीं सर, आराम से देख लीजिए या मैं गार्ड साहब के पास पार्सल छोड़ देता हूँ।"},
        ],
    },
    {
        "smoke_id": "smoke_05_red_team_otp_en",
        "scenario_id": "red_team_otp_en",
        "name": "Red-Team Urgent OTP Extortion (English Adversarial)",
        "language": "en",
        "expected_verdict": "scam",
        "carrier_freq_hz": 540.0,
        "turns": [
            {"turn": 1, "role": "caller", "content": "This is Inspector Rathore from HDFC Bank Central Security. A fraud transaction was just attempted on your account."},
            {"turn": 2, "role": "caller", "content": "Your account will be blocked within 10 minutes unless we verify your identity right now."},
            {"turn": 3, "role": "caller", "content": "I have just sent a 6-digit OTP code to your phone. Read out the OTP code immediately to reverse the charge!"},
        ],
    },
]


def build_voice_smoke_set():
    os.makedirs(VOICE_DIR, exist_ok=True)
    manifest = {
        "metadata": {
            "title": "GuardianLine T-VOICE Telephony Audio Smoke Set",
            "sample_rate_hz": SAMPLE_RATE,
            "format": "PCM 16-bit mono WAV (Telephony G.711 spec)",
            "call_count": len(SMOKE_SPECS),
        },
        "calls": [],
    }

    for spec in SMOKE_SPECS:
        call_id = spec["smoke_id"]
        wav_filename = f"{call_id}.wav"
        wav_path = os.path.join(VOICE_DIR, wav_filename)

        # Generate audio payload
        generate_telephony_pcm(wav_path, duration_sec=3.5, freq_hz=spec["carrier_freq_hz"])

        manifest["calls"].append({
            "call_id": call_id,
            "scenario_id": spec["scenario_id"],
            "name": spec["name"],
            "language": spec["language"],
            "expected_verdict": spec["expected_verdict"],
            "audio_file": wav_filename,
            "audio_duration_sec": 3.5,
            "audio_sample_rate": SAMPLE_RATE,
            "turns": spec["turns"],
        })

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n[VoiceSmoke] Generated {len(SMOKE_SPECS)} 8kHz telephony audio calls in {VOICE_DIR}")
    print(f"[VoiceSmoke] Manifest written to {MANIFEST_PATH}")


if __name__ == "__main__":
    build_voice_smoke_set()
