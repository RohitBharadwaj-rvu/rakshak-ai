# GuardianLine App Mode Setup Guide (Android Call Screening)

**Intended Users:** Android smartphone users (Android 10 / API 29 or higher).  
**Mechanism:** Native `CallScreeningService` + Conditional Busy Forwarding (`**67*`).  
**Time to Complete:** $< 3$ minutes.

---

## How App Mode Works

1. Inbound calls are analyzed on the handset before the phone rings.
2. **Saved Contacts:** Handset rings instantly as normal.
3. **Emergency Numbers (112, 100, 108, 1930):** Handset rings instantly.
4. **Unknown Callers:** Handset **does not ring**. The app automatically disallows/rejects the call on the handset in sub-second time.
5. The carrier detects the busy/rejected status and automatically triggers conditional forward on busy (`**67*`) to the GuardianLine Bolna Agent.
6. The caller hears a polite AI receptionist. If genuine, the agent can initiate an outbound transfer back to the elder.

---

## Step-by-Step Installation

### Step 1: Install GuardianLine APK
1. Download `GuardianLine.apk` to the handset.
2. Tap the downloaded file to install. If prompted, allow *Install from Unknown Sources* for this installer.

### Step 2: Grant Call Screening Role
1. Open the **GuardianLine** app.
2. Tap **1. Enable Screening Protection**.
3. Android system dialog will appear: *"Set GuardianLine as default Caller ID & spam app?"*
4. Tap **Set as default**.
5. The status indicator will turn green: `Status: ACTIVE & PROTECTED`.

### Step 3: Activate Carrier Busy Forwarding
1. Tap **2. Activate Carrier Forwarding (**67*)**.
2. The phone dialer will open with `**67*+919988776655#` pre-filled.
3. Press **Call**.
4. Confirm network toast: `"Call forwarding when busy: Registration was successful"`.

---

## Verification Test

1. From another phone whose number is **not** in the elder's contacts, place a call to the elder's phone.
2. Verify:
   - Handset screen does not wake up or ring.
   - Calling phone connects to the GuardianLine voice receptionist within 2 seconds.
3. Now place a call from a number saved in the elder's address book.
   - Handset rings immediately.

---

## Deactivation / Undo

1. Open Dialer and dial `##67#` (press Call) to cancel busy forwarding.
2. Open Android Settings $\rightarrow$ Apps $\rightarrow$ Default Apps $\rightarrow$ Caller ID & Spam $\rightarrow$ select None (or default Phone).
3. Uninstall the GuardianLine application.
