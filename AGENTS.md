# AGENTS.md — trik-lobe-server

<!-- encoding: utf-8 -->

Scope: Action triggers, guardrails, commands, and quirks for AI agents.
Aim: Every session starts knowing what to do and how to behave.
Structure: Hooks (action triggers) → Guardrails (rules) → Reference (commands,
architecture, CI, Python version) → Agent memory (tooling patterns).

Every line must answer: "Would an agent likely miss this without help?" If not, cut it.
Removing a documented rule changes agent behavior — only delete if provably incorrect.

## Hooks

Action triggers for AI agents. Before/when/after each action, follow the
corresponding hook. Keep this section updated when workflows change.

**Managing this section:** When adding/removing tools, changing configurations,
or learning new patterns, update this section and the corresponding reference
file (`.pre-commit-config.yaml`, `.github/workflows/`, etc.).

### On session init

- Read this Hooks section completely
- Read entire Guardrails section
- Read `pyproject.toml` to understand tool configuration
- Check `.github/workflows/` for CI setup
- Check `.pre-commit-config.yaml` for hooks
- Never talk to user before session warm-up complete

### Priority tasks (when asked)

- Check main branch CI status: `gh run list --branch main --limit 5`
- Check security alerts: `gh api repos/{owner}/{repo}/dependabot/alerts --jq '.[] | "\(.state) \(.security_advisory.severity) \(.dependency.package.name)"'`

### PR review (when asked)

- List open PRs: `gh pr list --state open`
- Suggest PRs for review based on age, size, or priority

### Before commit

- No need to run pre-commit hooks (installed to git, runs automatically)
- If docs changed: run `uv run mdformat README.md AGENTS.md TESTING.md DESIGN_DECISIONS.md --check`
- If adding new tool/config: update this Hooks section
- If editing or reorganizing AGENTS.md: diff against the original
  (`git diff HEAD -- AGENTS.md`), review every removed/modified line,
  and confirm each deletion was intentional — not an accidental drop
- When replacing a section, check if parts of the old content should
  be merged into the new rather than deleted outright
- Check if `uv.lock` should be committed (dependency changes)
- Check if `pyproject.toml` should be committed (config changes)

### Before push

- Check for useless files and secrets: `git status && git diff --cached`
- Check if config files changed: `git diff --stat`
- Run pre-push analysis: `uv run ruff check . && uv run pytest`
- Review lessons learned, suggest improvements
- Squash merge if mistake: `git reset --soft HEAD~1 && git commit`
- Never push to main directly

### Before branch

- Create feature branch from main: `git switch main && git pull && git switch --create feat/name`
- Branch naming: `feat/description`, `fix/description`, `docs/description`
- Keep feature branches focused (one idea per branch)

### Before PR

- Read PR discipline: PR titles, PR descriptions, PR size and focus
- Fetch and rebase to upstream main: `git fetch origin && git rebase origin/main`
  or `git pull --rebase origin main`
- Re-validate: `uv run ruff check . && uv run pytest`
- Ensure docs and code are in sync — any change affecting config, dependencies, public interface, or workflow must update README.md and/or AGENTS.md
- Ensure AGENTS.md updated with any new decisions/patterns
- Check if PR title follows Conventional Commits format
- Check if PR description covers root cause, profit, trade-offs, and verification
- Check if PR description has "Out of scope" section
- Run `git log --oneline --max-count=5` to review commits
- Sign commits (always sign for PRs — `--no-gpg-sign` is for feature branches only)
- Commit hypothesis in feature-branches for temporary knowledge storage

### Before test

- Ensure dependencies synced: `uv sync`
- Run full suite: `uv run pytest`
- Or single test: `uv run pytest tests/test_model.py::test_name --exitfirst`

### After CI failure

- Check each tool: ruff, basedpyright, pylint, bandit, vulture, pytest
- Check if failure is platform-specific (Windows/macOS/Linux)
- Check if failure is flaky (retry once)
- Check pytest coverage output
- **Error triage**: after any unexpected error, ask "Was this expected?
  Would I have been surprised if it succeeded?" If unexpected, stop and
  investigate — root cause first, fix second, skip third.

### PR finalization (after CI green)

- Review PR description for mojibake, encoding, or broken links
- If description was passed via CLI, verify with `gh pr view --json body`
- Sign the final commit: `git commit --amend --no-edit -S` (staged changes only)
- Push signed commit
- Mark PR as ready for review

### After push (retrospective)

- Analyze decisions, suggest improvements
- Suggest comments for unclear code
- Suggest docs updates for non-obvious patterns
- Update AGENTS.md with new patterns

### After merge

- Squash merge the PR: `gh pr merge <N> --squash --subject "<subject>" --body "<body>"`
- Check main branch CI status: `gh run list --branch main --limit 3`
- **If main CI fails**: treat as highest priority — fix immediately, don't move on
- Update local main: `git switch main && git pull`
- Delete merged feature branch: `git branch --delete branch-name`

## Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff check --fix` + `ruff-format` automatically.
CI runs `mdformat --check` on explicit file list.

## Guardrails

### PR description

This session context is ephemeral — all state is lost when the conversation ends.
**AGENTS.md MUST be updated before any PR is created.** Never rely on chat history
to preserve decisions, rationale, or patterns. If a change affects CI, toolchain,
architecture, or conventions, document it in AGENTS.md first.

PR description must cover:

- **Root cause** — what problem does this solve?
- **Profit** — measurable benefit (numbers if possible)
- **Trade-offs** — alternatives considered and rejected
- **Verification** — proof not visible in diff or CI checks

Do NOT list changed files (visible in diff) or CI status (visible in checks).

### Pattern recurrence escalation

When a gap appears in consecutive PRs or sessions, the fix must escalate:

- 1st occurrence — **document** (update canonical doc)
- 2nd occurrence — **automate** (add CI check or pre-commit hook)
- 3rd+ occurrence — **tool config** (linter rule, structural guard)

### Temp files

Use `.tmp/` in the repository root for all temporary files (PR bodies,
scratch data, hypothesis notes). This directory is gitignored.
Never write temp files to `/tmp/` or outside the workspace — the `.tmp/`
folder survives local development and is visible to future sessions.

### Git config

- **Never touch git config** — no `git config` commands, no modifying `.git/config`
- All git configuration is managed by the user

### .gitignore

- **Never modify .gitignore without user acceptance**
- Always ask before adding or removing entries from `.gitignore`

### Branch discipline

- Always work on feature branches, never directly on main
- Branch naming: `feat/description`, `fix/description`, `docs/description`
- Keep feature branches focused (one idea per branch)
- Commit hypothesis in feature-branches for temporary knowledge storage
- Squash merge for cleanup before push if mistake (ignored files, secrets)

### Push discipline

- **Feature branches**: unsigned push allowed (`git push` without signing)
- **PRs**: never use `--no-gpg-sign` (signing required for merge approval)
- **main branch**: never push directly — only merge via PR
- Push unsigned for CI runs on feature branches
- Always ask if doubt, always ask if unsure

### Commit signing

- **Feature branches**: may use `--no-gpg-sign` to prevent GPG lock
- **Push unsigned**: allowed for CI runs (feature branches)
- **PRs**: never use `--no-gpg-sign` (signing required for merge)
- **main branch**: never push directly

### Merge discipline

- Keep history clean with squash-merge: `gh pr merge <N> --squash --subject "<title>" --body "<body>"`
- Never push a merge commit to main — always merge via GitHub API
- Merge to main only by direct explicit command by user
- Otherwise — no merge to main

### PR titles

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:
`<type>: <description>` or `<type>(<scope>): <description>`.

Use imperative mood ("add" not "added"). Keep under 50 characters.

Types: `feat`, `fix`, `refactor`, `ci`, `docs`, `test`, `chore`, `perf`.
Scope is optional — use when the change is confined to one area of the codebase
(e.g. `model`, `server`, `camera`, `deps`). Let the project's structure
dictate scope names, not a fixed list.

Link issues in the PR body with `Closes #N` or `Fixes <full-url>`.

### PR descriptions

PR descriptions document **results and non-obvious decisions**, not a
file-by-file changelog (recoverable from git diff). State the main outcome,
then explain *why* decisions were made when the reasoning isn't obvious from
the code.

Add "How to test" steps only for unobvious changes (complex logic,
multi-step reproduction). Not needed for simple fixes or small
improvements already covered by tests.

Include an "Out of scope" section when you explicitly decided *not* to
do something in this PR — documenting intentional boundaries prevents
scope creep in review.

### PR size and focus

Aim for one idea per PR. Don't mix refactors with behavior changes. Keep
diffs under 400 lines when possible — large PRs get rubber-stamped or
delayed. If a change is big, split into stacked PRs (prerequisite first,
then follow-ups).

### Documenting decisions

When you make a non-obvious choice, document it at the right level:

1. **Inline comment** in the file (CI, code, config) — immediate context
   for anyone reading that file.
1. **AGENTS.md** — short precise phrases for high-signal facts agents need.
1. **DESIGN_DECISIONS.md** — full "why" explanation with rationale and trade-offs.

### Cross-platform

This project runs on Windows, macOS, and Linux. CI tests on all three.
When writing code or tests that touch OS-level APIs (sockets, files,
processes), always consider platform differences. `socket.socketpair()`
returns AF_INET on Windows but AF_UNIX on macOS/Linux, which changes
`getsockname()` behavior. Local tests on one OS are not proof the
code works on others.

### Tooling assumptions

- Never assume tooling behaves intuitively — verify
- Shell escaping is a common trap: test with `echo` before passing to real command
- When in doubt, route through files: write to `.tmp/<file>`, pipe to command

## Architecture

- `lobe_server/model.py`: Dual backend — `ONNXImageModel` (onnxruntime) and
  `TFLiteImageModel` (ai_edge_litert). Auto-detects format by scanning for
  `.onnx` or `.tflite` files. Labels from `labels.txt` (one per line), with
  fallback to `signature.json` → `classes.Label` (legacy Lobe compat).
  `ai_edge_litert` is a mandatory dependency.
- `lobe_server/server.py`: `LobeServer` — TCP server with asyncio event loop.
  `run_forever()` retries on connection failure after `RECONNECT_DELAY=3s`.

## Commands

```bash
uv sync                      # install everything (Python 3.12 required)
uv sync --frozen             # CI: use locked versions
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mdformat README.md AGENTS.md TESTING.md DESIGN_DECISIONS.md --check  # markdown
uv run basedpyright .        # typecheck (strict mode, 0 errors expected)
uv run pylint lobe_server TRIKLobeServer.py tests  # code quality (10.00 expected)
uv run bandit --recursive lobe_server/ TRIKLobeServer.py --skip B107  # security scan
uv run vulture lobe_server/ tests/ TRIKLobeServer.py  # dead code detection
uv run pytest                         # tests + coverage (config in pyproject.toml)
uv run pyinstaller TRIKLobeServer.py --onefile --icon=trik-studio.ico
```

**Required order:** `ruff → mdformat → basedpyright → pylint → bandit → vulture → pytest`.

## Live metrics

Always query live, never hardcode:

| Metric | Command |
|--------|---------|
| Test count | `uv run pytest --tb=no -q` |
| Coverage | `uv run pytest --cov-report=term-missing` |
| CI status (main) | `gh run list --branch main --limit 1 --json conclusion` |

## CI quirks

### CI setup

`astral-sh/setup-uv` replaces both `actions/setup-python` and `pip install uv`:

- `setup-uv` installs uv with built-in caching on GitHub-hosted runners
- Python version is read from `.python-version` — never hardcoded in YAML
- `setup-uv` has a `python-version` input only when `.python-version` is absent or testing a non-default version

### Runner notes

- `windows-2019` and `macos-13` runners **no longer exist** on GitHub.
- Build runners use **oldest free** for widest binary compatibility:
  `ubuntu-22.04`, `windows-2022`, `macos-latest`.
- Test runners use **`-latest`** for newest OS coverage:
  `ubuntu-latest`, `windows-latest`, `macos-latest`.
- `macos-15-large`/`-intel` are paid "larger runners" — not on free plan.
- `macos-latest` is ARM64 (Apple Silicon).
- Build produces per-OS artifacts via PyInstaller `--onefile`.

## Python version

**Must use Python 3.12** — Python 3.14 breaks `onnx` (no wheel, C++ build fails).
Pinned in `.python-version` (single source of truth — never hardcode in CI YAML).

## Agent memory

### Tool options

- Use standard, long options for all tools to avoid bias
- Verify which options are documented before adding to commands
- Git modern commands: prefer `git switch` over `git checkout`
- Reference: `git --help`, `pytest --help`, `bandit --help`
- **When asking questions**: answer 1 must be suggested preferred solution
- **Format questions** so user can answer "yes to all, go" — save their time

### Shell escaping

- Each shell has different escape rules — never assume PowerShell behaves like bash
- PowerShell double-quoted strings: `\b` = backspace (0x08), `\n` = newline, `\r` = CR, `` ` `` = backtick escape
- When passing complex text via CLI, use file/heredoc/stdin instead of inline arguments
- For `gh` commands with long bodies: `gh pr edit <N> --body-file <path>` avoids shell escaping entirely
- Rule of thumb: if a CLI argument contains special characters (backticks, quotes, newlines), route through a `.tmp/<file>` rather than inlining

### Three solutions

- Always think of three solutions: small effort, best practice, unobvious
- Present all three to user, let them choose
- Answer 1 is always the preferred solution based on analysis

### Verification

- Verify commands work before documenting them
- Check `--help` output for standard options
- Use long options to avoid bias and ensure portability

### Progressive disclosure

- Show only what's needed at the moment
- Let agent read more when needed
- Don't overwhelm with all information upfront
- Keep context small and focused

### Continuous improvement

- **Always learn, always improve**
- Retrospective after push: analyze decisions, suggest improvements
- Document lessons learned in this section
- Update Hooks section when new patterns emerge

### Root cause analysis

When something goes wrong, trace past the surface error to one of:

- **Missing hook**: No trigger or checklist exists for this action — add one
- **Missing in docs**: The knowledge wasn't recorded — write it down
- **Forgot to search/explore**: Existing docs had the answer but weren't consulted — add a "check docs" step to the hook

Fix the root cause, not just the symptom. A surface fix without addressing the hook/doc/search gap will repeat.

### Safe updates

When evaluating whether to keep or remove existing content, apply the mirror of
root cause analysis:

- **Would removing this change agent behavior?** If yes, keep it — the rule
  exists because it was needed.
- **Is the claim provably wrong?** Only then delete or correct — verify against
  executable sources (config, workflow, code) before removing.
