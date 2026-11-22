#!/usr/bin/env bash
# ============================================================================
# install_launchd.sh
#
# Generates and installs three macOS launchd jobs:
#   com.<user>.clips.clip.weekly    - Sunday 03:00 local time, run clip pipeline
#   com.<user>.clips.post.3pm       - Daily 15:00 local time, post one clip
#   com.<user>.clips.post.8pm       - Daily 20:00 local time, post one clip
#
# Survives reboots. Runs even when nobody is logged in to a GUI session as
# long as the Mac is awake. Use `pmset schedule` (see README) to wake the
# Mac from sleep ahead of each job.
#
# This script is safe to re-run; existing plists are overwritten.
# ============================================================================
set -euo pipefail

# --- Resolve paths ----------------------------------------------------------

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: python3 not found on PATH." >&2
  exit 1
fi

# Use the user's username for the plist label.
USER_LABEL="${USER:-$(whoami)}"
LABEL_PREFIX="com.${USER_LABEL}.clips"

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

# Optional: where to send stdout/stderr logs. Default to project logs dir.
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "Project dir : $PROJECT_DIR"
echo "Python      : $PYTHON_BIN"
echo "Log dir     : $LOG_DIR"
echo "Label prefix: $LABEL_PREFIX"
echo

# --- Plist generator --------------------------------------------------------

gen_plist() {
  local label="$1"
  local hour="$2"
  local minute="${3:-0}"
  local weekday="$4"   # empty = every day, 0=Sunday
  local program_args_5="$5"   # e.g. "run"
  local program_args_6="$6"   # e.g. "--limit 2"

  local weekday_xml=""
  if [[ -n "$weekday" ]]; then
    weekday_xml="      <key>Weekday</key><integer>$weekday</integer>"
  fi

  cat > "$LAUNCH_AGENTS_DIR/${label}.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>WorkingDirectory</key>
  <string>${PROJECT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>cli.py</string>
    <string>${program_args_5}</string>
    <string>${program_args_6}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>${hour}</integer>
    <key>Minute</key><integer>${minute}</integer>
${weekday_xml}
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/${label}.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/${label}.err.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST
}

# --- Three jobs -------------------------------------------------------------

WEEKLY_LABEL="${LABEL_PREFIX}.clip.weekly"
THREE_PM_LABEL="${LABEL_PREFIX}.post.3pm"
EIGHT_PM_LABEL="${LABEL_PREFIX}.post.8pm"
WATCHER_LABEL="${LABEL_PREFIX}.watcher"
CLEANUP_LABEL="${LABEL_PREFIX}.cleanup"

# Weekly clip run: Sunday 03:00 local time, --limit 2 (process up to 2 videos)
gen_plist "$WEEKLY_LABEL" 3 0 0 "run" "--limit 2"

# Daily 15:00 post
gen_plist "$THREE_PM_LABEL" 15 0 "" "post" ""

# Daily 20:00 post
gen_plist "$EIGHT_PM_LABEL" 20 0 "" "post" ""

# --- Live watcher (always-on daemon) + cleanup (hourly) ---------------------
# These have different plist shapes, so they're written directly.

cat > "$LAUNCH_AGENTS_DIR/${WATCHER_LABEL}.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${WATCHER_LABEL}</string>
  <key>WorkingDirectory</key>
  <string>${PROJECT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>cli.py</string>
    <string>live</string>
    <string>watch</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/${WATCHER_LABEL}.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/${WATCHER_LABEL}.err.log</string>
</dict>
</plist>
PLIST

cat > "$LAUNCH_AGENTS_DIR/${CLEANUP_LABEL}.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${CLEANUP_LABEL}</string>
  <key>WorkingDirectory</key>
  <string>${PROJECT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>cli.py</string>
    <string>live</string>
    <string>cleanup</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Minute</key><integer>17</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/${CLEANUP_LABEL}.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/${CLEANUP_LABEL}.err.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST

# --- Load them --------------------------------------------------------------

unload_if_loaded() {
  local label="$1"
  if launchctl list 2>/dev/null | grep -q "^${label}\b"; then
    launchctl unload "$LAUNCH_AGENTS_DIR/${label}.plist" 2>/dev/null || true
  fi
}

for label in "$WEEKLY_LABEL" "$THREE_PM_LABEL" "$EIGHT_PM_LABEL" \
             "$WATCHER_LABEL" "$CLEANUP_LABEL"; do
  unload_if_loaded "$label"
  launchctl load "$LAUNCH_AGENTS_DIR/${label}.plist"
  echo "Loaded: $label"
done

echo
echo "Schedule (all times in your Mac's local timezone, currently $(date +%Z)):"
echo "  Weekly clip run : Sunday 03:00   -> ${WEEKLY_LABEL}"
echo "  Post slot 1     : Daily   15:00   -> ${THREE_PM_LABEL}"
echo "  Post slot 2     : Daily   20:00   -> ${EIGHT_PM_LABEL}"
echo "  Live watcher    : always on       -> ${WATCHER_LABEL}  (KeepAlive=true)"
echo "  Cleanup         : hourly at :17    -> ${CLEANUP_LABEL}"
echo
echo "Logs:    $LOG_DIR/*.log"
echo "Inspect: launchctl list | grep clips"
echo "Stop:    ${PROJECT_DIR}/launchd/uninstall.sh"
echo
echo "TIP: If your Mac sleeps at 3AM, schedule wake-ups:"
echo "  sudo pmset repeat wakeorpoweron MTWRFSU 02:55:00"
echo "  sudo pmset repeat wakeorpoweron MTWRFSU 14:55:00"
echo "  sudo pmset repeat wakeorpoweron MTWRFSU 19:55:00"
echo
echo "TIP: The live watcher must keep running even when asleep. Either:"
echo "  - Keep the Mac awake: pmset -a disablesleep 1"
echo "  - Or schedule a wake every 2 minutes (the watcher catches up on startup):"
echo "    sudo pmset repeat wakeorpoweron MTWRFSU 00:00:00,02:00:00,04:00:00,..."
