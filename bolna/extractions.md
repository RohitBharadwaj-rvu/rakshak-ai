# Bolna post-call extractions · category "Scam Intel"

Set in the agent's Extractions tab (model GPT 4.1 Mini). The agent JSON only stores these by ID,
so recreate them by hand in a new account. Results arrive in the webhook as
`extracted_data["Scam Intel"][<field>]`: free-text values in `subjective`, pre-defined in `objective`, plus `confidence`.

| Name | Answer type | Extraction prompt |
| --- | --- | --- |
| `scam_type` | Pre-defined | What kind of call was this, based on what the caller said and asked for? |
| `upi_ids` | Free text | List every UPI ID the caller (user) said, written as name@bank, separated by commas. Convert spoken words: "rahul dot sbi at y b l" becomes rahul.sbi@ybl. If only part of a UPI ID was said, write it as heard and add "(incomplete)". Never guess missing parts. If none, write "none". |
| `phone_numbers` | Free text | List every phone number the caller (user) said, digits only, separated by commas. Only include a number the caller said as one number. Never join separate fragments or repeated parts into one number. Ignore numbers the assistant said. If none, write "none". |
| `bank_accounts` | Free text | List every bank account number the caller (user) said, digits only, separated by commas. Never guess or complete digits. If none, write "none". |
| `ifsc_codes` | Free text | List every IFSC code the caller (user) said, in capital letters (e.g. HDFC0001234). If none, write "none". |
| `caller_claimed_identity` | Free text | Who did the caller claim to be? Give the name and the organisation, bank, police station or company they claimed, e.g. "Rahul, SBI head office". If not said, write "unknown". |
| `amount_demanded` | Free text | How much money did the caller ask to be paid or transferred? Digits in rupees only, e.g. 5000. If none, write "none". |
| `otp_or_aadhaar_requested` | Pre-defined | Did the caller ask for an OTP, Aadhaar number, PIN, password or card details? |

## Pre-defined answers

**scam_type**

| Value | Condition |
| --- | --- |
| `bank_kyc` | Caller claims to be from a bank and says KYC, account or card is expired or blocked, and asks for OTP, details or payment |
| `digital_arrest` | Caller claims to be police, CBI or a court, threatens arrest or an FIR, and demands money |
| `other_scam` | Caller pressures for money, OTP, Aadhaar or bank details in any other way |
| `genuine` | Caller has a normal reason and does not ask for money, OTP or personal details |

**otp_or_aadhaar_requested**

| Value | Condition |
| --- | --- |
| `yes` | The caller asked for an OTP, Aadhaar number, PIN, password or card details at any point |
| `no` | The caller never asked for any of these |
