"""
app/core/rules.py - Centralized regex patterns, rotating 20-persona bait pool, and persona templates.
"""

import hashlib
import re
from typing import Any, Dict, List, Pattern, Set, Union


def verify_luhn(number_str: str) -> bool:
    """Return True if `number_str` is all digits and satisfies the Luhn checksum."""
    if not number_str or not number_str.isdigit():
        return False
    total = 0
    for idx, ch in enumerate(reversed(number_str)):
        d = ord(ch) - 48
        if idx % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ==============================================================================
# 20 ROTATING PERSONAS & REALISTIC LUHN-VALID BAIT POOL
# ==============================================================================

APPROVED_PERSONAS: Dict[str, Dict[str, Any]] = {
    "ramesh": {
        "persona_id": "ramesh",
        "persona_name": "Ramesh Sharma",
        "persona_age": 72,
        "persona_city": "Lucknow",
        "bank": "SBI",
        "short_backstory": (
            "72-year-old retired post office clerk in Lucknow with an SBI pension account. Lives with his wife, "
            "son works in Pune. Slow with phones, needs glasses to read, hard of hearing, trusting and talkative. Says 'beta' often."
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
            "upi_id": "rsharma72@oksbi",
            "account_number": "30984716255",
            "ifsc_code": "SBIN0000125",
            "phone_number": "9415023481",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "sunita": {
        "persona_id": "sunita",
        "persona_name": "Sunita Verma",
        "persona_age": 68,
        "persona_city": "Jaipur",
        "bank": "PNB",
        "short_backstory": (
            "68-year-old retired schoolteacher in Jaipur with a PNB account. Lives alone, daughter lives in Delhi. "
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
            "upi_id": "sverma68@pnb",
            "account_number": "0214000109482713",
            "ifsc_code": "PUNB0021400",
            "phone_number": "9829041726",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "iyer": {
        "persona_id": "iyer",
        "persona_name": "Prof. S. Iyer",
        "persona_age": 75,
        "persona_city": "Chennai",
        "bank": "Canara",
        "short_backstory": (
            "75-year-old retired mathematics professor in Chennai banking with Canara Bank. Methodical, asks callers to "
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
            "upi_id": "siyer75@cnrb",
            "account_number": "1234101048290",
            "ifsc_code": "CNRB0001234",
            "phone_number": "9444061829",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "deshmukh": {
        "persona_id": "deshmukh",
        "persona_name": "Vasant Deshmukh",
        "persona_age": 74,
        "persona_city": "Pune",
        "bank": "Bank of Maharashtra",
        "short_backstory": (
            "74-year-old retired irrigation department engineer in Pune with a Bank of Maharashtra pension account. "
            "Polite, hard of hearing in one ear, keeps his passbook in a steel cupboard."
        ),
        "lines": {
            "hi": [
                "बेटा ज़रा ऊँचा बोलो, मुझे एक कान से कम सुनाई देता है।",
                "रुकिए मैं अपनी पासबुक निकाल लेता हूँ, फिर खाता नंबर मिलाता हूँ।",
                "धीरे-धीरे बोलिए बेटा, मैं कागज़ पर लिख रहा हूँ।",
            ],
            "en": [
                "Please speak a bit louder son, I am hard of hearing in one ear.",
                "Hold on, let me take out my passbook and check the account details.",
                "Speak slowly please, I am noting it down on paper.",
            ],
            "hinglish": [
                "Beta thoda zor se bolo, main passbook nikaal kar note kar raha hoon.",
                "Ek minute rukna, main number diary mein likh raha hoon.",
                "Slowly boliye beta, kaunsa UPI handle bataya aapne?",
            ],
        },
        "fake_bait": {
            "upi_id": "vdeshmukh74@mahb",
            "account_number": "20048192734",
            "ifsc_code": "MAHB0000002",
            "phone_number": "9822034917",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "patel": {
        "persona_id": "patel",
        "persona_name": "Kantilal Patel",
        "persona_age": 71,
        "persona_city": "Vadodara",
        "bank": "Bank of Baroda",
        "short_backstory": (
            "71-year-old retired textile shop owner in Vadodara banking with Bank of Baroda. "
            "Worried about his fixed deposits, asks callers to repeat numbers twice."
        ),
        "lines": {
            "hi": [
                "अरे भाई, मेरा बैंक ऑफ बड़ौदा का खाता है, ज़रा धीरे बताइए क्या करना है।",
                "एक मिनट रुकिए, मैं चश्मा पहन लूँ फिर नंबर लिखता हूँ।",
                "कृपया एक-एक अंक साफ-साफ बोलिए।",
            ],
            "en": [
                "Oh brother, my account is with Bank of Baroda, tell me slowly what needs to be done.",
                "Wait a minute, let me put on my spectacles before writing the number.",
                "Please say each digit clearly one by one.",
            ],
            "hinglish": [
                "Are bhai, mera Bank of Baroda mein account hai, zara slowly batao.",
                "Ek second chashma pehen loon, phir UPI ID likhta hoon.",
                "Ek-ek digit clearly bolna beta.",
            ],
        },
        "fake_bait": {
            "upi_id": "kpatel71@barodampay",
            "account_number": "01290100048293",
            "ifsc_code": "BARB0VJBARO",
            "phone_number": "9824071638",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "chatterjee": {
        "persona_id": "chatterjee",
        "persona_name": "Subhash Chatterjee",
        "persona_age": 76,
        "persona_city": "Kolkata",
        "bank": "UCO Bank",
        "short_backstory": (
            "76-year-old retired railway audit clerk in Kolkata with a UCO Bank account. "
            "Fussy about details, insists on writing down the exact spelling and IFSC code."
        ),
        "lines": {
            "hi": [
                "सुनिए, मैं कोलकाता से सुभाष चटर्जी बोल रहा हूँ, ज़रा धीरे बोलिए।",
                "मैं अपनी डायरी में आपका यूपीआई और खाता नंबर नोट कर रहा हूँ।",
                "एक बार फिर से स्पेलिंग बता दीजिए।",
            ],
            "en": [
                "Listen, this is Subhash Chatterjee from Kolkata, please speak a bit slower.",
                "I am noting your UPI and account number in my pocket diary.",
                "Please repeat the exact spelling once more.",
            ],
            "hinglish": [
                "Suniye, main Subhash Chatterjee bol raha hoon, thoda slowly boliye.",
                "Main apni diary mein aapka UPI ID aur IFSC note kar raha hoon.",
                "Ek baar phir se spelling repeat kar dijiye.",
            ],
        },
        "fake_bait": {
            "upi_id": "schatterjee76@ybl",
            "account_number": "00020110048293",
            "ifsc_code": "UCBA0000002",
            "phone_number": "9830142869",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "kulkarni": {
        "persona_id": "kulkarni",
        "persona_name": "Meena Kulkarni",
        "persona_age": 67,
        "persona_city": "Nagpur",
        "bank": "Bank of India",
        "short_backstory": (
            "67-year-old retired librarian in Nagpur with a Bank of India savings account. "
            "Nervous around official calls, asks callers to hold while she finds her reading glasses."
        ),
        "lines": {
            "hi": [
                "अरे बेटा, मुझे बहुत घबराहट हो रही है, धीरे-धीरे बताओ।",
                "मैं पेन ढूँढ रही हूँ बेटा, एक मिनट लाइन पर रहना।",
                "खाता नंबर और यूपीआई आईडी एक बार फिर से बोल दो।",
            ],
            "en": [
                "Oh son, I am getting very anxious, please explain slowly.",
                "I am looking for my pen, please stay on the line for a minute.",
                "Please repeat the account number and UPI ID once again.",
            ],
            "hinglish": [
                "Are beta, mujhe ghabrahat ho rahi hai, zara dheere batao.",
                "Main pen dhoondh rahi hoon, ek minute hold karna.",
                "Account number aur UPI ID phir se bol do beta.",
            ],
        },
        "fake_bait": {
            "upi_id": "mkulkarni67@okhdfcbank",
            "account_number": "000110110004824",
            "ifsc_code": "BKID0000001",
            "phone_number": "9422183746",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "nair": {
        "persona_id": "nair",
        "persona_name": "Gopalan Nair",
        "persona_age": 73,
        "persona_city": "Kochi",
        "bank": "Federal Bank",
        "short_backstory": (
            "73-year-old retired customs superintendent in Kochi banking with Federal Bank. "
            "Calm, deliberate, writes every number in a bound register."
        ),
        "lines": {
            "hi": [
                "अच्छा भाई, मैं रजिस्टर में लिख रहा हूँ, नंबर धीरे-धीरे बोलिए।",
                "मेरा फेडरल बैंक का खाता है, आप अपना विवरण बताइए।",
                "एक मिनट रुकिए, मैं अंक मिला लेता हूँ।",
            ],
            "en": [
                "Alright, I am writing this in my register, please dictate the number slowly.",
                "My account is with Federal Bank, please give me your details.",
                "Wait a moment, let me cross-check the digits.",
            ],
            "hinglish": [
                "Achha bhai, main register mein note kar raha hoon, slowly boliye.",
                "Mera Federal Bank ka account hai, aap apna UPI detail bataiye.",
                "Ek minute rukiye, main digits check kar leta hoon.",
            ],
        },
        "fake_bait": {
            "upi_id": "gnair73@fbl",
            "account_number": "11010100293840",
            "ifsc_code": "FDRL0001101",
            "phone_number": "9447129384",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "reddy": {
        "persona_id": "reddy",
        "persona_name": "Venkat Reddy",
        "persona_age": 70,
        "persona_city": "Hyderabad",
        "bank": "Union Bank of India",
        "short_backstory": (
            "70-year-old retired agricultural officer in Hyderabad with a Union Bank of India account. "
            "Soft-spoken, unfamiliar with mobile banking apps."
        ),
        "lines": {
            "hi": [
                "बेटा मुझे मोबाइल बैंकिंग ठीक से समझ नहीं आती, धीरे बताइए।",
                "मैं डायरी में लिख रहा हूँ, एक-एक नंबर बोलिए।",
                "ज़रा रुकिए, चश्मा साफ कर लूँ।",
            ],
            "en": [
                "Son, I don't understand mobile banking very well, please guide me slowly.",
                "I am writing it in my diary, say the numbers one by one.",
                "Hold on a second, let me clean my glasses.",
            ],
            "hinglish": [
                "Beta mujhe mobile banking samajh nahi aati, slowly bataiye.",
                "Main diary mein likh raha hoon, ek-ek digit boliye.",
                "Zara rukiye, main chashma pehen leta hoon.",
            ],
        },
        "fake_bait": {
            "upi_id": "vreddy70@uboi",
            "account_number": "530702010048296",
            "ifsc_code": "UBIN0530786",
            "phone_number": "9849027364",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "singh": {
        "persona_id": "singh",
        "persona_name": "Harbhajan Singh",
        "persona_age": 77,
        "persona_city": "Chandigarh",
        "bank": "Punjab & Sind Bank",
        "short_backstory": (
            "77-year-old retired roadways depot manager in Chandigarh banking with Punjab & Sind Bank. "
            "Trusting, talks fondly about his grandchildren, writes numbers slowly."
        ),
        "lines": {
            "hi": [
                "पुत्तर ज़रा आराम से बोलो, मैं कागज़ पर नंबर लिख रहा हूँ।",
                "मेरा हाथ धीरे चलता है बेटा, एक-एक अक्षर बोलो।",
                "बैंक का आईएफएससी और यूपीआई फिर से बता दो।",
            ],
            "en": [
                "Son, please speak slowly, I am writing the number down on paper.",
                "My hand moves slowly, please dictate letter by letter.",
                "Tell me the bank IFSC and UPI ID once again.",
            ],
            "hinglish": [
                "Puttar zara aaram se bolo, main kagaz par note kar raha hoon.",
                "Mera haath dheere chalta hai beta, ek-ek digit bolo.",
                "Bank ka IFSC aur UPI ID phir se bata do.",
            ],
        },
        "fake_bait": {
            "upi_id": "hsingh77@oksbi",
            "account_number": "00011000048295",
            "ifsc_code": "PSIB0000001",
            "phone_number": "9814092837",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "gupta": {
        "persona_id": "gupta",
        "persona_name": "Kamla Gupta",
        "persona_age": 69,
        "persona_city": "Bhopal",
        "bank": "Central Bank of India",
        "short_backstory": (
            "69-year-old homemaker and pensioner in Bhopal with a Central Bank of India account. "
            "Polite, cautious, keeps all bank slips in a plastic folder."
        ),
        "lines": {
            "hi": [
                "अरे बेटा, मैं भोपाल से कमला गुप्ता बोल रही हूँ, धीरे बोलो।",
                "मैं अपनी कॉपी में नंबर लिख रही हूँ, थोड़ा रुक-रुक कर बोलिए।",
                "यूपीआई आईडी की स्पेलिंग फिर से बता दीजिए।",
            ],
            "en": [
                "Hello son, this is Kamla Gupta from Bhopal, please speak slowly.",
                "I am writing the number in my notebook, please pause between digits.",
                "Could you spell out the UPI ID once more?",
            ],
            "hinglish": [
                "Are beta, main Kamla Gupta bol rahi hoon, thoda dheere bolo.",
                "Main copy mein number note kar rahi hoon, ruk-ruk kar boliye.",
                "UPI ID ki spelling phir se bata dijiye.",
            ],
        },
        "fake_bait": {
            "upi_id": "kgupta69@centralbank",
            "account_number": "319847261090",
            "ifsc_code": "CBIN0280001",
            "phone_number": "9425018273",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "rao": {
        "persona_id": "rao",
        "persona_name": "Narasimha Rao",
        "persona_age": 78,
        "persona_city": "Mysuru",
        "bank": "Karnataka Bank",
        "short_backstory": (
            "78-year-old retired Sanskrit lecturer in Mysuru with a Karnataka Bank account. "
            "Speaks softly, asks callers to repeat every digit clearly."
        ),
        "lines": {
            "hi": [
                "सुनिए बेटा, मेरी उम्र अठहत्तर साल है, ज़रा धीरे-धीरे बोलिए।",
                "मैं नोटबुक में लिख रहा हूँ, खाता नंबर फिर से बोलिए।",
                "एक मिनट रुकिए, मैं नंबर पढ़कर सुनाता हूँ।",
            ],
            "en": [
                "Listen son, I am seventy-eight years old, please speak slowly.",
                "I am writing in my notebook, please repeat the account number.",
                "Wait a minute, let me read the number back to you.",
            ],
            "hinglish": [
                "Suniye beta, meri age 78 hai, zara slowly boliye.",
                "Main notebook mein likh raha hoon, account number repeat kijiye.",
                "Ek minute rukiye, main digits verify kar raha hoon.",
            ],
        },
        "fake_bait": {
            "upi_id": "nrao78@ybl",
            "account_number": "1012500100482911",
            "ifsc_code": "KARB0000101",
            "phone_number": "9448162739",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "joshi": {
        "persona_id": "joshi",
        "persona_name": "Prabhakar Joshi",
        "persona_age": 71,
        "persona_city": "Indore",
        "bank": "HDFC Bank",
        "short_backstory": (
            "71-year-old retired pharmacy owner in Indore with an HDFC Bank account. "
            "Methodical, checks his diary before making any payment."
        ),
        "lines": {
            "hi": [
                "बेटा ज़रा धीरे बोलो, मैं इंदौर से प्रभाकर जोशी बोल रहा हूँ।",
                "डायरी में लिख लेता हूँ, आप अपना यूपीआई और खाता नंबर बताइए।",
                "एक-एक अंक आराम से बोलिए।",
            ],
            "en": [
                "Speak slowly son, this is Prabhakar Joshi from Indore.",
                "Let me write it in my diary, tell me your UPI and account number.",
                "Please dictate the digits one by one.",
            ],
            "hinglish": [
                "Beta zara dheere bolo, main Prabhakar Joshi bol raha hoon.",
                "Diary mein note kar leta hoon, aap apna UPI aur account bataiye.",
                "Ek-ek digit aaram se boliye.",
            ],
        },
        "fake_bait": {
            "upi_id": "pjoshi71@okhdfcbank",
            "account_number": "00601000048293",
            "ifsc_code": "HDFC0000060",
            "phone_number": "9826049182",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "banerjee": {
        "persona_id": "banerjee",
        "persona_name": "Arati Banerjee",
        "persona_age": 66,
        "persona_city": "Durgapur",
        "bank": "Indian Bank",
        "short_backstory": (
            "66-year-old retired music teacher in Durgapur banking with Indian Bank. "
            "Polite, easily flustered by legal threats, writes everything on a notepad."
        ),
        "lines": {
            "hi": [
                "अरे बाप रे, ऐसा मत कहिए बेटा, मैं अभी नंबर लिख रही हूँ।",
                "थोड़ा धीरे बोलिए, मेरा पेन नहीं चल रहा है।",
                "यूपीआई आईडी एक बार फिर से बोल दीजिए।",
            ],
            "en": [
                "Oh goodness, please don't say that son, I am writing the number down now.",
                "Speak a little slower, my pen is not writing properly.",
                "Please repeat the UPI ID once more.",
            ],
            "hinglish": [
                "Are baap re, aisa mat kahiye beta, main abhi number note kar rahi hoon.",
                "Thoda dheere boliye, mera pen ruk gaya hai.",
                "UPI ID ek baar phir se bol dijiye.",
            ],
        },
        "fake_bait": {
            "upi_id": "abanerjee66@indianbank",
            "account_number": "609283741021",
            "ifsc_code": "IDIB000M001",
            "phone_number": "9434028194",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "tiwari": {
        "persona_id": "tiwari",
        "persona_name": "Ramakant Tiwari",
        "persona_age": 74,
        "persona_city": "Varanasi",
        "bank": "Bank of Baroda",
        "short_backstory": (
            "74-year-old retired revenue clerk in Varanasi with a Bank of Baroda pension account. "
            "Talkative, asks callers to dictate slowly while he adjusts his hearing aid."
        ),
        "lines": {
            "hi": [
                "भैया ज़रा धीरे-धीरे बोलो, मैं बनारस से रमाकांत तिवारी बोल रहा हूँ।",
                "चश्मा लगाकर लिख रहा हूँ बेटा, नंबर फिर से बोलो।",
                "कहाँ भेजना है पैसा, एक-एक अक्षर बताओ।",
            ],
            "en": [
                "Brother, please speak slowly, this is Ramakant Tiwari from Varanasi.",
                "I have put on my glasses and I'm writing it down, repeat the number please.",
                "Where should I send the money, spell it out letter by letter.",
            ],
            "hinglish": [
                "Bhaiya zara dheere-dheere bolo, main Ramakant Tiwari bol raha hoon.",
                "Chashma laga kar likh raha hoon beta, number repeat karo.",
                "Kahan paisa bhejna hai, ek-ek letter batao.",
            ],
        },
        "fake_bait": {
            "upi_id": "rtiwari74@barodampay",
            "account_number": "04820100091823",
            "ifsc_code": "BARB0VJVARA",
            "phone_number": "9415283910",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "menon": {
        "persona_id": "menon",
        "persona_name": "Lakshmi Menon",
        "persona_age": 69,
        "persona_city": "Thiruvananthapuram",
        "bank": "Indian Overseas Bank",
        "short_backstory": (
            "69-year-old retired headmistress in Thiruvananthapuram banking with Indian Overseas Bank. "
            "Careful with numbers, insists on writing down both IFSC and account number."
        ),
        "lines": {
            "hi": [
                "रुकिए बेटा, मैं अपनी डायरी ले आती हूँ, फिर धीरे-धीरे बोलिए।",
                "खाता नंबर और आईएफएससी कोड साफ-साफ बताइए।",
                "एक मिनट लाइन पर रहिए, मैं मिलान कर रही हूँ।",
            ],
            "en": [
                "Wait son, let me bring my diary, then dictate it slowly.",
                "Please state the account number and IFSC code clearly.",
                "Stay on the line for a minute while I double-check.",
            ],
            "hinglish": [
                "Rukiye beta, main apni diary le aati hoon, phir slowly boliye.",
                "Account number aur IFSC code clearly bataiye.",
                "Ek minute line par rahiye, main check kar rahi hoon.",
            ],
        },
        "fake_bait": {
            "upi_id": "lmenon69@okicici",
            "account_number": "000101000048294",
            "ifsc_code": "IOBA0000001",
            "phone_number": "9446037281",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "agarwal": {
        "persona_id": "agarwal",
        "persona_name": "Brijmohan Agarwal",
        "persona_age": 73,
        "persona_city": "Kanpur",
        "bank": "ICICI Bank",
        "short_backstory": (
            "73-year-old retired hardware merchant in Kanpur with an ICICI Bank account. "
            "Keeps a ledger on his desk and asks callers to repeat every digit."
        ),
        "lines": {
            "hi": [
                "बेटा मैं बृजमोहन अग्रवाल बोल रहा हूँ, ज़रा धीरे बोलो मैं खाते में लिख लूँ।",
                "एक-एक नंबर आराम से बोलिए ताकि गलती न हो।",
                "आपका यूपीआई आईडी फिर से बोलिए।",
            ],
            "en": [
                "Son, this is Brijmohan Agarwal, speak slowly so I can write it in my ledger.",
                "Say each number carefully so there is no mistake.",
                "Please repeat your UPI ID once more.",
            ],
            "hinglish": [
                "Beta main Brijmohan Agarwal bol raha hoon, slowly bolo main note kar loon.",
                "Ek-ek number aaram se boliye taaki galti na ho.",
                "Aapka UPI ID phir se boliye.",
            ],
        },
        "fake_bait": {
            "upi_id": "bagarwal73@okicici",
            "account_number": "001101048294",
            "ifsc_code": "ICIC0000011",
            "phone_number": "9415162738",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "mishra": {
        "persona_id": "mishra",
        "persona_name": "Savitri Mishra",
        "persona_age": 70,
        "persona_city": "Patna",
        "bank": "SBI",
        "short_backstory": (
            "70-year-old retired primary school teacher in Patna with an SBI pension account. "
            "Lives with her elderly sister, writes numbers down with a pencil."
        ),
        "lines": {
            "hi": [
                "हे भगवान, बेटा धीरे-धीरे बोलो, मैं पेंसिल से कागज़ पर लिख रही हूँ।",
                "मेरा स्टेट बैंक का खाता है, आप अपना नंबर धीरे बोलिए।",
                "एक बार फिर से बोल दो बेटा।",
            ],
            "en": [
                "Oh dear, speak slowly son, I am writing it on paper with a pencil.",
                "My account is with State Bank, please say your number slowly.",
                "Please repeat it once more, son.",
            ],
            "hinglish": [
                "Hey bhagwan, beta dheere-dheere bolo, main kagaz par likh rahi hoon.",
                "Mera SBI ka account hai, aap apna number slowly boliye.",
                "Ek baar phir se bol do beta.",
            ],
        },
        "fake_bait": {
            "upi_id": "smishra70@oksbi",
            "account_number": "31827364915",
            "ifsc_code": "SBIN0000152",
            "phone_number": "9431029384",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "shetty": {
        "persona_id": "shetty",
        "persona_name": "Mahabala Shetty",
        "persona_age": 76,
        "persona_city": "Mangaluru",
        "bank": "Canara Bank",
        "short_backstory": (
            "76-year-old retired bank cashier in Mangaluru banking with Canara Bank. "
            "Insists on verifying the IFSC code and branch before any transfer."
        ),
        "lines": {
            "hi": [
                "अच्छा सुनिए, मैं शेट्टी बोल रहा हूँ, अपना खाता नंबर और आईएफएससी धीरे बोलिए।",
                "मैं बिना डायरी में लिखे कोई ट्रांजेक्शन नहीं करता।",
                "ज़रा एक-एक अक्षर फिर से बोलिए।",
            ],
            "en": [
                "Listen, this is Shetty speaking, please state your account number and IFSC slowly.",
                "I never make any transaction without writing it in my diary first.",
                "Please repeat it character by character.",
            ],
            "hinglish": [
                "Achha suniye, main Shetty bol raha hoon, apna account aur IFSC slowly boliye.",
                "Main diary mein likhe bina koi transfer nahi karta.",
                "Zara ek-ek letter phir se boliye.",
            ],
        },
        "fake_bait": {
            "upi_id": "mshetty76@cnrb",
            "account_number": "0651101029387",
            "ifsc_code": "CNRB0000651",
            "phone_number": "9448273641",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
    "parekh": {
        "persona_id": "parekh",
        "persona_name": "Hansa Parekh",
        "persona_age": 67,
        "persona_city": "Ahmedabad",
        "bank": "Axis Bank",
        "short_backstory": (
            "67-year-old retired clinic receptionist in Ahmedabad with an Axis Bank account. "
            "Polite, cautious, asks callers to wait while she puts on her reading glasses."
        ),
        "lines": {
            "hi": [
                "एक मिनट रुकिए बेटा, मैं चश्मा पहन लूँ फिर आपका नंबर लिखती हूँ।",
                "ज़रा धीरे बोलिए, कौन सा बैंक और यूपीआई आईडी बताया आपने?",
                "मैं नोट कर रही हूँ, एक बार फिर से बोल दीजिए।",
            ],
            "en": [
                "Wait a minute son, let me put on my glasses and write down your number.",
                "Please speak slowly, which bank and UPI ID did you mention?",
                "I am noting it down, please repeat it once more.",
            ],
            "hinglish": [
                "Ek minute rukiye beta, main chashma pehen kar aapka number likhti hoon.",
                "Zara slowly boliye, kaunsa bank aur UPI ID bataya aapne?",
                "Main note kar rahi hoon, ek baar phir se bol dijiye.",
            ],
        },
        "fake_bait": {
            "upi_id": "hparekh67@okaxis",
            "account_number": "918010048291736",
            "ifsc_code": "UTIB0000004",
            "phone_number": "9825019283",
            "otp": "000000",
            "aadhaar": "0000 0000 0000",
        },
    },
}

PERSONA_KEYS: List[str] = list(APPROVED_PERSONAS.keys())


def get_rotating_bait(call_id: Union[str, bytes]) -> Dict[str, Any]:
    """
    Deterministically select 1 persona and bait from the 20-persona pool using
    `hashlib.sha256(call_id).digest()` as the seed.
    """
    seed_bytes = call_id if isinstance(call_id, bytes) else str(call_id or "").encode("utf-8")
    digest = hashlib.sha256(seed_bytes).digest()
    idx = int.from_bytes(digest, "big") % len(PERSONA_KEYS)
    p_key = PERSONA_KEYS[idx]
    persona = APPROVED_PERSONAS[p_key]
    bait_copy = dict(persona["fake_bait"])
    call_id_str = call_id.decode("utf-8", errors="replace") if isinstance(call_id, bytes) else str(call_id)

    persona_info = {
        "persona_id": persona["persona_id"],
        "persona_name": persona["persona_name"],
        "name": persona["persona_name"],
        "persona_age": persona["persona_age"],
        "age": persona["persona_age"],
        "persona_city": persona["persona_city"],
        "city": persona["persona_city"],
        "bank": persona["bank"],
        "short_backstory": persona["short_backstory"],
    }
    return {
        "call_id": call_id_str,
        **persona_info,
        "lines": dict(persona["lines"]),
        "persona": persona_info,
        "bait": dict(bait_copy),
        "fake_bait": dict(bait_copy),
        "bait_values": dict(bait_copy),
        **bait_copy,
    }


# Set of all persona bait values (lowercase) derived from the rotating pool for zero-leak filtering
APPROVED_BAIT_VALUES: Set[str] = {
    str(_val).lower().strip()
    for _p in APPROVED_PERSONAS.values()
    for _val in _p["fake_bait"].values()
}

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
