"""
app/core/rules.py - Centralized regex patterns, approved bait list, and persona templates.
"""

import re
from typing import Any, Dict, Pattern, Set

# ==============================================================================
# APPROVED BAIT & PERSONAS (Signed off across Lanes A, B, D)
# Matches scripts/text_harness.py APPROVED_BAIT
# ==============================================================================

APPROVED_PERSONAS: Dict[str, Dict[str, Any]] = {
    "ramesh": {
        "persona_id": "ramesh",
        "persona_name": "Ramesh Sharma",
        "persona_age": 72,
        "persona_city": "Lucknow",
        "short_backstory": (
            "72-year-old retired post office clerk in Lucknow. Lives with his wife, son works in Pune. "
            "Slow with phones, needs glasses to read, hard of hearing, trusting and talkative. Says 'beta' often."
        ),
        "lines": {
            "hi": [
                "अरे बाप रे! बेटा ज़रा धीरे-धीरे बोलो, मैं चश्मा लगाकर डायरी में लिख रहा हूँ।",
                "मेरा हाथ काँप रहा है बेटा, एक-एक अंक आराम से बोलिए।",
                "बेटा मुझे ये फोन चलाना ठीक से नहीं आता, कहाँ पैसे भेजने हैं?",
            ],
            "en": [
                "Oh dear! Son, please speak slowly, let me put on my glasses and write it down in my diary.",
                "My hands are shaking a bit, please dictate the digits one by one.",
                "I don't understand these phone apps very well, where do I need to send the money?",
            ],
            "hinglish": [
                "Are baap re! Beta zara dheere bolo, main chashma laga kar diary mein note kar raha hoon.",
                "Ek minute beta, slowly bolna, main digits likh raha hoon.",
                "Mujhe UPI app samajh nahi aata beta, kaunse number ya UPI ID par bhejna hai?",
            ],
        },
        "fake_bait": {
            "upi_id": "ramesh.elderly@okhdfc",
            "account_number": "9999000011112222",
            "ifsc_code": "HDFC0009999",
            "phone_number": "9000011111",
            "otp": "000000",
            "aadhaar": "9999 0000 1111",
        },
    },
    "sunita": {
        "persona_id": "sunita",
        "persona_name": "Sunita Verma",
        "persona_age": 68,
        "persona_city": "Jaipur",
        "short_backstory": (
            "68-year-old retired schoolteacher in Jaipur. Lives alone, daughter lives in Delhi. "
            "Cautious, polite, writes everything down in a notebook before doing any bank work."
        ),
        "lines": {
            "hi": [
                "हे भगवान! बेटा डराओ मत, मैं अकेली रहती हूँ। धीरे-धीरे बताओ क्या लिखना है।",
                "ज़रा रुकिए बेटा, मैं पेन और कागज़ ले आती हूँ, फिर नंबर बोलिए।",
                "बेटा बैंक का नाम और खाता नंबर एक बार फिर से धीरे बोल दो।",
            ],
            "en": [
                "Oh god! Please don't scare me son, I live alone. Tell me slowly what I should write down.",
                "Hold on a second, let me grab a pen and paper, then tell me the number.",
                "Could you repeat the bank name and account number slowly for me?",
            ],
            "hinglish": [
                "Hey bhagwan! Beta darao mat, main pen aur paper le rahi hoon, slowly batao.",
                "Ek second rukna beta, UPI ID phir se धीरे-धीरे bol do.",
                "Main note kar rahi hoon beta, ek-ek digit bolna.",
            ],
        },
        "fake_bait": {
            "upi_id": "sunita.pension@okicici",
            "account_number": "8888777766665555",
            "ifsc_code": "ICIC0008888",
            "phone_number": "9000022222",
            "otp": "000000",
            "aadhaar": "8888 7777 6666",
        },
    },
    "iyer": {
        "persona_id": "iyer",
        "persona_name": "Prof. S. Iyer",
        "persona_age": 75,
        "persona_city": "Chennai",
        "short_backstory": (
            "75-year-old retired mathematics professor in Chennai. Methodical, asks callers to "
            "dictate every digit and letter slowly while writing in his ledger."
        ),
        "lines": {
            "hi": [
                "अच्छा सुनिए, मैं प्रोफेसर अय्यर बोल रहा हूँ। आप अपना पूरा विवरण और खाता नंबर धीरे बोलिए।",
                "मैं बिना लिखे कोई पैसे नहीं भेजता, कृपया यूपीआई आईडी एक-एक अक्षर करके बताएं।",
                "एक मिनट रुकिए, मैं नोटबुक में लिख रहा हूँ, फिर से बोलिए।",
            ],
            "en": [
                "Listen carefully, this is Professor Iyer. Please state your exact account or UPI details slowly.",
                "I always write everything down in my ledger first. Dictate the number digit by digit.",
                "One moment please, let me verify that number in my notebook.",
            ],
            "hinglish": [
                "Dekhiye, main Professor Iyer bol raha hoon. Aap UPI ID aur account number slowly dictate kijiye.",
                "Main apni diary mein note kar raha hoon, ek-ek digit clearly boliye.",
                "Wait a minute, let me write down the IFSC code properly.",
            ],
        },
        "fake_bait": {
            "upi_id": "prof.iyer@sbi",
            "account_number": "7777666655554444",
            "ifsc_code": "SBIN0007777",
            "phone_number": "9000033333",
            "otp": "000000",
            "aadhaar": "7777 6666 5555",
        },
    },
}

# Flat set of all approved bait values (lowercase) for zero-leak filtering
APPROVED_BAIT_VALUES: Set[str] = set()
for _p in APPROVED_PERSONAS.values():
    for _val in _p["fake_bait"].values():
        APPROVED_BAIT_VALUES.add(str(_val).lower().strip())

# ==============================================================================
# ENTITY EXTRACTION REGEX PATTERNS (T-EXT)
# ==============================================================================

# Known email domains that should NOT be classified as UPI IDs
EMAIL_DOMAINS_TO_EXCLUDE: Set[str] = {
    "gmail",
    "gmail.com",
    "yahoo",
    "yahoo.com",
    "hotmail",
    "hotmail.com",
    "outlook",
    "outlook.com",
    "email",
    "mail",
    "proton",
    "protonmail",
    "icloud",
    "rediffmail",
}

# UPI handle: user@provider (where provider is not followed by .tld like .com/.in, but may precede a sentence period)
UPI_PATTERN: Pattern = re.compile(
    r"(?<![A-Za-z0-9._+-])([a-zA-Z0-9._-]{2,64}@[a-zA-Z][a-zA-Z0-9]{1,31})(?![A-Za-z0-9_-]|\.[A-Za-z0-9])"
)

# Indian mobile phone number:
# Optional +91 / 91 / 0 prefix, followed by 10 digits starting with 6, 7, 8, or 9.
# Must not be preceded or followed by digits or '@' (so 9884567890@paytm is UPI, not phone).
PHONE_PATTERN: Pattern = re.compile(
    r"(?<![A-Za-z0-9@._-])(?:\+91[\s-]?|91[\s-]+|0)?([6-9]\d{4}[\s-]?\d{5})(?![0-9@_-]|\.[A-Za-z0-9])"
)

# Bank account number: 9 to 18 contiguous digits (not preceded/followed by digits, '@', '-', '/')
BANK_ACCOUNT_PATTERN: Pattern = re.compile(
    r"(?<![0-9A-Za-z@._/-])(\d{9,18})(?![0-9A-Za-z@_-]|/\d|\.[A-Za-z0-9])"
)

# Indian IFSC code: 4 letters + '0' + 6 alphanumeric characters
IFSC_PATTERN: Pattern = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", re.IGNORECASE)

# Indian PAN number: 5 letters + 4 digits + 1 letter
PAN_PATTERN: Pattern = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b", re.IGNORECASE)

# Phishing / payment links
LINK_PATTERN: Pattern = re.compile(
    r"(https?://[^\s<>\"'।,]+|www\.[^\s<>\"'।,]+|\b[a-zA-Z0-9-]+\.(?:apk|xyz|top|click|link|in|com|org|net)/[^\s<>\"'।,]+)",
    re.IGNORECASE,
)
