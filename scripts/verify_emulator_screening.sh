#!/usr/bin/env bash
# Verify GuardianLine Android call screening in JUnit 5 and (when an AVD is running) via adb emu gsm call.
# Tests all four required cases:
#   1. Saved contacts ring (ALLOW)
#   2. Unknown numbers are rejected (REJECT_AND_FORWARD -> triggers **67* busy forwarding)
#   3. Emergency numbers 112 and 1930 ring (ALLOW)
#   4. BOLNA_GATEWAY_NUMBER rings (ALLOW)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANDROID_DIR="$REPO_ROOT/android"

GATEWAY_NUMBER=$(grep -E '^BOLNA_GATEWAY_NUMBER=' "$ANDROID_DIR/gradle.properties" | cut -d= -f2)
echo "=== [1/2] Running Android JUnit 5 Screening Suite (BOLNA_GATEWAY_NUMBER=$GATEWAY_NUMBER) ==="
(cd "$ANDROID_DIR" && ./gradlew testDebugUnitTest assembleDebug --no-daemon)

if ! command -v adb >/dev/null 2>&1; then
  echo "adb not on PATH; skipping live AVD gsm call injection (JUnit 5 suite passed)."
  exit 0
fi

DEVICE_COUNT=$(adb devices | awk 'NR>1 && $2=="device" {count++} END {print count+0}')
if [[ "$DEVICE_COUNT" -eq 0 ]]; then
  echo "No running Android emulator detected via 'adb devices'; skipping live AVD gsm call injection (JUnit 5 suite passed)."
  exit 0
fi

echo "=== [2/2] Running Live Emulator Call Screening Checks ==="
APK_PATH="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
adb install -r "$APK_PATH"
adb shell cmd role add-role-holder android.app.role.CALL_SCREENING ai.guardianline.screening

simulate_call() {
  local num="$1"
  local label="$2"
  echo "-> Simulating incoming call from $num ($label)..."
  adb emu gsm call "$num"
  sleep 2
  adb emu gsm cancel "$num"
  sleep 1
}

simulate_call "112" "Emergency 112 (expect ALLOW / ring)"
simulate_call "1930" "Cybercrime Helpline 1930 (expect ALLOW / ring)"
simulate_call "$GATEWAY_NUMBER" "Bolna Gateway $GATEWAY_NUMBER (expect ALLOW / ring)"
simulate_call "+919876543210" "Saved Contact +919876543210 (expect ALLOW / ring when present in Contacts)"
simulate_call "+919900112233" "Unknown Caller (expect REJECT_AND_FORWARD)"

echo "=== Recent GuardianCallScreeningService Logcat Output ==="
adb logcat -d -s GuardianCallScreening:* | tail -n 20 || true
