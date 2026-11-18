#!/usr/bin/env bash
set -euo pipefail
for label in com.lockedin.fitsync com.lockedin.fitsync.poll; do
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
done
echo "Removed the LockedIn sync agents. Config in ~/.config/lockedin/ was left in place."
