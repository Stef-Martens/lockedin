#!/usr/bin/env bash
set -euo pipefail
plist="$HOME/Library/LaunchAgents/com.lockedin.fitsync.plist"
launchctl bootout "gui/$(id -u)/com.lockedin.fitsync" 2>/dev/null || true
rm -f "$plist"
echo "Removed the LockedIn sync agent. Config in ~/.config/lockedin/ was left in place."
