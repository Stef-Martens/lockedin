#!/bin/bash
# Builds the LockedIn iPhone app, signs it with your Personal Team and installs it on your iPhone.
# A free Apple ID's signature runs out after 7 days: run this again (make ios) when the app stops opening.
set -euo pipefail
cd "$(dirname "$0")"

export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
BUNDLE_ID=be.stefmartens.lockedin.watch

TEAM="${LOCKEDIN_TEAM_ID:-}"
if [[ -z "$TEAM" && -f .team-id ]]; then
  TEAM="$(tr -d '[:space:]' < .team-id)"
fi
if [[ -z "$TEAM" ]]; then
  echo "No team ID. Set LOCKEDIN_TEAM_ID or put it in ios/.team-id (README section 13 says where to find it)." >&2
  exit 1
fi

if ! command -v xcodegen >/dev/null; then
  echo "xcodegen is missing: brew install xcodegen" >&2
  exit 1
fi

DEVICE="${IOS_DEVICE:-}"
if [[ -z "$DEVICE" ]]; then
  # The first physical iPhone that's plugged in or paired over Wi-Fi.
  DEVICE="$(xcrun devicectl list devices 2>/dev/null | awk '
    /physical/ && /\(iPhone[0-9]+,[0-9]+\)/ && (/ connected / || /available \(paired\)/) {
      if (match($0, /[0-9A-Fa-f]{8}-[0-9A-Fa-f-]{12,}/)) { print substr($0, RSTART, RLENGTH); exit }
    }')"
fi
if [[ -z "$DEVICE" ]]; then
  echo "No iPhone found. Plug it in (or put it on the same Wi-Fi), unlock it, and check: xcrun devicectl list devices" >&2
  echo "Or name it: IOS_DEVICE=<identifier> make ios" >&2
  exit 1
fi
echo "Installing on $DEVICE with team $TEAM"

xcodegen generate
xcodebuild build \
  -project LockedIn.xcodeproj -scheme LockedIn -configuration Debug \
  -destination "id=$DEVICE" -derivedDataPath build \
  -allowProvisioningUpdates -allowProvisioningDeviceRegistration \
  DEVELOPMENT_TEAM="$TEAM"

xcrun devicectl device install app --device "$DEVICE" build/Build/Products/Debug-iphoneos/LockedIn.app

if ! launch="$(xcrun devicectl device process launch --device "$DEVICE" --terminate-existing "$BUNDLE_ID" 2>&1)"; then
  echo "$launch" >&2
  if grep -qiE 'trust|profile|security' <<<"$launch"; then
    echo >&2
    echo "The iPhone doesn't trust your developer certificate yet. On the iPhone: Settings → General →" >&2
    echo "VPN & Device Management → your Apple ID → Trust. Then run make ios again." >&2
  fi
  exit 1
fi
echo "$launch"
