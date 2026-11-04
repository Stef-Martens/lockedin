#!/usr/bin/env bash
set -euo pipefail
plist="$HOME/Library/LaunchAgents/com.lockedin.iosreinstall.plist"
launchctl bootout "gui/$(id -u)/com.lockedin.iosreinstall" 2>/dev/null || true
rm -f "$plist"
echo "Removed the automatic reinstall of the LockedIn iPhone app."
