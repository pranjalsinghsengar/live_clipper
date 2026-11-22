#!/usr/bin/env bash
# Unload and remove the three launchd jobs.
set -euo pipefail

USER_LABEL="${USER:-$(whoami)}"
LABEL_PREFIX="com.${USER_LABEL}.clips"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

for label in \
  "${LABEL_PREFIX}.clip.weekly" \
  "${LABEL_PREFIX}.post.3pm"   \
  "${LABEL_PREFIX}.post.8pm"   \
  "${LABEL_PREFIX}.watcher"    \
  "${LABEL_PREFIX}.cleanup"
do
  plist="$LAUNCH_AGENTS_DIR/${label}.plist"
  if [[ -f "$plist" ]]; then
    launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
    echo "Removed: $label"
  fi
done

echo "Done. Log files in $HOME/.../logs are not removed."
