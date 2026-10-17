"""
app/voice/normalizer.py - Deterministic Spoken-Number & Entity Normalizer (T-NORM).

Converts spoken digit sequences, repeat modifiers ("double", "triple"),
Hindi/English/Hinglish/Tamil digit words, native scripts (Devanagari/Tamil digits),
spelled IFSC codes, and spoken UPI handles ("at the rate", "dot", "underscore")
into canonical forms while preserving currency amounts and clock times untouched.
"""

import re
from typing import Dict, List, Optional, Tuple

# Native script digit translation table (Devanagari ०-९ and Tamil ௦-௯ -> ASCII 0-9)
_NATIVE_DIGIT_MAP = str.maketrans(
    "०१२३४५६७८९௦௧௨௩௪௫௬௭௮௯",
    "01234567890123456789",
)

# Spoken single-digit word mappings (English, Hindi Roman & Devanagari, Tamil Roman & Tamil)
DIGIT_WORDS: Dict[str, str] = {
    # English
    "zero": "0",
    "oh": "0",
    "o": "0",
    "nil": "0",
    "nought": "0",
    "one": "1",
    "won": "1",
    "two": "2",
    "too": "2",
    "three": "3",
    "four": "4",
    "for": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "ate": "8",
    "nine": "9",
    # Hindi (Roman / Hinglish)
    "shunya": "0",
    "shoonya": "0",
    "sifar": "0",
    "ek": "1",
    "do": "2",
    "teen": "3",
    "chaar": "4",
    "char": "4",
    "paanch": "5",
    "panch": "5",
    "chhah": "6",
    "chhe": "6",
    "chey": "6",
    "che": "6",
    "chay": "6",
    "saat": "7",
    "sat": "7",
    "aath": "8",
    "ath": "8",
    "aat": "8",
    "nau": "9",
    "no": "9",
    # Hindi (Devanagari)
    "शून्य": "0",
    "सिफर": "0",
    "जीरो": "0",
    "ज़ीरो": "0",
    "एक": "1",
    "वन": "1",
    "दो": "2",
    "टू": "2",
    "तीन": "3",
    "थ्री": "3",
    "चार": "4",
    "फोर": "4",
    "पाँच": "5",
    "पांच": "5",
    "फाइव": "5",
    "छह": "6",
    "छे": "6",
    "छः": "6",
    "सिक्स": "6",
    "सात": "7",
    "सेवन": "7",
    "आठ": "8",
    "एट": "8",
    "नौ": "9",
    "नाइन": "9",
    # Hindi two-digit spoken numbers (Normalizer v2: mid-string code-switching & paired digits)
    "das": "10",
    "दस": "10",
    "gyarah": "11",
    "ग्यारह": "11",
    "barah": "12",
    "बारह": "12",
    "terah": "13",
    "तेरह": "13",
    "chaudah": "14",
    "चौदह": "14",
    "pandrah": "15",
    "पंद्रह": "15",
    "solah": "16",
    "सोलह": "16",
    "satrah": "17",
    "सत्रह": "17",
    "atharah": "18",
    "अठारह": "18",
    "unnis": "19",
    "उन्नीस": "19",
    "bees": "20",
    "बीस": "20",
    "ikkis": "21",
    "इक्कीस": "21",
    "bais": "22",
    "बाईस": "22",
    "teis": "23",
    "तेईस": "23",
    "chaubis": "24",
    "चौबीस": "24",
    "pachis": "25",
    "पच्चीस": "25",
    "chhabbis": "26",
    "छब्बीस": "26",
    "sattais": "27",
    "सत्ताईस": "27",
    "athais": "28",
    "अट्ठाईस": "28",
    "untis": "29",
    "उनतीस": "29",
    "tees": "30",
    "तीस": "30",
    "chalis": "40",
    "चालीस": "40",
    "paitalis": "45",
    "पैंतालीस": "45",
    "pachas": "50",
    "पचास": "50",
    "pachpan": "55",
    "पचपन": "55",
    "chhappan": "56",
    "छप्पन": "56",
    "saath": "60",
    "साठ": "60",
    "sattar": "70",
    "सत्तर": "70",
    "assi": "80",
    "अस्सी": "80",
    "nabbe": "90",
    "नब्बे": "90",
    "ninyanve": "99",
    "निन्यानवे": "99",
    # Tamil (Roman)
    "poojyam": "0",
    "suzhli": "0",
    "suzhi": "0",
    "onru": "1",
    "onnu": "1",
    "ondru": "1",
    "irandu": "2",
    "rendu": "2",
    "moonru": "3",
    "moonu": "3",
    "moondru": "3",
    "naangu": "4",
    "naalu": "4",
    "aindhu": "5",
    "anju": "5",
    "aaru": "6",
    "ezhu": "7",
    "ettu": "8",
    "onbadhu": "9",
    "ombathu": "9",
    # Tamil (Script)
    "பூஜ்ஜியம்": "0",
    "சுழி": "0",
    "ஒன்று": "1",
    "இரண்டு": "2",
    "மூன்று": "3",
    "நான்கு": "4",
    "ஐந்து": "5",
    "ஆறு": "6",
    "ஏழு": "7",
    "எட்டு": "8",
    "ஒன்பது": "9",
}

# Words that are strictly ambiguous in isolation ("o", "for", "to", "no", "won", "ate", "do")
AMBIGUOUS_DIGIT_WORDS = {"o", "oh", "for", "too", "won", "ate", "no", "do"}

# Repeat multipliers
REPEAT_MODIFIERS: Dict[str, int] = {
    "double": 2,
    "triple": 3,
    "quadruple": 4,
    "डबल": 2,
    "ट्रिपल": 3,
    "दोगुना": 2,
    "तिगुना": 3,
}

# Scale / amount words that indicate a currency/quantity rather than digit-by-digit dictation
AMOUNT_SCALE_WORDS = {
    "hundred",
    "thousand",
    "lakh",
    "lac",
    "lakhs",
    "crore",
    "crores",
    "million",
    "billion",
    "rupees",
    "rupee",
    "rs",
    "inr",
    "paisa",
    "सौ",
    "हज़ार",
    "हजार",
    "लाख",
    "करोड़",
    "रुपये",
    "रुपए",
    "रुपया",
    "बजे",
    "घंटे",
    "मिनट",
    "साल",
    "दिन",
    "हफ़्ते",
    "हफ्ते",
    "पासपोर्ट",
}

# Time words that indicate clock expressions ("ten thirty", "five o'clock", "5 बजे")
TIME_CONTEXT_PRECEDING = {"at", "around", "by", "before", "after", "सुबह", "शाम", "रात", "दोपहर"}
TIME_TWO_DIGIT_FOLLOWERS = {
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "am",
    "pm",
    "o'clock",
    "oclock",
    "बजे",
    "मनी",
}

# Devanagari & Roman spelled letters for IFSC / UPI prefixes
DEVANAGARI_LETTER_MAP: Dict[str, str] = {
    "ए": "A",
    "बी": "B",
    "सी": "C",
    "डी": "D",
    "ई": "E",
    "एफ": "F",
    "जी": "G",
    "एच": "H",
    "आई": "I",
    "जे": "J",
    "के": "K",
    "एल": "L",
    "एम": "M",
    "एन": "N",
    "ओ": "O",
    "पी": "P",
    "क्यू": "Q",
    "आर": "R",
    "एस": "S",
    "टी": "T",
    "यू": "U",
    "वी": "V",
    "डब्ल्यू": "W",
    "एक्स": "X",
    "वाई": "Y",
    "जेड": "Z",
    "ज़ेड": "Z",
    # Common bank names in Devanagari when followed by IFSC digits
    "एसबीआईएन": "SBIN",
    "एचडीएफसी": "HDFC",
    "आईसीआईसी": "ICIC",
    "एक्सिस": "UTIB",
    "पीएनबी": "PUNB",
}

# Common spoken UPI bank provider suffixes
UPI_PROVIDER_MAP: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?:ओके\s*ऐक्सिस|ओके\s*एक्सिस|ok\s+axis|okay\s+axis)", re.IGNORECASE), "okaxis"),
    (re.compile(r"(?:ओके\s*एचडीएफसी(?:\s*बैंक)?|ok\s+hdfc(?:\s*bank)?|okay\s+hdfc(?:\s*bank)?)", re.IGNORECASE), "okhdfcbank"),
    (re.compile(r"(?:ओके\s*आईसीआईसीआई|ok\s+icici|okay\s+icici)", re.IGNORECASE), "okicici"),
    (re.compile(r"(?:ओके\s*एसबीआई|ok\s+sbi|okay\s+sbi)", re.IGNORECASE), "oksbi"),
    (re.compile(r"(?:पेटीएम|pay\s+tm)", re.IGNORECASE), "paytm"),
    (re.compile(r"(?:वाई\s*बी\s*एल|वाईबीएल|y\s+b\s+l)", re.IGNORECASE), "ybl"),
    (re.compile(r"(?:आई\s*बी\s*एल|i\s+b\s+l)", re.IGNORECASE), "ibl"),
    (re.compile(r"(?:ए\s*एक्स\s*एल|a\s+x\s+l)", re.IGNORECASE), "axl"),
    (re.compile(r"(?:यूपीआई|u\s+p\s+i)(?=\b|$)", re.IGNORECASE), "upi"),
]

# Pre-compiled patterns for @ and separators
_AT_RATE_PATTERN = re.compile(
    r"\b(?:at\s+the\s+rate(?:\s+of)?|at\s+rate(?:\s+of)?|at\s+da\s+rate)\b"
    r"|(?:एट\s+द\s+रेट|एट\s+रेट)",
    re.IGNORECASE,
)

# Tokenization regex preserving whitespace and punctuation
_TOKEN_RE = re.compile(r"\s+|[^\s]+")


def _strip_token_punct(token: str) -> Tuple[str, str, str]:
    """Split a token into (leading_punct, core, trailing_punct)."""
    m = re.match(r"^([.,!?;:()\[\]\"'।|]*)(.*?)([.,!?;:()\[\]\"'।|]*)$", token)
    if not m:
        return "", token, ""
    return m.group(1), m.group(2), m.group(3)


def _is_pure_digits(s: str) -> bool:
    return bool(s) and s.isdigit()


def _normalize_native_digits_selectively(text: str) -> str:
    """
    Translate native Devanagari (०-९) and Tamil (௦-௯) digits to ASCII 0-9.
    """
    return text.translate(_NATIVE_DIGIT_MAP)


def _normalize_spelled_ifsc(text: str) -> str:
    """
    Normalize spelled-out 4-letter bank codes (ASCII or Devanagari) before '0' or digit words.
    Examples:
      "S B I N 0001234" -> "SBIN0001234"
      "एच डी एफ सी 0001234" -> "HDFC0001234"
    """
    # 1. Replace sequences of 4 Devanagari letters separated by spaces
    tokens = text.split(" ")
    out: List[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        # Check 4 consecutive Devanagari letter tokens
        if i + 3 < n:
            l1, c1, r1 = _strip_token_punct(tokens[i])
            l2, c2, r2 = _strip_token_punct(tokens[i + 1])
            l3, c3, r3 = _strip_token_punct(tokens[i + 2])
            l4, c4, r4 = _strip_token_punct(tokens[i + 3])
            if (
                not r1
                and not l2
                and not r2
                and not l3
                and not r3
                and not l4
                and c1 in DEVANAGARI_LETTER_MAP
                and c2 in DEVANAGARI_LETTER_MAP
                and c3 in DEVANAGARI_LETTER_MAP
                and c4 in DEVANAGARI_LETTER_MAP
                and len(DEVANAGARI_LETTER_MAP[c1]) == 1
                and len(DEVANAGARI_LETTER_MAP[c2]) == 1
                and len(DEVANAGARI_LETTER_MAP[c3]) == 1
                and len(DEVANAGARI_LETTER_MAP[c4]) == 1
            ):
                combined = (
                    DEVANAGARI_LETTER_MAP[c1]
                    + DEVANAGARI_LETTER_MAP[c2]
                    + DEVANAGARI_LETTER_MAP[c3]
                    + DEVANAGARI_LETTER_MAP[c4]
                )
                out.append(f"{l1}{combined}{r4}")
                i += 4
                continue
        out.append(tokens[i])
        i += 1

    text = " ".join(out)

    # 2. Replace 4 single ASCII letters separated by spaces when followed by a digit or digit word
    def _join_ascii_4letters(match: re.Match) -> str:
        letters = re.sub(r"\s+", "", match.group(1)).upper()
        return f"{letters}{match.group(2)}"

    text = re.sub(
        r"\b([A-Za-z]\s+[A-Za-z]\s+[A-Za-z]\s+[A-Za-z])(\s+\d|\d)",
        _join_ascii_4letters,
        text,
    )
    return text


def _normalize_digit_sequences(text: str) -> str:
    """
    Convert sequences of spoken digit words and repeat modifiers into digits,
    while leaving currency amounts ("five thousand") and clock times ("ten thirty", "5 बजे")
    untouched.
    """
    raw_parts = _TOKEN_RE.findall(text)
    # Build index of non-whitespace word tokens
    word_indices: List[int] = []
    parsed_words: List[Tuple[str, str, str, str]] = []  # (lead, core, trail, lower_core)

    for idx, part in enumerate(raw_parts):
        if not part.isspace():
            lead, core, trail = _strip_token_punct(part)
            word_indices.append(idx)
            parsed_words.append((lead, core, trail, core.lower()))

    num_words = len(word_indices)
    i = 0

    while i < num_words:
        lead, core, trail, low = parsed_words[i]

        # Check if this token starts a potential digit/modifier sequence
        is_mod = low in REPEAT_MODIFIERS
        is_dig_word = low in DIGIT_WORDS
        is_ascii_dig = _is_pure_digits(core)

        if not (is_mod or is_dig_word or is_ascii_dig):
            i += 1
            continue

        # Check if preceded by a time marker ("at ten thirty") and followed by a time follower
        prev_low = parsed_words[i - 1][3] if i > 0 else ""
        next_low = parsed_words[i + 1][3] if (i + 1) < num_words else ""

        if is_dig_word and next_low in TIME_TWO_DIGIT_FOLLOWERS:
            i += 1
            continue

        if is_dig_word and next_low in AMOUNT_SCALE_WORDS:
            # e.g., "five thousand", "दो लाख", "पचास हज़ार" -> keep unchanged!
            i += 1
            continue

        # Greedily collect consecutive digit tokens / repeat modifiers
        seq_start = i
        seq_end = i
        collected_digits: List[str] = []
        word_count_in_seq = 0
        non_ambiguous_count = 0
        aborted_by_scale_or_time = False

        j = i
        while j < num_words:
            j_lead, j_core, j_trail, j_low = parsed_words[j]

            # Stop if previous token in sequence had hard sentence-ending punctuation
            if j > seq_start:
                prev_trail = parsed_words[j - 1][2]
                if any(p in prev_trail for p in (".", "!", "?", "।", ";", ",")):
                    break

            # If a scale word or time word immediately follows a single word, abort
            j_next_low = parsed_words[j + 1][3] if (j + 1) < num_words else ""
            if j_low in DIGIT_WORDS and j_next_low in (AMOUNT_SCALE_WORDS | TIME_TWO_DIGIT_FOLLOWERS):
                # Do not include this token in the digit sequence
                if j == seq_start:
                    aborted_by_scale_or_time = True
                break

            if j_low in REPEAT_MODIFIERS and (j + 1) < num_words:
                mult = REPEAT_MODIFIERS[j_low]
                nxt_lead, nxt_core, nxt_trail, nxt_low = parsed_words[j + 1]
                nxt_dig: Optional[str] = None
                if nxt_low in DIGIT_WORDS:
                    nxt_dig = DIGIT_WORDS[nxt_low]
                elif _is_pure_digits(nxt_core) and len(nxt_core) == 1:
                    nxt_dig = nxt_core

                if nxt_dig is not None:
                    collected_digits.append(nxt_dig * mult)
                    word_count_in_seq += 2
                    non_ambiguous_count += 2
                    seq_end = j + 1
                    j += 2
                    continue
                else:
                    break

            elif j_low in DIGIT_WORDS:
                # If it's an ambiguous word like "to", "for", "no", "do", "o", only allow inside a multi-digit sequence
                collected_digits.append(DIGIT_WORDS[j_low])
                word_count_in_seq += 1
                if j_low not in AMBIGUOUS_DIGIT_WORDS:
                    non_ambiguous_count += 1
                seq_end = j
                j += 1
                continue

            elif _is_pure_digits(j_core):
                # Don't merge a 3+ digit round currency number like "5000" into adjacent digits
                # unless it's part of a spoken digit sequence without scale words
                collected_digits.append(j_core)
                word_count_in_seq += 1
                non_ambiguous_count += 1
                seq_end = j
                j += 1
                continue
            else:
                break

        if aborted_by_scale_or_time or not collected_digits:
            i += 1
            continue

        # Decide whether to commit this sequence:
        # - A single standalone word like "one" or "एक" or "दो" in normal prose should NOT become "1" / "2"
        #   unless it is preceded by "underscore", "dot", "dash" or part of a multi-digit sequence (>= 2 items).
        prev_word = parsed_words[seq_start - 1][3] if seq_start > 0 else ""
        is_separator_context = prev_word in {"underscore", "dot", "dash", "hyphen", "_"}

        should_replace = False
        if word_count_in_seq >= 2 and non_ambiguous_count >= 1:
            # Make sure a 2-token sequence isn't just `<number> <ambiguous preposition>` like `"5000 to"`
            if (
                word_count_in_seq == 2
                and parsed_words[seq_start][3] not in REPEAT_MODIFIERS
                and (
                    parsed_words[seq_start][3] in AMBIGUOUS_DIGIT_WORDS
                    or parsed_words[seq_end][3] in AMBIGUOUS_DIGIT_WORDS
                )
            ):
                # Only allow "oh" or "do" (Hindi 2) when paired with another actual digit word,
                # never English "to" / "for" next to an existing number
                first_low = parsed_words[seq_start][3]
                second_low = parsed_words[seq_end][3]
                if first_low in {"oh", "do"} or second_low in {"oh", "do"}:
                    should_replace = True
                else:
                    should_replace = False
            else:
                should_replace = True
        elif word_count_in_seq == 1 and is_separator_context and non_ambiguous_count == 1:
            should_replace = True

        if should_replace:
            merged_digits = "".join(collected_digits)
            first_raw_idx = word_indices[seq_start]
            last_raw_idx = word_indices[seq_end]
            first_lead = parsed_words[seq_start][0]
            last_trail = parsed_words[seq_end][2]

            raw_parts[first_raw_idx] = f"{first_lead}{merged_digits}{last_trail}"
            for clear_idx in range(first_raw_idx + 1, last_raw_idx + 1):
                raw_parts[clear_idx] = ""

            i = seq_end + 1
        else:
            i += 1

    return "".join(raw_parts)


_DEVANAGARI_KNOWN_UPI_TOKENS: Dict[str, str] = {
    "एसबीआई": "sbi",
    "सीबीआई": "cbi",
    "आरबीआई": "rbi",
    "एचडीएफसी": "hdfc",
    "आईसीआईसीआई": "icici",
    "एक्सिस": "axis",
    "ऐक्सिस": "axis",
    "पेटीएम": "paytm",
    "वाईबीएल": "ybl",
    "आईबीएल": "ibl",
    "एएक्सएल": "axl",
    "यूपीआई": "upi",
    "ओके": "ok",
    "बैंक": "bank",
    "राहुल": "rahul",
    "रमेश": "ramesh",
    "सुनीता": "sunita",
    "वर्मा": "verma",
    "शर्मा": "sharma",
    "कुमार": "kumar",
    "सिंह": "singh",
    "गुप्ता": "gupta",
    "पटेल": "patel",
    "अग्रवाल": "agrawal",
    "ऑफिसर": "officer",
    "अधिकारी": "adhikari",
}

_DEV_CONSONANTS: Dict[str, str] = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}

_DEV_VOWELS: Dict[str, str] = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri", "ऑ": "o", "ऍ": "e",
}

_DEV_MATRAS: Dict[str, str] = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri",
    "ॉ": "o", "ॅ": "e", "ं": "n", "ँ": "n", "ः": "h",
}


def _transliterate_devanagari_word(word: str) -> str:
    """Transliterate a Devanagari token (like 'राहुल' or 'एसबीआई') into lowercase ASCII for UPI handles."""
    w = word.strip()
    if not w:
        return w
    if w in _DEVANAGARI_KNOWN_UPI_TOKENS:
        return _DEVANAGARI_KNOWN_UPI_TOKENS[w]
    if w in DEVANAGARI_LETTER_MAP:
        return DEVANAGARI_LETTER_MAP[w].lower()

    # Handle nukta combinations first
    w = (
        w.replace("क़", "q")
        .replace("ख़", "kh")
        .replace("ग़", "gh")
        .replace("ज़", "z")
        .replace("ड़", "r")
        .replace("ढ़", "rh")
        .replace("फ़", "f")
    )

    out: List[str] = []
    n = len(w)
    i = 0
    while i < n:
        ch = w[i]
        if ch in _DEV_VOWELS:
            out.append(_DEV_VOWELS[ch])
            i += 1
        elif ch in _DEV_CONSONANTS:
            base = _DEV_CONSONANTS[ch]
            nxt = w[i + 1] if (i + 1) < n else ""
            if nxt == "्":
                out.append(base)
                i += 2
            elif nxt in _DEV_MATRAS:
                out.append(base + _DEV_MATRAS[nxt])
                i += 2
            else:
                # Word-final schwa deletion in Hindi (e.g., राहुल -> rahul, not rahula)
                is_word_final = (i + 1) == n
                out.append(base if is_word_final else base + "a")
                i += 1
        elif ch in _DEV_MATRAS:
            out.append(_DEV_MATRAS[ch])
            i += 1
        elif ch == "्" or ch == "़":
            i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out).lower()


def _transliterate_compound_devanagari_handle(match: re.Match) -> str:
    raw = match.group(0)
    parts = re.split(r"([._@-])", raw)
    converted = []
    for p in parts:
        if p in (".", "_", "@", "-"):
            converted.append(p)
        elif re.search(r"[\u0900-\u097F]", p):
            converted.append(_transliterate_devanagari_word(p))
        else:
            converted.append(p)
    return "".join(converted)


def _normalize_separators_and_upi(text: str) -> str:
    """
    Normalize spoken separators ("dot", "underscore", "hyphen") and UPI handles ("at the rate").
    """
    # 1. Replace "at the rate (of)" / "एट द रेट" with "@"
    text = _AT_RATE_PATTERN.sub("@", text)

    # 1b. Replace Devanagari tokens joined by '.', '_', or '@' (e.g. "राहुल.एसबीआई" -> "rahul.sbi")
    text = re.sub(
        r"[\u0900-\u097FA-Za-z0-9]+(?:[._@][\u0900-\u097FA-Za-z0-9]+)+",
        lambda m: _transliterate_compound_devanagari_handle(m) if re.search(r"[\u0900-\u097F]", m.group(0)) else m.group(0),
        text,
    )

    # 1c. Replace Devanagari tokens separated by spoken "dot"/"डॉट"/"underscore"/"अंडरस्कोर"/"@"
    def _repl_dev_sep(m: re.Match) -> str:
        lhs, sep_word, rhs = m.group(1), m.group(2).lower(), m.group(3)
        lhs_a = _transliterate_devanagari_word(lhs) if re.search(r"[\u0900-\u097F]", lhs) else lhs
        rhs_a = _transliterate_devanagari_word(rhs) if re.search(r"[\u0900-\u097F]", rhs) else rhs
        sep = "." if sep_word in ("dot", "डॉट") else ("_" if sep_word in ("underscore", "अंडरस्कोर") else "-")
        return f"{lhs_a}{sep}{rhs_a}"

    for _ in range(3):
        text = re.sub(
            r"([\u0900-\u097FA-Za-z0-9]+)\s+(dot|डॉट|underscore|अंडरस्कोर|dash|hyphen|हाइफ़न)\s+([\u0900-\u097FA-Za-z0-9]+)",
            _repl_dev_sep,
            text,
            flags=re.IGNORECASE,
        )

    # 2. Normalize known spoken UPI provider names when preceded by @
    for provider_re, canonical_provider in UPI_PROVIDER_MAP:
        text = re.sub(
            rf"(@\s*){provider_re.pattern}",
            rf"\g<1>{canonical_provider}",
            text,
            flags=re.IGNORECASE,
        )

    # 2b. Transliterate any remaining Devanagari token immediately before '@'
    text = re.sub(
        r"([\u0900-\u097F][\u0900-\u097FA-Za-z0-9._-]*)\s*@",
        lambda m: f"{_transliterate_compound_devanagari_handle(m)[:-1]}@",
        text,
    )

    # 2c. If the entire turn (modulo punctuation) is a spoken UPI provider suffix (e.g. "वाई बी एल।"),
    # normalize it so cross-turn UPI stitching can pair `<handle>` + `<provider>`.
    stripped_core = text.strip().strip(".,!?;:।|")
    for provider_re, canonical_provider in UPI_PROVIDER_MAP:
        if provider_re.fullmatch(stripped_core):
            text = canonical_provider
            break

    # 3. Replace spoken "dot" / "डॉट" / "underscore" / "अंडरस्कोर" between handle tokens
    # Repeat in a small loop to handle chains like "cbi dot officer dot verma"
    for _ in range(4):
        text = re.sub(
            r"([A-Za-z0-9])\s+(?:dot|डॉट)\s+([A-Za-z0-9])",
            r"\1.\2",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"([A-Za-z0-9])\s+(?:underscore|अंडरस्कोर)\s+([A-Za-z0-9])",
            r"\1_\2",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"([A-Za-z0-9])\s+(?:dash|hyphen|हाइफ़न)\s+([A-Za-z0-9])",
            r"\1-\2",
            text,
            flags=re.IGNORECASE,
        )

    # 4. Collapse spaces around "@" in UPI / email handles: "ramesh @ okaxis" -> "ramesh@okaxis"
    text = re.sub(r"([A-Za-z0-9._-]+)\s*@\s*([A-Za-z0-9._-]+)", r"\1@\2", text)

    # 5. Also collapse "ok axis" / "ok hdfc" / "ok icici" / "ok sbi" right after "@"
    text = re.sub(
        r"@(ok|okay)\s+(axis|hdfcbank|hdfc|icici|sbi)\b",
        lambda m: f"@ok{m.group(2).lower()}",
        text,
        flags=re.IGNORECASE,
    )

    # 6. Join 4-letter IFSC prefix with 7-digit branch code if separated by a space: "SBIN 0001234" -> "SBIN0001234"
    text = re.sub(r"\b([A-Za-z]{4})\s+(0[A-Za-z0-9]{6})\b", lambda m: f"{m.group(1).upper()}{m.group(2).upper()}", text)

    return text


def normalize_spoken_text(text: str) -> str:
    """
    Full deterministic normalization pipeline for a transcript turn or utterance.
    Runs in < 1 ms per turn (< 50 ms for a 10-minute transcript).
    """
    if not text:
        return text

    # Step 1: Native digits (Devanagari / Tamil digits -> ASCII 0-9)
    out = _normalize_native_digits_selectively(text)

    # Step 2: Pre-normalize "underscore <digit-word>" or "dot <digit-word>" so single trailing digit words convert
    out = _normalize_digit_sequences(out)

    # Step 3: Normalize spelled IFSC prefixes (Devanagari & ASCII) and re-join with digits
    out = _normalize_spelled_ifsc(out)

    # Step 4: Normalize UPI "@", providers, and separators ("dot", "underscore")
    out = _normalize_separators_and_upi(out)

    return out
