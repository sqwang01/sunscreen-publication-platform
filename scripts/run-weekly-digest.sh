#!/bin/bash
# Weekly sunscreen & photoprotection literature digest.
# Run by launchd (com.stevenwang.sunscreen-digest) every Monday 06:00 local time,
# or manually: bash scripts/run-weekly-digest.sh
set -u

REPO="/Users/stevewang/Desktop/Ai Project 2026/sunscreen publication Platform"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin"

LOGDIR="$REPO/scripts/logs"
mkdir -p "$LOGDIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/$STAMP.log"

{
  echo "=== weekly digest run: $(date) ==="
  cd "$REPO" || { echo "cannot cd to repo"; exit 1; }

  echo "--- syncing repo ---"
  git pull --rebase --autostash origin main 2>&1 || echo "git pull failed (continuing)"

  echo "--- running claude ---"
  claude -p "$(cat "$REPO/scripts/digest-prompt.md")" \
    --permission-mode bypassPermissions \
    --allowedTools Bash Read Write Edit Glob Grep WebFetch WebSearch \
    --output-format text 2>&1
  STATUS=$?

  echo "--- claude exit: $STATUS ---"
  echo "--- final git log ---"
  git log --oneline -3 2>&1
  echo "=== done: $(date) ==="
  exit $STATUS
} | tee "$LOG"

cp "$LOG" "$LOGDIR/last-run.log"
