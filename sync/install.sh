#!/usr/bin/env bash
# Installs the launchd agent that runs sync/fit_sync.py whenever the Zwift or HealthFit folder changes,
# and every 15 minutes (StartInterval 900), plus a second one that asks the site once a minute whether
# "Check again" was pressed (fit_sync.py --poll). Reads folder paths from ~/.config/lockedin/sync.env.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
conf="$HOME/.config/lockedin/sync.env"
agents="$HOME/Library/LaunchAgents"
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

mkdir -p "$agents" "$(dirname "$log")"
for label in com.lockedin.fitsync com.lockedin.fitsync.poll; do
  "$py" - "$here/$label.plist.template" "$agents/$label.plist" "$here/fit_sync.py" "$log" "$watch" "$py" <<'PY'
import sys
src, dst, script, log, watch, py = sys.argv[1:]
t = (open(src).read().replace("__PYTHON__", py).replace("__SCRIPT__", script)
     .replace("__LOG__", log).replace("__WATCH_PATHS__", watch))
open(dst, "w").write(t)
PY

  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$agents/$label.plist"
done
echo "Installed. Log: $log"
echo
echo "Now give Full Disk Access to this exact file (System Settings → Privacy & Security → Full Disk Access → +,"
echo "then press Cmd+Shift+G and paste the path):"
echo "  $py"
