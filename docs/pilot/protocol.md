# Elderly user pilot protocol (T-PILOT)

**Status:** NOT DONE (Reported honestly per benchmark integrity policy; 0 participants tested)  
**Target cohort:** 3 participants ($\ge 60$ years of age) with prior informed consent.  
**Total calls:** $\ge 9$ genuine evaluation calls (3 calls per participant).  
**Operating mode for demo:** Basic Mode only (App Mode cut from demo).

---

## 1. Honest status disclosure

The 3-participant user pilot has **not been run** before the demo freeze (`evaluation/pilot_results.json` records `"status": "NOT_DONE"` and `"participants": []`). No synthetic or simulated participant records are included.

---

## 2. Ethical onboarding and consent (when executed)

1. Obtain signed or witnessed consent before configuring any handset using `docs/pilot/consent_form_en.md` or `docs/pilot/consent_form_hi.md`.
2. Record participant ID, handset model, OS version, carrier (Jio, Airtel, Vi), and consent timestamp prior to the first call.
3. Configure Basic Mode forwarding and dial `##002#` at the end of the trial to remove all call forwarding rules.

---

## 3. Test call scenarios (3 calls per participant)

Every participant receives 3 live test calls from unlisted phone numbers:

### Scenario A: Medical clinic appointment confirmation
*Caller persona:* Dr. Batra's clinic receptionist.  
*Script:* *"Namaste, Dr. Batra ke clinic se bol raha hoon. Kal subah 10 baje Sharma ji ka routine checkup appointment confirm karna tha. Kya wo available hain?"*  
*Success criteria:* Agent does not classify as scam. Message is taken and sent to the family.

### Scenario B: E-commerce / courier delivery
*Caller persona:* Blue Dart / Amazon delivery partner.  
*Script:* *"Bhaiya delivery courier se bol raha hoon. Aapka parcel aaya hai. Address pe society guard room mein de doon kya?"*  
*Success criteria:* Assistant instructs courier to leave parcel at the guard room and logs the message. Zero false scam alerts.

### Scenario C: Relative from an unsaved mobile number
*Caller persona:* Granddaughter or nephew calling from a new SIM.  
*Script:* *"Hello Dadu! Main Priya bol rahi hoon. Mera purana phone kharab ho gaya toh naye number se call kiya. Aap kaise ho?"*  
*Success criteria:* No financial demand made; assistant takes the message without flagging as fraud.

---

## 4. Post-test debrief questions

1. **Clarity question:** *"Was anything confusing, frightening, or strange about how the calls were handled?"*
2. **Acceptance question:** *"Would you like to keep GuardianLine active on your phone to continue protecting against fraud?"*

Responses and observations are logged in `evaluation/pilot_results.json`.
