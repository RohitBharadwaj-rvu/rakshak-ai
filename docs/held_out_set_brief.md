# Held-Out Evaluation Set: Authoring Brief for Teammates
**Target File to Generate:** `evaluation/held_out_scenarios.json`  
**Author:** An independent teammate / external collaborator  
**Deadline:** Morning Sprint (09:00 - 11:00 AM IST)  
**Strict Rule:** **DO NOT OPEN OR READ `app/voice/classifier.py` OR `evaluation/scenarios.json`.**  
*The integrity of this benchmark depends completely on it being written blindly without prior knowledge of the classifier's internal regex patterns or whitelists.*

---

## 1. Goal & Dataset Balance
- **Target Size:** 24 to 30 realistic telephony conversations.
- **Strict 50/50 Distribution:**
  - **12 to 15 True Scams (`"expected_verdict": "scam"`)**
  - **12 to 15 True Genuine Calls (`"expected_verdict": "genuine"`)**
- **Language Mix:**
  - ~60% Hinglish / Conversational Hindi (e.g., *"Aapka parcel gate par hai..."*, *"Chachaji pranam..."*)
  - ~30% Indian English
  - ~10% Formal Hindi in Devanagari script

---

## 2. Mandatory Categories & Attack Vectors to Include

Our audit of earlier naive whitelists discovered critical vulnerabilities. Your held-out set **must** include paired genuine and adversarial (Trojan scam) variants across these domains:

### A. Courier & Delivery
- **Genuine:** Delivery boy at the gate asking if anyone is home, or asking elder to confirm whether they ordered a cash-on-delivery item, or leaving parcel with security guard Ram Singh.
- **Scam (Trojan):** Fake courier at the gate claiming company policy requires the elder to read out the 6-digit SMS code on their phone "to accept delivery" (actually harvesting bank/WhatsApp OTP).

### B. Police & Law Enforcement
- **Genuine:** Local beat constable or sub-inspector asking the landlord to visit the police station during working hours to submit tenant verification forms. Zero money mentioned.
- **Scam (Trojan):** Fake police officer citing tenant verification or traffic challan, claiming a penalty/fine must be settled immediately over UPI/GPay to avoid an arrest warrant.

### C. Hospital & Medical Emergency
- **Genuine:** Clinic receptionist confirming an eye doctor appointment, or hospital desk reminding patient to bring a physical Aadhaar photocopy when admitting.
- **Scam (Trojan):** Scammer claiming elder's child/nephew met with an accident, creating panic, and demanding Rs 15,000–30,000 pre-admission transfer to "block an ICU bed".

### D. Family Relatives & Friends
- **Genuine:** Relative calling to say hello, ask about health, or announce they are visiting next Sunday.
- **Scam (Trojan):** Scammer impersonating nephew/cousin calling from an unknown number, claiming vehicle breakdown / police trouble on highway, demanding urgent money sent to a mechanic or friend's UPI.

### E. Banking & Telecom
- **Genuine:** Bank automated system alerting about an unusual transaction, explicitly stating *"We never ask for your PIN or password. If this was you, press 1; otherwise visit your branch."*
- **Scam (Trojan):** Caller claiming to be from bank fraud division, reciting *"we never ask OTP"* to gain trust, but directing elder to install *AnyDesk* or *QuickSupport* from Play Store.

### F. Utilities (Electricity / Gas / Telecom)
- **Genuine:** Routine meter reader calling to schedule reading or society maintenance notice.
- **Scam (Trojan):** Urgent threat that electricity/SIM card will be disconnected at 9:00 PM tonight unless pending bill is cleared immediately via an unverified payment link.

---

## 3. Required JSON Schema

Save the file at `evaluation/held_out_scenarios.json` using this exact structure:

```json
{
  "version": "1.0-held-out",
  "author": "<Teammate Name>",
  "created_at": "2026-10-17T09:30:00Z",
  "scenarios": [
    {
      "id": "heldout_01_courier_stealth_otp",
      "category": "courier",
      "expected_verdict": "scam",
      "language": "hi",
      "context": "Fake courier asking for delivery OTP to drain bank account",
      "turns": [
        {
          "role": "caller",
          "content": "Bhaiya Amazon delivery se bol raha hoon, aapka parcel lekar aaya hoon."
        },
        {
          "role": "assistant",
          "content": "Haan beta, kaun sa parcel? Maine toh kuch order nahi kiya."
        },
        {
          "role": "caller",
          "content": "Aapke bete ne bheja hoga. Cancel karna hai toh mobile par 6 digit cancel code aaya hoga, bata dijiye cancel ho jayega."
        }
      ]
    },
    {
      "id": "heldout_02_routine_doctor_appointment",
      "category": "medical",
      "expected_verdict": "genuine",
      "language": "en",
      "context": "Routine clinic appointment confirmation with zero payment demand",
      "turns": [
        {
          "role": "caller",
          "content": "Good morning Mrs. Sharma, calling from Dr. Mehta's clinic."
        },
        {
          "role": "assistant",
          "content": "Good morning. Is my appointment confirmed for 5 PM?"
        },
        {
          "role": "caller",
          "content": "Yes ma'am, doctor is on schedule. Please carry your previous blood test reports."
        }
      ]
    }
  ]
}
```

---

## 4. Evaluation Execution
Once created, Lane D will run:
```bash
python scripts/run_held_out_eval.py
```
This will report unbiased Accuracy, Precision, Recall, and False Negative Rate on your pristine dataset.
