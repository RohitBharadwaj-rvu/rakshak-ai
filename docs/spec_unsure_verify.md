# Specification: "Unsure $\rightarrow$ Verify" Protocol
**Author:** Lane D (Detection & Defense Architecture)  
**Status:** Approved Specification (To be integrated into Lane A Bolna Agent)  
**Target:** Safe Telephony Receptionist Policy for Ambiguous / High-Risk Inbound Calls

---

## 1. Motivation: The Failure of Binary Classification
Forcing a binary choice (`scam` vs `genuine`) on ambiguous inbound calls creates an unresolvable trade-off:
- **False Positive:** A real doctor, hospital desk, or courier is sent to the deceptive honeypot.
- **False Negative:** An adversarial scammer using novel vocabulary is transferred directly to the elderly victim.

The **"Unsure $\rightarrow$ Verify"** protocol breaks this binary trap. It defines an assertive, polite, non-punitive verification boundary that protects the elder without escalating to hostility.

---

## 2. Trigger Conditions
The protocol is invoked whenever ANY of the following occur:

1. **Classifier Ambiguity:** `classify_caller` returns `verdict: "unsure"` (confidence between $0.21$ and $0.84$).
2. **Authority / Urgency without Verified Whitelist:** Caller claims to be police, bank fraud department, hospital, or telecom official, but the call originated from an unknown or non-toll-free number.
3. **Any Unscheduled Value / Credential Request:** Caller asks for money, advance payment, OTP, Aadhaar number, or app download (*AnyDesk/QuickSupport*), even if claiming to be a relative or delivery boy.
4. **Engine Timeout ($>1.4$s) or Early Call Phase:** If the classification pipeline hits the latency ceiling or is on turn 1–2 with incomplete intent signals.

---

## 3. What the Agent Says to the Caller (In-Character Safe Scripts)

The receptionist agent remains respectful, calm, and firmly non-compliant. It directs the caller to physical or authenticated channels:

### Case A: Courier Requesting "Delivery OTP"
> **Hindi:**  
> *"Bhaiya, hamare yahan phone par OTP share karna strictly mana hai. Aap parcel building ke main gate security guard ke paas drop kar dijiye, hum wahan se collect kar lenge. Shukriya."*  
> **English:**  
> *"We do not share OTPs over the phone. Please drop the package with the building security guard at the gate. Thank you."*

### Case B: Police Citing "Tenant Verification / Penalty"
> **Hindi:**  
> *"Sir, official policy ke anusar hum kisi bhi verification ya fine ke liye seedhe local police station aakar physically milenge. Phone par koi statement ya payment nahi kiya jayega. Aap station ka address bata dijiye."*  
> **English:**  
> *"According to our family policy, we will visit the local police station in person for any verification or documentation. No statements or payments are made over the phone."*

### Case C: Hospital / Emergency Advance Demand
> **Hindi:**  
> *"Hum abhi hospital ke physical reception counter par pahunch rahe hain. Wahan desk par saara payment aur documents jama karenge. Phone par koi advance nahi bhejte."*  
> **English:**  
> *"We are on our way to the hospital reception desk and will settle all fees and documents at the physical counter. No advance is transferred over phone."*

### Case D: Relative Calling from Unknown Phone Requesting Urgent Cash
> **Hindi:**  
> *"Beta, hum safety ke liye dusre number se aaye call par payment nahi karte. Main abhi aapke regular saved number par call back kar raha hoon, wahan baat karte hain."*  
> **English:**  
> *"For safety, we do not transfer money on calls from unfamiliar numbers. I am hanging up and calling your registered mobile phone right now."*

---

## 4. What the Family is Told (Immediate Alert Payload)

Whenever the protocol triggers, the system dispatches an urgent, non-alarming notification to the family member's WhatsApp / SMS / App Dashboard:

### Notification Message (WhatsApp / SMS)
```text
🛡️ GUARDIANLINE DEFENSIVE ALERT
Call Screened for: Mrs. Savitri Sharma (+91 98XXX XXXXX)
Status: UNSURE -> VERIFIED CHALLENGE APPLIED

Caller Number: +91 91234 56789
Claimed Identity: "Hauz Khas Police Station / Sub-Inspector"
Request: Asked for immediate Rs 2,500 penalty payment via GPay.

Action Taken:
Receptionist politely refused phone payment and instructed caller to meet at the local station in person. The call was safely concluded.

Audio Transcript Excerpt:
Caller: "...aapne biometric register nahi kiya, 2500 fine lagega..."
Agent: "...hum seedhe local police station aakar milenge..."

Next Steps for Family:
1. Please call your elder to reassure them.
2. If this was a legitimate call, contact local station directly at official verified landline.
```

### JSON Dispatch Payload (Lane B Backend Webhook)
```json
{
  "event": "caller_screened_unsure_verify",
  "call_id": "call_live_9872",
  "timestamp": "2026-10-17T01:10:00Z",
  "elder": {
    "name": "Mrs. Savitri Sharma",
    "phone": "+919876543210"
  },
  "inbound_caller": {
    "phone": "+919123456789",
    "claimed_entity": "police_station"
  },
  "screening_result": {
    "verdict": "unsure",
    "confidence": 0.62,
    "primary_risk": "authority_payment_demand",
    "challenge_applied": "physical_station_visit_instruction"
  },
  "family_dispatch": {
    "recipient_phone": "+919988776655",
    "channel": "whatsapp_and_sms",
    "alert_level": "medium_advisory"
  }
}
```

---

## 5. Implementation Roadmap (Post-Lane A Integration)
1. **Lane A Bolna Agent State Machine:** When `classify_caller` returns `unsure`, transition to the `challenge_defensive` dialogue node using the scripts above.
2. **Lane B Fast Notification Pipeline:** Connect `POST /tools/classify_caller` response to the existing alert queue when verdict is `unsure` or `scam`.
