#!/usr/bin/env bash
# Install git hooks — run once per session or after clone.
# Usage: bash scripts/install-hooks.sh

set -eu
HOOKS_DIR=".git/hooks"
SCRIPT_DIR="scripts"

install() {
  local src="$SCRIPT_DIR/$1"
  local dst="$HOOKS_DIR/$1"
  if [ -f "$src" ]; then
    ln -sf "../../$src" "$dst"
    chmod +x "$src"
    echo "Installed $1 hook"
  else
    echo "WARN: $src not found"
  fi
}

install "pre-push"
echo "Done. Hooks block: pushes to main, tag deletion, .omo/ artifacts."
