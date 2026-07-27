# AGENTS.md — trik-lobe-server

## Project

Desktop TCP server that runs ML inference (ONNX/TFLite) and sends results to TRIK robots.
Entrypoint: `TRIKLobeServer.py`. Package: `lobe_server/`.

## Commands

```bash
uv sync                      # install everything (Python 3.12 required)
uv sync --frozen             # CI: use locked versions
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mdformat README.md MODERNIZATION.md AGENTS.md --check  # markdown (explicit list, no --exclude flag)
uv run basedpyright .        # typecheck (strict mode, 0 errors expected)
uv run pylint lobe_server TRIKLobeServer.py tests  # code quality (10.00 expected)
uv run bandit -r lobe_server/ TRIKLobeServer.py --skip B107  # security scan
uv run vulture lobe_server/ tests/ TRIKLobeServer.py  # dead code detection
uv run pytest                         # tests + coverage (config in pyproject.toml)
uv run pyinstaller TRIKLobeServer.py --onefile --icon=trik-studio.ico
```

**Required order:** `ruff → mdformat → basedpyright → pylint → bandit → vulture → pytest`.

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
- If docs changed: run `uv run mdformat AGENTS.md README.md MODERNIZATION.md --check`
- If adding new tool/config: update this Hooks section
- Check if `uv.lock` should be committed (dependency changes)
- Check if `pyproject.toml` should be committed (config changes)

### Before push

- Check for useless files: `git status` — review all staged/unstaged changes
- Check for secrets: `git diff --cached` — ensure no API keys, tokens, passwords
- Check if `uv.lock` changed (dependency updates)
- Check if `pyproject.toml` changed (tool config updates)
- Run `git diff --stat` to understand scope of changes
- Run full pre-push analysis: `uv run ruff check . && uv run pytest`
- **What I have learned:** Review lessons learned, suggest improvements
- Squash merge if mistake (ignored files, secrets): `git reset --soft HEAD~1 && git commit`
- Feature branches: unsigned push allowed for CI
- Never push to main directly

### Before branch

- Create feature branch from main: `git checkout main && git pull && git checkout -b feat/name`
- Branch naming: `feat/description`, `fix/description`, `docs/description`
- Keep feature branches focused (one idea per branch)

### Before PR

- Read PR discipline: PR titles, PR descriptions, PR size and focus
- Re-validate: `uv run ruff check . && uv run pytest`
- Ensure AGENTS.md updated with any new decisions/patterns
- Check if PR title follows Conventional Commits format
- Check if PR description has "Out of scope" section
- Run `git log --oneline -5` to review commits
- Sign commits (no `--no-sign` for PRs)
- Commit hypothesis in feature-branches for temporary knowledge storage

### Before test

- Ensure dependencies synced: `uv sync`
- Run full suite: `uv run pytest`
- Or single test: `uv run pytest tests/test_model.py::test_name -x`

### After CI failure

- Check ruff (lint), basedpyright (types), pylint (quality)
- Check bandit (security), vulture (dead code)
- Check pytest (tests + coverage)
- Runner-specific: check platform differences (Windows/macOS/Linux)
- Check if failure is platform-specific (Windows/macOS/Linux)
- Check if failure is flaky (retry once)

### After push (retrospective)

- Analyze what decisions were wrong or unexpected
- What tests were hard to write? Suggest improvements
- What code was hard to understand? Suggest comments
- What decisions were made that should be documented?
- What patterns emerged that should be added to AGENTS.md?
- Small code comments are fine to prevent bias
- Improve yourself with retrospective and hooks

### After merge

- Update local main: `git checkout main && git pull`
- Delete merged feature branch: `git branch -d branch-name`

## Python version

**Must use Python 3.12** — Python 3.14 breaks `onnx` (no wheel, C++ build fails).
Pinned in `.python-version` (single source of truth — never hardcode in CI YAML).

## Architecture

- `lobe_server/model.py`: Dual backend — `ONNXImageModel` (onnxruntime) and
  `TFLiteImageModel` (ai_edge_litert). Auto-detects format by scanning for
  `.onnx` or `.tflite` files. Labels from `labels.txt` (one per line), with
  fallback to `signature.json` → `classes.Label` (legacy Lobe compat).
  `ai_edge_litert` is a mandatory dependency.
- `lobe_server/server.py`: `LobeServer` — TCP server with asyncio event loop.
  `run_forever()` retries on connection failure after `RECONNECT_DELAY=3s`.

## Tests

87 tests, 100% coverage. All mock-based — no real camera, network, or TFLite.
Run single test: `uv run pytest tests/test_model.py::test_onnx_model_load_with_signature_json -x`.

`reportMissingTypeStubs`, `reportUnknownMemberType`, etc. set to `"none"` in
pyproject.toml because numpy/onnxruntime/pytest have no stubs — intentional,
0 errors expected.

### Test coverage notes

- Coverage config is single-sourced in `pyproject.toml`: `addopts = "--cov"`,
  `source = ["lobe_server"]`, `fail_under = 100`. CI runs bare `uv run pytest`.
  To skip coverage locally: `uv run pytest --no-cov`.
- WebcamCamera.__init__ requires cv2 (native C extension) — tests bypass it
  with `patch.object(WebcamCamera, "__init__", return_value=None)`.
  To reach 100%, use `@patch.dict("sys.modules", {"cv2": mock_cv2})`.
- `load_model` had dead code (TFLite fallback unreachable after ONNX early
  return). Removed, not tested.
- `_handle_connection` cancel loop (pending task cancellation) requires a
  blocking prediction so tasks are still pending when reader finishes.
  Use `threading.Event` to block `camera.capture()` in `asyncio.to_thread`.
- C-level builtins (e.g. `socket.getsockname`) can't be patched on
  instances — `patch.object` raises "read-only attribute". Patch the
  class instead: `patch.object(socket.socket, "getsockname", ...)`.
- `asyncio.wait(FIRST_COMPLETED)` silently swallows task exceptions:
  if task A raises but B completes first, the exception is lost and
  tests appear to pass. When you need to verify a task succeeds,
  `await` it directly instead of wrapping in `asyncio.wait`.

## Guardrails

### Docs before PR

This session context is ephemeral — all state is lost when the conversation ends.
**AGENTS.md MUST be updated before any PR is created.** Never rely on chat history
to preserve decisions, rationale, or patterns. If a change affects CI, toolchain,
architecture, or conventions, document it in AGENTS.md first.

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
- **PRs**: never use `--no-sign` (signing required for merge approval)
- **main branch**: never push directly — only merge via PR
- Push unsigned for CI runs on feature branches
- Always ask if doubt, always ask if unsure

### Commit signing

- **Feature branches**: may use `--no-sign` to prevent GPG lock
- **Push unsigned**: allowed for CI runs (feature branches)
- **PRs**: never use `--no-sign` (signing required for merge)
- **main branch**: never push directly

### Merge discipline

- Keep history clean for main branch with squash-merge if merging PRs
- Merge to main only by direct explicit command by user
- Otherwise — no merge to main
- Always ask if doubt, always ask if unsure

### Continuous improvement

- **Always learn, always improve**
- Retrospective after push: analyze decisions, suggest improvements
- Document lessons learned in this section
- Update Hooks section when new patterns emerge

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

### Cross-platform

This project runs on Windows, macOS, and Linux. CI tests on all three.
When writing code or tests that touch OS-level APIs (sockets, files,
processes), always consider platform differences. `socket.socketpair()`
returns AF_INET on Windows but AF_UNIX on macOS/Linux, which changes
`getsockname()` behavior. Local tests on one OS are not proof the
code works on others.
