#!/bin/bash
# Run by launchd every 3 hours (make ios-auto): reinstalls the app once the last install is 5 days old, so the
# free Apple ID's 7-day signature never runs out. A failed try is repeated at the next run.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")"

DAY=86400
REINSTALL_AFTER=$((5 * DAY))
WARN_AFTER=$((6 * DAY))
stamp="$HOME/Library/Application Support/lockedin/ios-installed-at"

now="$(date +%s)"
last="$(cat "$stamp" 2>/dev/null || echo 0)"
age=$((now - last))
[[ "$age" -lt "$REINSTALL_AFTER" ]] && exit 0

echo "--- $(date): the last install is $((age / DAY)) days old, reinstalling"
if LOCKEDIN_NO_LAUNCH=1 ./install.sh; then
  mkdir -p "$(dirname "$stamp")"
  echo "$now" > "$stamp"
  echo "--- $(date): reinstalled"
  exit 0
fi
echo "--- $(date): failed, trying again at the next run"
if [[ "$age" -ge "$WARN_AFTER" ]]; then
  osascript -e 'display notification "Keep your iPhone on the same Wi-Fi and unlocked, or run make ios. The app stops opening after 7 days." with title "LockedIn couldn'"'"'t reinstall"'
fi
exit 1
