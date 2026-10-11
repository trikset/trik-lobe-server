#!/usr/bin/env bash
# check-pr.sh — verify branch is clean and ready for a PR.
# Run before: gh pr create
# Usage:      bash scripts/check-pr.sh

set -eu

BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null)
ERR=0

echo "=== Pre-PR readiness check ==="

# 1. Not on main
if [ "$BRANCH" = "main" ]; then
  echo "FAIL: On main branch. Create a feature branch:"
  echo "  git switch --create feat/<name>"
  echo "  git branch --unset-upstream"
  ERR=1
else
  echo "OK   Branch: $BRANCH"
fi

# 2. No .omo/ staged
OMO=$(git diff --cached --name-only -- .omo/ 2>/dev/null || true)
if [ -n "$OMO" ]; then
  echo "FAIL: .omo/ artifacts staged. Remove:"
  echo "  git reset -- .omo/"
  ERR=1
else
  echo "OK   No .omo/ staged"
fi

# 3. Diff doesn't contain .omo/
OMO_FILES=$(git diff HEAD --name-only -- .omo/ 2>/dev/null || true)
if [ -n "$OMO_FILES" ]; then
  echo "FAIL: .omo/ files in working tree. Add to .gitignore:"
  echo "  git update-index --assume-unchanged .omo/"
  ERR=1
fi

# 4. No force-push in recent commits
RECENT=$(git log --oneline -5 --format="%h %s")
if echo "$RECENT" | grep -qi "force\|reset\|revert"; then
  echo "WARN: Recent commits contain force-push/reset signs. Verify this PR is clean."
fi

# 5. Diff is reasonable (not too large)
COUNT=$(git diff --stat HEAD 2>/dev/null | wc -l)
if [ "$COUNT" -gt 50 ]; then
  echo "WARN: Diff is $COUNT lines. Consider smaller PRs."
fi

# 6. Branch is based on current upstream/main
BASE=$(git merge-base HEAD upstream/main 2>/dev/null || echo "unknown")
if [ "$BASE" = "unknown" ]; then
  echo "WARN: Could not verify base against upstream/main."
else
  BEHIND=$(git rev-list --count "$BASE..upstream/main" 2>/dev/null || echo "0")
  if [ "$BEHIND" -gt 0 ]; then
    echo "WARN: Branch is $BEHIND commits behind upstream/main. Rebase:"
    echo "  git fetch upstream && git rebase upstream/main"
  else
    echo "OK   Branch is up to date with upstream/main"
  fi
fi

echo ""
if [ "$ERR" -eq 1 ]; then
  echo "FAIL: Fix the issues above before creating a PR."
else
  echo "OK: Ready for PR."
fi
exit "$ERR"