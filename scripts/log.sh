#!/usr/bin/env bash
# Run a command with a timestamped full-output log in .tmp/.
# Usage: bash scripts/log.sh <command> [args...]
# Example: bash scripts/log.sh uv run pytest --cov
# Full log: .tmp/<command-pattern>-<HHMMSS>.log
# Terminal: last 15 lines (enough for pass/fail signal)

set -eu
mkdir -p .tmp
PATTERN=$(echo "$*" | sed 's/[^a-zA-Z0-9]/_/g' | head -c 80)
LOG=".tmp/${PATTERN}-$(date +%H%M%S).log"
echo "    → .tmp/${PATTERN}-$(date +%H%M%S).log" >&2
"$@" 2>&1 | tee "$LOG" | tail -15
exit "${PIPESTATUS[0]}"
