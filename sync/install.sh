#!/usr/bin/env bash
# Installs the launchd agent that runs sync/fit_sync.py whenever the Zwift or HealthFit folder changes,
# and every 15 minutes (StartInterval 900). Reads folder paths from ~/.config/lockedin/sync.env.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
conf="$HOME/.config/lockedin/sync.env"
plist="$HOME/Library/LaunchAgents/com.lockedin.fitsync.plist"
log="$HOME/Library/Logs/lockedin-sync.log"

[ -f "$conf" ] || { echo "Create $conf first (see README → Mac sync)."; exit 1; }
get() { { grep -E "^$1=" "$conf" || true; } | tail -1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//'; }

zwift="$(get ZWIFT_ACTIVITIES_DIR)"; zwift="${zwift:-$HOME/Documents/Zwift/Activities}"
healthfit="$(get HEALTHFIT_DIR)"
watch="    <string>${zwift/#\~/$HOME}</string>"
[ -n "$healthfit" ] && watch="$watch
    <string>${healthfit/#\~/$HOME}</string>"

# /usr/bin/python3 is a shim; the interpreter that actually reads your folders (and needs
# Full Disk Access) is the one it points to.
py="$(/usr/bin/python3 -c 'import os, sys; print(os.path.realpath(sys.executable))')"

mkdir -p "$(dirname "$plist")" "$(dirname "$log")"
"$py" - "$here/com.lockedin.fitsync.plist.template" "$plist" "$here/fit_sync.py" "$log" "$watch" "$py" <<'PY'
import sys
src, dst, script, log, watch, py = sys.argv[1:]
t = (open(src).read().replace("__PYTHON__", py).replace("__SCRIPT__", script)
     .replace("__LOG__", log).replace("__WATCH_PATHS__", watch))
open(dst, "w").write(t)
PY

launchctl bootout "gui/$(id -u)/com.lockedin.fitsync" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "Installed. Log: $log"
echo
echo "Now give Full Disk Access to this exact file (System Settings → Privacy & Security → Full Disk Access → +,"
echo "then press Cmd+Shift+G and paste the path):"
echo "  $py"
