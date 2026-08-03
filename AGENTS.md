# AGENTS.md — trik-lobe-server

<!-- encoding: utf-8 -->

Scope: Action triggers, guardrails, and commands for AI agents.
Aim: Every session starts knowing what to do and how to behave.
Structure: Hooks (action triggers) → Guardrails (rules) → Reference (commands,
live metrics, Python version) → Agent behavior (tooling patterns).
Memory: Details, architecture, design decisions, and quirks explanations live
in `MEMORY.md`. Pull sections on demand — never duplicate rationale here.

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
- Read `MEMORY.md` header + section list (Architecture, CI quirks, Design
  decisions); pull sections on demand when a task touches those areas
- Never talk to user before session warm-up complete

### Priority tasks (when asked)

- Check main branch CI status: `gh run list --branch main --limit 5`
- Check security alerts: `gh api repos/{owner}/{repo}/dependabot/alerts --jq '.[] | "\(.state) \(.security_advisory.severity) \(.dependency.package.name)"'`

### PR review (when asked)

- List open PRs: `gh pr list --state open`
- Suggest PRs for review based on age, size, or priority

### Before commit

- If hooks are not installed (fresh clone), run `uv run pre-commit install`
  once — they then run automatically on every commit
- To run all hooks manually at any time: `uv run pre-commit run --all-files`
- If docs changed: run `uv run pre-commit run mdformat --all-files`
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
- If the PR depends on another unmerged PR, branch from that PR's branch instead of main
- Branch naming: `feat/description`, `fix/description`, `docs/description`
- Keep feature branches focused (one idea per branch)

### Before PR

- Read PR discipline: PR titles, PR descriptions, PR size and focus
- Fetch and rebase to upstream main: `git fetch origin && git rebase origin/main`
  or `git pull --rebase origin main`
- Re-validate: `uv run ruff check . && uv run pytest`
- Ensure docs and code are in sync — any change affecting config, dependencies, public interface, or workflow must update README.md, AGENTS.md, and/or MEMORY.md. If `.github/workflows/` changed, grep README/AGENTS/MEMORY for claims about the affected behavior and update them.
- Ensure AGENTS.md (rules) or MEMORY.md (details/rationale) updated with any new decisions/patterns
- **Docs drift review**: `git diff HEAD -- AGENTS.md` and review it hard — every added line must pass the boundary test. Then read the full AGENTS.md top-to-bottom for generalization (phrase specific one-off facts as general patterns) and extract any remaining detail/rationale into MEMORY.md.
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

### Before running a command

- If this command type has known pitfalls (Shell escaping, temp files,
  gh PR bodies), re-read the relevant guardrail section before constructing it
- When in doubt, route through `.tmp/<file>` rather than inline arguments

### On tool error during execution

- When a command outputs `fatal:`, `error:`, or exits non-zero: **stop immediately**
- Do not proceed to the next command until root cause is identified
- If the error was a script/command bug (not a real failure):
  1. Fix the immediate issue
  1. **Update AGENTS.md (rules) or MEMORY.md (details) now** — add a guardrail, hook, or Shell escaping bullet
  1. Verify the fix by re-running the failed command
  1. Only then continue with the next task
- If the root cause category is new, add it to the Root cause analysis section

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
- If this PR is stacked on another PR (base != main), add "Depends on #N" to the description
- Sign the final commit: `git commit --amend --no-edit -S` (staged changes only)
- Push signed commit
- Mark PR as ready for review

### After push to existing PR

- If new commits were pushed after the PR was created, update the PR body:
  `gh pr edit <N> --body-file .tmp/pr-body.md`
- Stale PR bodies are misleading — the description must reflect all commits

### After push (retrospective)

- Analyze decisions, suggest improvements
- Suggest comments for unclear code
- Suggest docs updates for non-obvious patterns
- Update AGENTS.md (rules) or MEMORY.md (details/rationale) with new patterns

### After merge

- Squash merge the PR: `gh pr merge <N> --squash --subject "<subject>" --body "<body>"`
- Check main branch CI status: `gh run list --branch main --limit 3`
- **If main CI fails**: treat as highest priority — fix immediately, don't move on
- Update local main: `git switch main && git pull`
- Delete merged feature branch: `git branch --delete branch-name`

### Before release

- Check release gates: 0 open PRs, 0 security alerts, green main CI
  (`gh pr list --state open`, `gh api .../dependabot/alerts`)
- On a release branch, set `pyproject.toml` version to the zero-filled date,
  e.g. `26.08.03` for tag `v26.08.03` (dev version is `YY.MM.DD.dev0` on main)
- Commit, tag `vYY.MM.DD`, push the tag
- The `release` job of `python-app.yml` (triggered by the `v*` tag) builds 3
  platform binaries and creates a DRAFT release with LLM-generated release
  notes (via the `release-notes` skill). Artifact naming and notes structure:
  see `MEMORY.md` CI quirks + the skill file.
- **Review/edit the draft notes**, then publish manually — releases are never
  auto-published

## Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff` (`uv run ruff check --fix`), `ruff-format`,
and `mdformat` as local hooks using the venv tools, plus the remote
`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, and `uv-lock`. Install
once per clone: `uv run pre-commit install`. Run all hooks manually:
`uv run pre-commit run --all-files`. On Windows PowerShell, check markdown
through the hook: `uv run pre-commit run mdformat --all-files`.

## Guardrails

### PR description

This session context is ephemeral — all state is lost when the conversation ends.
**AGENTS.md MUST be updated before any PR is created.** Never rely on chat history
to preserve decisions, rationale, or patterns. If a change affects CI, toolchain,
architecture, or conventions, document it in AGENTS.md (rules) or MEMORY.md
(details/rationale) first.

PR description must cover:

- **Root cause** — what problem does this solve? (not: "various X accumulated" —
  trace to the actual reason: missing check, missing doc, wrong assumption)
- **Profit** — measurable benefit (numbers if possible)
- **Trade-offs** — alternatives considered and rejected
- **Verification** — proof not visible in diff or CI checks

Do NOT list changed files (visible in diff) or CI status (visible in checks).
Do NOT list commit hashes (fragile, visible in PR commit tab).

Before writing the body, check: is the base `main`? If not, add
"Depends on #N" referencing the base PR.

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
- **Never use `--admin` without direct explicit unbiased user prompt** — it
  bypasses required reviews. Only apply when the user independently confirms.
- Squash-merge subject uses Conventional Commits format (\<50 chars); all useful
  info from the PR description goes into the squash body (root cause, profit,
  trade-offs, verification, out of scope), not just a file changelog.

### Stacked PRs (squash merge)

When merging a chain of stacked PRs (A → B → C → main):

- **Merge bottom-up**: the PR targeting `main` first, then each next PR.
- **After each merge, `--delete-branch` deletes the base branch → GitHub
  auto-closes the next stacked PR** (base branch gone). Recovery:
  1. Recreate the deleted base branch from `main` (`git branch <name> main; git push origin <name>`)
  1. `gh pr reopen <N>` then `gh pr edit <N> --base main`
  1. Delete the temp base branch
  1. Rebuild the head branch onto main: `git reset --hard origin/main` then
     `git cherry-pick <first-commit>^..<last-commit>` (its own commits only)
  1. `git push --force-with-lease`
- **Gate on CI**: after each merge, verify main CI is green before merging the
  next PR (`gh run list --branch main --limit 3`).
- Conflicts during rebuild are expected (main has squash content the branch
  pre-dates) — resolve by taking the intended final state, or skip commits
  already upstream (`git cherry-pick --skip`).

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
1. **MEMORY.md** — full "why" explanation with rationale and trade-offs;
   architecture details, design decisions, and CI quirks all live there.

**AGENTS.md stores rules/constraints only** — never rationale or "why"
explanations. Rationale → MEMORY.md. If a line explains *why*
instead of *what to do*, it's in the wrong file.

Operational boundary test when deciding where a line goes:

- A hook/rule line that needs a concrete value (name, number, command arg)
  must be a pointer — `see MEMORY.md <section>` — never the value itself.
- If the agent behaves correctly without the line loaded in AGENTS.md and
  only needs it for a specific task, it belongs in MEMORY.md.

**Verify toolchain/dependency-manager names against executable sources**
(`pyproject.toml`, `uv.lock`) before writing them into any doc. A config value
is not the project's ecosystem — e.g. Dependabot used `package-ecosystem: "pip"`
(its closest legacy tag) until the native `uv` tag existed.

### Language

- Use SIMPLE ENGLISH for all globally-visible content: release notes, PR
  descriptions, commit messages, docs, comments.
- EXCEPTION: reply to GitHub issues/comments in the same language the author
  used.
- Friendly small-talk is fine; keep it brief.

### Cross-platform

This project runs on Windows, macOS, and Linux. CI tests on all three.
When writing code or tests that touch OS-level APIs (sockets, files,
processes), always consider platform differences. See TESTING.md for
platform-specific test patterns (socketpair, temp files, deprecations).
Local tests on one OS are not proof the code works on others.

### Tooling assumptions

- Never assume tooling behaves intuitively — verify
- Shell escaping is a common trap: test with `echo` before passing to real command
- When in doubt, route through files: write to `.tmp/<file>`, pipe to command

### Decision-making

- **When unsure or in doubt, ask the user** — never guess or assume intent
- **Default to conservative**: if an action risks code, tests, architecture,
  or the product, postpone and discuss rather than act
- **When the user says "run auto"**: execute fully and accurately without
  questions — but still postpone anything genuinely biased or uncertain
- **Self-verify first**: check doubts yourself with read-only experiments
  before asking

## Memory index

Details live in `MEMORY.md` — pull a section on demand:

| Topic | Section in MEMORY.md |
|-------|----------------------|
| Model loading, connection protocol | Architecture |
| CI quirks, runner notes, release flow | CI quirks |
| Rationale and trade-offs for choices | Design decisions |
| Python version constraint | Python version (below) |

`python-app.yml` is the single workflow file — job guards: see `MEMORY.md`
CI quirks.

## Commands

```bash
uv sync                      # install everything (Python 3.12 required)
uv sync --frozen             # CI: use locked versions
uv run ruff check .          # lint
uv run ruff format .         # format
uv run pre-commit run mdformat --all-files   # markdown (root-level docs; PowerShell-safe)
uv run basedpyright .        # typecheck (strict mode, 0 errors expected)
uv run pylint lobe_server TRIKLobeServer.py tests  # code quality (10.00 expected)
uv run bandit --recursive lobe_server/ TRIKLobeServer.py --skip B107  # security scan
uv run vulture lobe_server/ tests/ TRIKLobeServer.py  # dead code detection
uv run pytest                         # tests + coverage (config in pyproject.toml)
uv run pyinstaller TRIKLobeServer.py --onefile --icon=trik-studio.ico  # Windows only (.ico)
```

**Required order:** `ruff → mdformat → basedpyright → pylint → bandit → vulture → pytest`.

## Live metrics

Always query live, never hardcode:

| Metric | Command |
|--------|---------|
| Test count | `uv run pytest --tb=no -q` |
| Coverage | `uv run pytest --cov-report=term-missing` |
| CI status (main) | `gh run list --branch main --limit 1 --json conclusion` |

## Python version

**Must use Python 3.12** — Python 3.14 breaks `onnx` (no wheel, C++ build fails).
Pinned in `.python-version` (single source of truth — never hardcode in CI YAML).

## Agent behavior

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
- **Commit messages with special chars** — PowerShell interprets `-1`,
  backticks, and quotes in `git commit -m` as command syntax. Always use
  `git commit --file .tmp/msg.txt` for non-trivial messages.

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

- **Every error must leave a trace**: before moving on from any unexpected
  error, ensure the lesson is captured in AGENTS.md (rules) or MEMORY.md
  (details/rationale)
- **Check if this has happened before**: grep AGENTS.md and MEMORY.md for the
  error type before crafting a fix — the solution may already be documented
- **Keep patterns general**: phrase new bullets to catch similar future
  cases, not just the exact one-time scenario
- **Store only high-signal, expensive-to-rediscover facts**: if a failure
  message, `--help`, or the config file explains it, teach rediscovery instead
  of memorializing. Every stored line has a maintenance cost — weigh it against
  the benefit.
- **Verify tooling "installed/runs automatically" claims against the
  environment** — a config file existing is not the same as the tool being
  active. Confirm with a command, not an assumption.
- **Prefer concepts over exact numbers/line-numbers in docs** — they drift
  silently; live queries and conceptual descriptions don't. When adding a new
  rule/guardrail, grep AGENTS.md and MEMORY.md for existing entries that the
  rule makes stale and migrate them to the concept form.

### Root cause analysis

When something goes wrong, trace past the surface error to one of:

- **Missing hook**: No trigger or checklist exists for this action — add one
- **Missing in docs**: The knowledge wasn't recorded — write it down
- **Forgot to search/explore**: Existing docs had the answer but weren't consulted — add a "check docs" step to the hook
- **Ignored error signal**: The tool produced `fatal:` or non-zero exit but execution continued — add an "On tool error" hook

Fix the root cause, not just the symptom. A surface fix without addressing the
hook/doc/search/error gap will repeat.

After fixing the root cause, re-run the failed command to verify.
Only then proceed to the next task.

### Safe updates

When evaluating whether to keep or remove existing content, apply the mirror of
root cause analysis:

- **Would removing this change agent behavior?** If yes, keep it — the rule
  exists because it was needed.
- **Is the claim provably wrong?** Only then delete or correct — verify against
  executable sources (config, workflow, code) before removing.
