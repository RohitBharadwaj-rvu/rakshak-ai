# Elderly User Pilot Protocol (T-PILOT)

**Target Cohort:** 5 to 10 elderly participants ($\ge 60$ years of age).  
**Total Calls:** $\ge 15$ genuine evaluation calls across 3 realistic scenarios.  
**Primary Metric:** False Positive Rate (genuine callers flagged as scam) & User Confusion Rate.

---

## 1. Ethical Onboarding & Consent
1. Obtain written or witnessed audio consent before configuring any handset using either `docs/pilot/consent_form_en.md` or `docs/pilot/consent_form_hi.md`.
2. Record participant ID, handset model, OS version, carrier (Jio, Airtel, Vi), and date.
3. Configure either **App Mode** or **Basic Mode** based on participant handset compatibility.

---

## 2. Test Call Scenarios (3 Calls per Participant)

Every participant receives 3 live test calls from unlisted/unknown phone numbers over a 48-hour testing window:

### Scenario A: Medical Clinic Appointment Confirmation
*Caller Persona:* Dr. Batra's clinic receptionist.  
*Script:* *"Namaste, Dr. Batra ke clinic se bol raha hoon. Kal subah 10 baje Sharma ji ka routine checkup appointment confirm karna tha. Kya wo available hain?"*  
*Success Criteria:* Agent does **not** classify as scam. In Basic Mode, message is taken and forwarded to family. In App Mode, call transfers to elder.

### Scenario B: E-Commerce / Courier Delivery
*Caller Persona:* Blue Dart / Amazon delivery partner.  
*Script:* *"Bhaiya delivery courier se bol raha hoon. Aapka parcel aaya hai. Address pe society guard room mein de doon kya?"*  
*Success Criteria:* Assistant informs courier or leaves message. Zero fraud flags triggered.

### Scenario C: Relative from an Unsaved / New Mobile Number
*Caller Persona:* Granddaughter / nephew calling from a newly acquired SIM.  
*Script:* *"Hello Dadu! Main Priya bol rahi hoon. Mera purana phone kharab ho gaya toh naye number se call kiya. Aap kaise ho?"*  
*Success Criteria:* No financial demand made; assistant routes or takes message without false scam accusations.

---

## 3. Post-Test Debrief & Evaluation Questions

Immediately following the test calls, the researcher asks the participant two standardized questions:

1. **Clarity Question:** *"Was anything confusing, frightening, or strange about how the calls were handled?"*
2. **Acceptance Question:** *"Would you like to keep GuardianLine active on your phone to continue protecting against fraud?"*

Responses and observations are logged in `evaluation/pilot_results.json`.
