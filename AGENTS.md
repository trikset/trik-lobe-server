# AGENTS.md — trik-lobe-server

<!-- encoding: utf-8 -->

Scope: Action triggers, guardrails, and commands for AI agents.
Memory: Details, architecture, design decisions, and quirks explanations live
in `MEMORY.md` (pull sections on demand) — never duplicate rationale here.

Every line must answer: "Would an agent likely miss this without help?" If not, cut it.
Removing a documented rule changes agent behavior — only delete if provably incorrect.

## Hooks

Action triggers for AI agents. When adding/removing tools or changing
configurations, update this section and the referenced config files
(`.pre-commit-config.yaml`, `.github/workflows/`, etc.).

### On session init

- Read Hooks + Guardrails, `pyproject.toml`, `.github/workflows/`,
  `.pre-commit-config.yaml`, and `MEMORY.md` header + section list (pull
  sections on demand)
- Never talk to user before session warm-up complete

### Priority tasks / PR review (when asked)

- Main CI status: `gh run list --branch main --limit 5`
- Security alerts: `gh api repos/{owner}/{repo}/dependabot/alerts --jq '.[] | "\(.state) \(.security_advisory.severity) \(.dependency.package.name)"'`
- List open PRs: `gh pr list --state open`; suggest by age, size, or priority

### Before commit

- Fresh clone: `uv run pre-commit install` once; run all hooks with
  `uv run pre-commit run --all-files` (see Pre-commit hooks)
- New tool/config → update this Hooks section
- Editing or reorganizing AGENTS.md: `git diff HEAD -- AGENTS.md`, review every
  removed/modified line — confirm each deletion is intentional; when replacing
  a section, merge old content into the new rather than deleting outright
- Dependency changes → commit `uv.lock`; config changes → commit `pyproject.toml`

### Before push/PR

- Branch from main: `git switch main && git pull && git switch --create feat/name`; name `feat/`, `fix/`, or `docs/` + description; branch from the dependent PR's branch if stacked
- Rebase onto the real upstream tip: `git fetch origin && git rebase origin/main`; confirm the base first (`git merge-base HEAD origin/main`) — rebasing onto an ancestor replays merged commits
- Review PR discipline (titles, descriptions, size/focus) and commits: `git log --oneline --max-count=5`
- Check for useless files/secrets: `git status && git diff --cached`; config changes: `git diff --stat`
- Re-validate: `uv run ruff check . && uv run pytest`
- Squash-fix mistakes before push: `git reset --soft HEAD~1 && git commit`
- Never push to main directly
- Docs and code stay in sync: config/dependency/public-interface/workflow changes update README.md, AGENTS.md, and/or MEMORY.md; if `.github/workflows/` changed, grep docs for stale claims
- **Docs drift review**: `git diff HEAD -- AGENTS.md` — every added line must pass the boundary test; read AGENTS.md top-to-bottom for generalization and extract detail/rationale into MEMORY.md
- Sign commits for PRs (see "Commit signing & merge")

### Before test / command

- `uv sync`; full suite `uv run pytest`; single test
  `uv run pytest tests/test_model.py::test_name --exitfirst`
- Re-read the relevant guardrail for known-pitfall command types (Shell
  escaping, temp files, `gh` PR bodies)
- When in doubt, route through `.tmp/<file>` rather than inline arguments

### On tool error / after CI failure

- `fatal:`, `error:`, or non-zero exit: **stop immediately**; identify the root
  cause before proceeding
- Script/command bug: fix → update AGENTS.md (rules) or MEMORY.md (details) now
  → re-run to verify → continue
- Transient infra failures (DNS, network, CI outage) ≠ code errors: verify local
  state, retry with backoff, then report — don't blindly repeat the command
- CI failure: check each tool (ruff, basedpyright, pylint, bandit, vulture,
  pytest), platform-specificity, flakiness (retry once), and coverage output
- **Error triage**: after any unexpected error ask "Was this expected? Would I
  have been surprised if it succeeded?" If unexpected, stop and investigate —
  root cause first, fix second, skip third.

### PR finalization (after CI green)

- Review PR description for mojibake, broken links; verify CLI-passed bodies
  with `gh pr view --json body`
- Head commits must be signed: `git log --format=%G? origin/main..HEAD` — all
  `G`; re-sign any `N` before merge
- Stacked PR (base != main): add "Depends on #N" to the description
- After pushing new commits, update the body (stale bodies mislead):
  `gh pr edit <N> --body-file .tmp/pr-body.md`
- Sign the final commit (`git commit --amend --no-edit -S`, staged only),
  push, mark PR ready for review

### After push (retrospective)

- Analyze decisions; suggest comments for unclear code and docs for non-obvious
  patterns
- Capture every rule deviation/missing rule NOW — end with AGENTS.md/MEMORY.md
  updated or an explicit decision not to

### After merge

- Squash merge: `gh pr merge <N> --squash --subject "<title>" --body "<body>"`
- Check main CI: `gh run list --branch main --limit 3` — **if main CI fails,
  fix immediately, don't move on**
- Update local main: `git switch main && git pull`; delete the merged branch:
  `git branch --delete branch-name`

### Before release

- Gates: 0 open PRs, 0 security alerts, green main CI
- Version = zero-filled date: set `pyproject.toml` to `YY.MM.DD` on the release
  branch (`YY.MM.DD.dev0` on main); commit, tag `vYY.MM.DD`, push the tag
- The `v*` tag triggers the `release` job (3 platform binaries + DRAFT release
  with LLM-generated notes) — details: MEMORY.md CI quirks + `release-notes` skill
- **Review/edit the draft notes**, then publish manually — never auto-published

## Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff` (`uv run ruff check --fix`),
`ruff-format`, and `mdformat` as local hooks via the venv, plus remote
`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, and `uv-lock`.
Install once: `uv run pre-commit install`; run all: `uv run pre-commit run --all-files`. On Windows PowerShell, check markdown via the hook:
`uv run pre-commit run mdformat --all-files`.

## Guardrails

### PR description

Session context is ephemeral — update AGENTS.md (rules) or MEMORY.md (details)
BEFORE creating any PR; never rely on chat history to preserve decisions.

Cover: **Root cause** (traced to the actual reason — missing check, missing doc,
wrong assumption; not "various X accumulated"), **Profit** (measurable, numbers
if possible), **Trade-offs** (alternatives rejected), **Verification** (proof
not visible in diff/CI). Do NOT list changed files, CI status, or commit hashes
(all visible elsewhere). Base not `main`? Add "Depends on #N".

### PR discipline

**Titles:** [Conventional Commits](https://www.conventionalcommits.org/)
`<type>: <description>` or `<type>(<scope>): <description>`; imperative mood;
under 50 chars. Types: `feat`, `fix`, `refactor`, `ci`, `docs`, `test`,
`chore`, `perf`. Scope optional, project-structure-driven (e.g. `model`,
`server`, `camera`, `deps`). Link `Closes #N` / `Fixes <url>`. Superseding PR:
add `Closes #N` — `Supersedes` is **not** a closing keyword.

**Descriptions:** document **results and non-obvious decisions**, not a
file-by-file changelog (recoverable from git diff); explain *why* when not
obvious from code. "How to test" only for unobvious changes. Add an "Out of
scope" section for explicit non-goals. Squash-merge body carries root cause,
profit, trade-offs, verification, out of scope.

**Size and focus:** one idea per PR; don't mix refactors with behavior changes;
keep diffs under 400 lines. Big changes → stacked PRs (prerequisite first). New
distinct work → new branch/PR, never append to an open one.

### Repo hygiene

- Use `.tmp/` (repo root, gitignored) for all temporary files (PR bodies,
  scratch, hypothesis notes) — never `/tmp/` or outside the workspace
- **Never touch git config** (`git config`, `.git/config`) — managed by the user
- **Never modify .gitignore** without user acceptance
- Always work on feature branches, never directly on main; one idea per branch;
  commit hypothesis in feature-branches; squash-fix mistakes before push

### Commit signing & merge

- **Feature branches**: may use `--no-gpg-sign` for early CI-only pushes to
  avoid GPG lock; push unsigned for CI runs only before a PR exists
- **Before PR**: re-sign branch commits made with `--no-gpg-sign`:
  `git rebase --exec 'git commit --amend --no-edit -S' <base>`, then verify
  `git log --format=%G? origin/main..HEAD` shows all `G`
- **PRs**: never use `--no-gpg-sign`; head commits must be signed
- **main**: never push directly; merge only via GitHub API squash merge, and
  only by a direct explicit user command
- **Never `--admin`-merge unsigned commits**; `--admin` (signed only) still
  needs a direct explicit unbiased user prompt — it bypasses required reviews
- Squash-merge subject uses Conventional Commits (\<50 chars); the body carries
  the PR-description info, not just a file changelog

### Stacked PRs (squash merge)

Merging A → B → C → main: **merge bottom-up** (the `main`-targeting PR first)
and **gate on CI** after each merge. `--delete-branch` auto-closes the next PR
(base branch gone) — full recovery procedure: see MEMORY.md Workflows.

### Documenting decisions

Non-obvious choices get documented at the right level:

1. **Inline comment** in the file — immediate context
1. **AGENTS.md** — short precise rules agents need
1. **MEMORY.md** — full "why", rationale, and trade-offs

**AGENTS.md stores rules/constraints only — never rationale.** If a line
explains *why* instead of *what to do*, it's in the wrong file. Boundary test:

- A rule needing a concrete value (name, number, command arg) must be a pointer
  — `see MEMORY.md <section>` — never the value itself
- If the agent behaves correctly without the line loaded and only needs it for
  a specific task, it belongs in MEMORY.md
- A line that explains *why* is rationale → goes to MEMORY.md; removing it
  without relocating is a loss

**Verify toolchain/dependency-manager names against executable sources**
(`pyproject.toml`, `uv.lock`) before writing them into any doc — a config value
is not the project's ecosystem (see MEMORY.md CI quirks for the Dependabot
example).

- README is end-user-facing only (install, settings, usage, models, releases);
  at most a small "For developers" section

### Global conventions

- SIMPLE ENGLISH for all globally-visible content (release notes, PR
  descriptions, commits, docs, comments); EXCEPTION: reply to GitHub
  issues/comments in the language the author used
- Windows, macOS, and Linux — CI tests all three; when code/tests touch OS
  APIs (sockets, files, processes), consider platform differences (see
  TESTING.md); local tests on one OS don't prove the others

### Tooling assumptions

- Never assume tooling behaves intuitively — verify; "probably supported" is
  not supported. Before proposing a config key, CLI flag, or framework feature,
  confirm it exists in docs, `--help`, or schema with a read-only probe
- Shell escaping is a common trap: test with `echo` before passing to a real
  command; if an argument contains special characters (backticks, quotes,
  newlines), route through `.tmp/<file>` rather than inlining
- Re-read `.md` diffs after mdformat: line-start `+`/`-`/`*` mid-paragraph get
  reflowed into lists — never start a wrapped line with a list character
- `coverage.py` `exclude_lines` REPLACES the default exclusions (incl.
  `if TYPE_CHECKING:`); use `exclude_also` to add to the defaults instead

### Decision-making

- **When unsure or in doubt, ask the user** — never guess or assume intent
- **Default to conservative**: if an action risks code, tests, architecture, or
  the product, postpone and discuss rather than act
- **"run auto"**: execute fully and accurately without questions — but still
  postpone anything genuinely biased or uncertain
- **Self-verify first**: check doubts yourself with read-only experiments
  before asking
- Before proposing async/concurrency fixes, read the actual loop (`await`
  semantics) — a sequential await does not saturate a thread pool
- Offer three solutions (small effort, best practice, unobvious); present all
  three, answer 1 = preferred; format questions so the user can answer
  "yes to all, go"

### Reviewers & suppressions

GitHub's `github-code-quality` bot reads `.github/copilot-instructions.md` +
`AGENTS.md` from the PR head branch — align it there but treat as
**best-effort**. Do **not** change code to satisfy it if it breaks our gates
(100% coverage, ruff ALL, basedpyright strict) — that's a false positive:
dismiss the thread, don't degrade the code. See MEMORY.md "GitHub AI reviewer
(code-quality) alignment".

Every in-code suppression (`# noqa`, `# type: ignore`, `# pylint: disable`,
`# nosec`) must carry a reasoning comment; `# pyright:`/`# pylint: disable`
file headers are the test-scoped relaxation mechanism. Production linters run
full strictness — scope relaxations to tests for pytest idioms. Full inventory:
MEMORY.md "Suppression audit".

## Memory index

Details live in `MEMORY.md` — pull a section on demand:

| Topic | Section in MEMORY.md |
|-------|----------------------|
| Model loading, connection protocol | Architecture |
| CI quirks, runner notes, release flow | CI quirks |
| Stacked PR recovery | Workflows |
| Rationale and trade-offs for choices | Design decisions |
| Python version constraint | Python version (below) |

`python-app.yml` is the single workflow file — job guards: see MEMORY.md
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
uv run bandit --recursive lobe_server/ TRIKLobeServer.py  # security scan
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

### Tooling & verification

- Use standard, long options for all tools (bias-free, portable); verify
  options against `--help` before adding them to commands; verify commands
  work before documenting them
- Prefer modern git: `git switch` over `git checkout`
- When claiming a refactor reduces SLOC/complexity/test-count, measure before
  and after; if a consolidation backfires, revert it. Report measured deltas,
  not estimates
- **When presenting suggestions/choices**, use numbered items (1, 2, 3) or
  letters (A, B, C), mark the recommended option, and format so the user can
  answer in one line: "yes to all", "just 1 and 3", or "go A and D"

### Shell escaping

- Each shell has different escape rules — never assume PowerShell behaves like
  bash. PowerShell double-quoted strings: `\b` = backspace (0x08), `\n` =
  newline, `\r` = CR, `` ` `` = backtick escape
- Complex text via CLI → file/heredoc/stdin instead of inline arguments; `gh`
  long bodies → `gh pr edit <N> --body-file <path>` avoids escaping entirely
- **Commit messages with special chars** — PowerShell interprets `-1`,
  backticks, and quotes in `git commit -m` as command syntax. Always use
  `git commit --file .tmp/msg.txt` for non-trivial messages

### Progressive disclosure

Show only what's needed at the moment; let the agent read more when needed;
keep context small and focused. (Docs-structure contract: AGENTS.md = pointers,
MEMORY.md = on-demand detail.)

### Process improvement

- **Every error must leave a trace**: before moving on, capture the lesson in
  AGENTS.md (rules) or MEMORY.md (details)
- **Check if this has happened before**: grep AGENTS.md and MEMORY.md for the
  error type before crafting a fix
- **Keep patterns general**: phrase bullets to catch similar future cases, not
  the exact one-time scenario
- **Store only high-signal, expensive-to-rediscover facts**; prefer concepts
  over exact numbers/line-numbers — they drift silently. When adding a rule,
  grep for entries it makes stale and migrate them
- **Verify tooling "installed/runs automatically" claims against the
  environment** — a config file existing is not the same as the tool being
  active; confirm with a command
- **Gaps escalate**: 1st occurrence — document (canonical doc); 2nd —
  automate (CI check or pre-commit hook); 3rd+ — tool config (linter rule,
  structural guard)
- **Root cause analysis**: when something goes wrong, fix the root cause, not
  the symptom — a surface fix repeats; re-run the failed command to verify.
  Trace past the surface error to one of:
  - **Missing hook** — no trigger/checklist exists — add one
  - **Missing in docs** — knowledge wasn't recorded — write it down
  - **Forgot to search/explore** — add a "check docs" step to the hook
  - **Ignored error signal** — tool produced `fatal:` but execution continued —
    add an "On tool error" hook
- **Safe updates** (mirror of root cause analysis when removing content):
  - **Would removing this change agent behavior?** If yes, keep it
  - **Is the claim provably wrong?** Only then delete/correct — verify against
    executable sources (config, workflow, code)
  - **Does it enforce a docs/structure contract?** Keep structural-convention
    rules (e.g. Progressive disclosure) even when the wording looks generic
  - **Rationale must never be deleted** — when removing a line that is
    rationale/detail (not a rule), relocate it to MEMORY.md, not drop it; if it
    wouldn't be re-derivable later, it belongs in MEMORY
