#!/usr/bin/env bash
# Installs the launchd agent that keeps the iPhone app signed (ios/auto-reinstall.sh, every 3 hours).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
plist="$HOME/Library/LaunchAgents/com.lockedin.iosreinstall.plist"
log="$HOME/Library/Logs/lockedin-ios.log"

[ -f "$here/.team-id" ] || { echo "Put your team ID in ios/.team-id first (README section 13)."; exit 1; }

mkdir -p "$(dirname "$plist")" "$(dirname "$log")"
sed -e "s|__SCRIPT__|$here/auto-reinstall.sh|" -e "s|__LOG__|$log|" "$here/com.lockedin.iosreinstall.plist.template" > "$plist"

launchctl bootout "gui/$(id -u)/com.lockedin.iosreinstall" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "Installed. Log: $log"
