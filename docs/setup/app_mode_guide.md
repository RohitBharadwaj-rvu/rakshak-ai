# GuardianLine App Mode Setup Guide (Android Call Screening)

**Intended Users:** Android smartphone users (Android 10 / API 29 or higher).  
**Mechanism:** Native `CallScreeningService` + Conditional Busy Forwarding (`**67*`).  
**Time to Complete:** $< 3$ minutes.

---

## How App Mode Operates

1. Inbound calls are evaluated silently on the elder's device before the ringer sounds:
   - **Saved Contacts:** Handset rings immediately.
   - **Emergency Services (112, 100, 108, 1930):** Handset rings immediately.
   - **Unknown Numbers:** The app disallows and rejects the call in sub-second time.
2. The carrier detects the call as rejected/busy and triggers conditional busy forward (`**67*`) to the GuardianLine voice assistant.
3. *Design Target:* The voice receptionist aims to connect within 2 seconds of call redirection.

> [!NOTE]
> **Important Scope Note:**  
> App Mode configures forward on busy (`**67*`). If a call from a saved contact is ignored or unanswered, it will ring out or go to normal carrier voicemail unless unanswered forwarding (`**61*`) is also configured.

---

## Step-by-Step Installation

### Step 1: Install GuardianLine APK
Install `GuardianLine.apk` onto the senior's phone.

### Step 2: Grant Call Screening Role
1. Open the **GuardianLine** app.
2. Tap **1. Enable Screening Protection**.
3. In the system prompt, choose **Set as default** Caller ID & spam app.
4. Ensure Contact Access permission is granted so family members ring normally.

### Step 3: Activate Carrier Busy Forwarding
1. Tap **2. Activate Carrier Forwarding (**67*)**.
2. The phone dialer opens with `**67*<gateway_number>#` pre-filled.
3. Press **Call** to activate.
4. Verify using `*#67#`.

---

## Deactivation / Undo

1. In the Phone dialer, dial `##67#` (press Call) to cancel busy forwarding.
2. In Android Settings $\rightarrow$ Default Apps $\rightarrow$ Caller ID & Spam $\rightarrow$ reset to Phone.
3. Uninstall GuardianLine if no longer desired.
