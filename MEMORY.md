# MEMORY.md — trik-lobe-server

<!-- encoding: utf-8 -->

Scope: Main memory for AI agents — architecture, CI quirks, and design decisions.
Aim: Hold every *why* and *detail* that AGENTS.md rules refer to. AGENTS.md is
the "what to do" front door; this file is the store it points into.
Structure: Architecture → CI quirks → Design decisions (dated entries).
Use: Pull the section a task needs on demand (see AGENTS.md "On session init").
Rules live in AGENTS.md; rationale and detail live here — never in AGENTS.md.

## Architecture

### Model loading — `lobe_server/model.py`

- Dual backend: `ONNXImageModel` (onnxruntime) and `TFLiteImageModel`
  (ai_edge_litert). Auto-detects format by scanning for `.onnx` or `.tflite`
  files. `ai_edge_litert` is a mandatory dependency.
- Labels from `labels.txt` (one per line, UTF-8 BOM tolerated), with fallback
  to `signature.json` → `classes.Label` (legacy Lobe compat). See the
  "Add labels.txt → signature.json priority" decision.
- Both classes expose the same `predict()` → `.prediction` interface, so the
  call site in `server.py` is backend-agnostic. See "Remove lobe SDK".
- Three supported model directory layouts are documented in
  "Model directory layout (three supported layouts)".

### Connection protocol — `lobe_server/server.py`

- `LobeServer` is a TCP client connecting to the robot's mailbox server.
  Sends `register:<port>:<hull>`, `self:<hull>`, `keepalive` (every 5s),
  `data:<prediction>` (every 0.2s).
- Receives `self:<hull>`, `connection:<ip>:<port>:<hull>` during handshake,
  `data:quit` for shutdown, and `keepalive` every 3s from the robot —
  hardcoded in `trikNetwork/src/connection.cpp`, never negotiated.
- `_reader` is the sole health monitor: breaks on empty recv or `RECV_TIMEOUT`
  (10s, `asyncio.wait_for`). `_keepalive_loop`/`_prediction_loop` are
  outbound-only — death detection is the reader's job. Full strategy and the
  `_send` guardrail are in "Connection health detection strategy".

## CI quirks

### CI setup

`astral-sh/setup-uv` replaces both `actions/setup-python` and `pip install uv`:

- `setup-uv` installs uv with built-in caching on GitHub-hosted runners
- Python version is read from `.python-version` — never hardcoded in YAML
- `setup-uv` has a `python-version` input only when `.python-version` is absent or testing a non-default version
- setup-uv input is `enable-cache`, not `cache` — the deprecated `cache:` input is silently ignored
- `uv lock --check` is the lockfile-drift gate (CI + pre-commit) — fails when `pyproject.toml` and `uv.lock` diverge
- Dependabot ecosystem tag is `uv` (this project); uv/dependency updates are grouped into one PR per interval so a single CI run covers them
- Dependabot `uv` ecosystem has known gaps (astral-sh/uv#2512) — confirm `uv.lock`
  actually moved in dep PRs; a widened constraint with a stale lock passes `uv lock --check`
- ruff `select = ["ALL"]` auto-enables any new rules a ruff version bump adds —
  a previously-green tree failing after a bump is likely a new rule, not a code
  regression. Evaluate the rule on merit before "fixing" code.
- Changing `dependabot.yml` (e.g. adding an ignore) closes open grouped PRs and
  Dependabot regenerates them shortly after. Wait for regeneration before
  hand-creating an equivalent dep PR — manual and auto PRs overlap.
- `python-app.yml` is the single workflow file. It runs `test` on all events
  (PR, main-push, tag-push, dispatch — tag runs are rare and catch worker
  drift); `build` on non-PR pushes; `version-check` + `release` only on `v*`
  tags. The `release` job overrides permissions to `contents: write`.
- `gh` CLI in GitHub Actions needs `GH_TOKEN: ${{ github.token }}` explicitly —
  it is not auto-injected.
- `softprops/action-gh-release` reuses an existing release for a tag. When
  re-releasing the same tag, delete the release (and tag) first:
  `gh release delete <tag> --yes --cleanup-tag`, then re-tag.
- Verify the full release output, not just "workflow green" — a draft can be
  green yet carry a stale body or old assets. Check: notes structure (deps
  table, contributors, compare link), all 3 versioned assets, and the inner
  `.bin` name.
- The release flow builds 3 platform binaries and creates a DRAFT release with
  LLM-generated notes (via the `release-notes` skill); versions are zero-filled
  dates (`26.08.03` ↔ tag `v26.08.03`). Each platform ships as one archive —
  `-Windows.zip`, `-Linux.tar.gz`, `-macOS.tar.gz` — bundling the versioned
  binary (`*.exe` / `*.bin`) + `settings.ini` at the root. Drafts require
  maintainer review — never auto-publish. Skill frontmatter is preserved via
  `mdformat-frontmatter`.
- Every job runs a "Check for all tools" step (composite action) after its
  install steps — verifies worker binaries and venv packages exist and logs
  versions, failing fast if a runner lost a tool (e.g. `zip`).

### Runner notes

- `windows-2019` and `macos-13` runners **no longer exist** on GitHub.
- Build runners use **oldest free** for widest binary compatibility:
  `ubuntu-22.04`, `windows-2022`, `macos-latest`.
- Test runners use **`-latest`** for newest OS coverage:
  `ubuntu-latest`, `windows-latest`, `macos-latest`.
- `macos-15-large`/`-intel` are paid "larger runners" — not on free plan.
- `macos-latest` is ARM64 (Apple Silicon).
- Build produces per-OS artifacts via PyInstaller `--onefile`.

## Design decisions

Dated entries, each with context → decision → rationale → consequences.

### [2025-07-10] pip → uv

**Context:** The project used `pip` + `requirements.txt` with no lockfile,
no deterministic installs, and slow resolution.

**Decision:** Migrate to `uv` for all development workflows.

**Rationale:**

- 10-100× faster dependency resolution
- Built-in lockfile (`uv.lock`) for reproducible environments
- Single binary, no Python dependency to install itself
- Handles platform-specific markers and custom indexes natively

**Consequences:**

- `pyproject.toml` replaces `requirements.txt` + `dev-requirements.txt`
- `uv sync` for deterministic, fast installs
- `uv run` for all Python commands
- `uv.lock` committed for reproducible environments

### [2026-07-14] Remove lobe SDK

**Context:** The `lobe` SDK (Microsoft Lobe) was last released Feb 2022;
the entire Lobe product has been discontinued. Old pins (`pillow~=9.0.1`,
`matplotlib~=3.5.1`) blocked installation on Python ≥3.12.

**Decision:** Remove the `lobe` dependency entirely. Replace with a custom
dual-backend model loader.

**What the server actually used from `lobe`:**

```python
from lobe import ImageModel

model = ImageModel.load(path)  # read signature.json + load TFLite
result = model.predict(pil_image)  # preprocess + inference
prediction = result.prediction  # top class label string
```

**Replacement:** `lobe_server/model.py` — dual backend `ONNXImageModel` +
`TFLiteImageModel`:

1. Auto-detects model format by scanning directory for `.tflite` or `.onnx` files
1. Labels loaded from `labels.txt` (priority) or `signature.json` → `classes.Label`
1. `signature.json` may optionally contain `filename` to specify model file explicitly
1. Preprocesses images the same way Lobe did (resize + center crop + normalize)
1. Returns a `ClassificationResult` with the same `.prediction` API

The call site in `server.py` needed zero changes — both model classes expose
the same `predict()` → `.prediction` interface.

**Consequences:**

- No more `matplotlib` dependency
- `Pillow` can be any modern version
- Server works on Python 3.12
- CI no longer needs to install `lobe`
- Both ONNX and TFLite are first-class citizens

### [2026-07-14] Add ONNX runtime

**Context:** Needed a reliable ONNX inference backend for the new model loader.

**Decision:** Add `onnxruntime`.

**Rationale:**

- Pre-built wheels on PyPI for all platforms (x64 + ARM64)
- Python 3.10-3.14 support with no compilation needed
- Actively maintained by Microsoft
- Bundles cleanly with PyInstaller (auto-detected)

### [2026-07-14] Add ai-edge-litert (LiteRT)

**Context:** Needed native TFLite inference. The old stack used `tflite-runtime`
(abandoned, no Python 3.12+ wheels) or `tflite2onnx` (brittle conversion).

**Decision:** Add `ai-edge-litert`, Google's successor to TensorFlow Lite runtime.

**Rationale:**

- Pre-built wheels on PyPI for all platforms (Python 3.10-3.14)
- Fully backward compatible with all `.tflite` models
- Same API as `tflite_runtime.interpreter` — zero code changes
- C extension, bundles with PyInstaller without special handling

**Consequences:**

- `tflite-runtime` removed (abandoned, no wheels for 3.12+)
- `tflite2onnx` removed (fragile conversion step no longer needed)

### [2026-07-14] Remove matplotlib

**Context:** Only used by Lobe's `model.visualize()` (Grad-CAM heatmaps).
The server never called this method.

**Decision:** Remove `matplotlib`.

### [2026-07-14] Add labels.txt → signature.json priority

**Context:** `signature.json` was a Lobe-ism. Non-Lobe models (Teachable Machine,
Azure Custom Vision, Edge Impulse) export `labels.txt` — one label per line.

**Decision:** `_read_labels(model_path)` now has two paths, in priority order:

1. **labels.txt exists** — read labels from file (one per line)
   - UTF-8 BOM handling: `encoding="utf-8-sig"`
   - Empty line filtering: blank lines stripped
1. **No labels.txt, signature.json exists** — extract `classes.Label`

**Consequences:**

- Teachable Machine / Edge Impulse / Azure CV: export labels.txt, drop
  it next to the model, no signature.json needed
- Backward compatible: every existing Lobe model still works via
  signature.json → classes.Label

### [2026-07-14] Toolchain: ruff, pylint, basedpyright, mdformat

**Context:** The project used `flake8` + `isort` + `black` with no type checking
and no markdown formatting.

**Decision:**
| Tool | Replaces | Why |
|------|----------|-----|
| `ruff` | `flake8` + `isort` + `black` | Single tool, 100× faster, same rules |
| `pylint` | — | Strict mode for deeper code quality analysis |
| `basedpyright` | — | Strict type checking (stricter than mypy) |
| `mdformat` | — | Consistent markdown formatting |

**Configuration philosophy:**

- `ruff` handles surface-level issues (formatting, imports, simple bugs)
- `pylint` handles deeper quality (unused vars, exceptions, complexity)
- `basedpyright` handles type safety

### [2026-07-14] Testing with pytest

**Context:** Zero test coverage, zero confidence for changes.

**Decision:** Add `pytest` + `pytest-cov` with `--cov-fail-under=100`.

**Coverage approach:**

- 100% coverage enforced (count is a live metric — see `AGENTS.md` Live metrics)
- Mock-based: no real camera, no real network, no real TFLite runtime needed
- See `TESTING.md` for full details and known gaps.

### [2026-07-14] PyInstaller notes

- `onnxruntime` is auto-detected by `hook-onnxruntime.py` from
  `pyinstaller-hooks-contrib` — no `--hidden-import` flags needed.
- Warning `Hidden import 'protobuf' not found` is harmless — protobuf is
  bundled transitively via the `onnx` dependency.

### [2026-07-14] LSP / editor notes

- LSP errors ("Cannot resolve imported module numpy") are false positives
  when the editor's Python interpreter differs from the project venv.
  For VS Code: set `python.defaultInterpreterPath` to `.venv/Scripts/python.exe`.

### [2026-07-14] Model directory layout (three supported layouts)

```
A) labels.txt + model.onnx (recommended for ONNX):
    model_path/
        model.onnx
        labels.txt

B) labels.txt + model.tflite (recommended for TFLite):
    model_path/
        model.tflite
        labels.txt

C) Microsoft Lobe legacy:
    model_path/
        signature.json
        model.tflite
```

### [2026-07-30] Connection protocol architecture

**Context:** The lobe server is a TCP client that connects to the robot's mailbox
server. Understanding the robot's protocol is essential for correct connection
health management.

**What the lobe server sends (outbound):**

- `register:<port>:<hull>` — on connect, registers with the robot
- `self:<hull>` — identifies itself
- `keepalive` — every `KEEPALIVE_INTERVAL=5s`
- `data:<prediction>` — every `PREDICTION_INTERVAL=0.2s`

**What the robot sends (inbound):**

- `self:<hull>` — during handshake, identifies itself
- `connection:<ip>:<port>:<hull>` — during handshake, informs about other robots
- `data:quit` — explicit shutdown command
- `keepalive` — every **3000ms** (hardcoded in `trikNetwork/src/connection.cpp`,
  never negotiated on the wire)

**Heartbeat on the robot side:**

- Robot kills the TCP connection if **no data received for 5000ms**
  (`heartbeatTime` in `connection.cpp`)
- The robot's keepalive timer resets on every outbound message, so under
  normal operation the 5s timeout never fires (lobe server sends keepalive
  every 5s and predictions every 0.2s)

### [2026-07-30] Connection health detection strategy

**Context:** The `_reader` task is the sole connection health monitor.
`_keepalive_loop` and `_prediction_loop` are strictly outbound — they never
detect a dead peer. `contextlib.suppress(OSError)` in `_send` is intentional:
send errors are transient glitches; death detection is the reader's job.

**Decision:**

- **Primary: `RECV_TIMEOUT`** — `asyncio.wait_for(sock_recv, timeout=10)` in
  `_reader`. The robot sends `keepalive` every 3s, so under normal operation
  the timeout never fires. After 10s of silence (3 missed keepalives + margin),
  the reader breaks and triggers reconnection.
- **Not used: TCP keepalive (`SO_KEEPALIVE`)** — requiring platform-specific API
  (`SIO_KEEPALIVE_VALS` on Windows, `TCP_KEEPIDLE` on Linux, `TCP_KEEPALIVE` on
  macOS) adds complexity without benefit since the application-level keepalive
  already provides a faster, platform-agnostic signal.

**Rationale:**

- `asyncio.wait_for` is stdlib, works identically on all three platforms
- No new dependencies
- 10s timeout gives ~3s margin over the 3s keepalive interval

**Guardrail:** Do not remove `contextlib.suppress(OSError)` from `_send`.
Transient send errors are normal; death detection belongs exclusively in
the `_reader`. Removing the suppress would cause reconnect storms on
momentary network glitches.

### [2026-08-05] Reconnect forever on peer death

**Context:** `_reader` set `self._running = False` after *every* break
(timeout, empty recv, reset), so `run_forever` exited instead of reconnecting —
contradicting the documented "triggers reconnection" behavior, the
`reconnecting...` log, and the `2c2bb3c` disconnect-fix intent. Worse, a TCP
reset (`ConnectionResetError` ⊂ `OSError`) hit the generic `except OSError`
retry path and spun forever on a dead socket, never reconnecting.

**Decision:**

- `_reader` breaks now leave `self._running` intact: timeout / empty recv /
  `ConnectionError` (reset, abort, refused) all break → `run_forever`
  reconnects after `RECONNECT_DELAY`. Only `data:quit` sets `_running = False`.
- Generic `OSError` (e.g. the Windows `wait_for`-cancel artifact) is retried up
  to `CONNECTION_ERROR_LIMIT = 3` consecutive times before breaking.
- The server reconnects forever until the robot returns; Ctrl-C / terminal
  close still terminate it — `KeyboardInterrupt` is a `BaseException`, never
  caught by `run_forever`'s `except Exception`.

**Consequences:** Robot crash/restart now auto-reconnects. Tests updated:
`test_reader_empty_recv`, `test_reader_heartbeat_timeout`,
`test_reader_connection_reset` now assert `_running` stays `True`;
`test_run_forever_does_not_swallow_keyboardinterrupt` locks the exit property.

**Detail:** `except` ordering in `_reader` is load-bearing — both `TimeoutError`
and `ConnectionError` subclass `OSError`, so they must come before the generic
`except OSError`, or their handling is swallowed. Do not reorder.

### [2026-08-05] Robustness batch

**Context:** Several small reliability and UX gaps: `input()` raised EOFError
when stdin was not a TTY; a down HTTP camera blocked a full 10s timeout every
prediction cycle and hammered the endpoint; cancelled child tasks in
`_handle_connection` were not awaited; malformed `settings.ini` surfaced raw
`KeyError`/`ValueError`.

**Decisions:**

- `TRIKLobeServer._pause_for_user()` gates the "press any key" prompt on
  `sys.stdin is not None and sys.stdin.isatty()` — headless runs (systemd,
  nohup) no longer crash on EOF, and a missing stdin is a no-op.
- `UrlCamera`/`RobotCamera` fast-fail for `_FAILURE_COOLDOWN = 2.0s` after a
  failed fetch (`_last_failure` tracked via `time.monotonic`), so a dead
  endpoint costs one 10s timeout per 12s instead of per cycle, and recovers
  within the cooldown once the camera returns.
- `_handle_connection` awaits cancelled tasks via
  `await asyncio.gather(*pending, return_exceptions=True)` — no "Task was
  destroyed" warnings, no leftover pending tasks when a connection drops.
- `load_settings` validates input: missing `[Settings]` section, non-integer
  values, `SERVER_PORT` outside 1-65535, non-positive `MY_HULL_NUMBER`, and
  negative `CAMERA_NUMBER` raise `ValueError` naming the offending key.

**Rationale:** `time.monotonic` is the correct clock (immune to wall-clock
jumps). The OSError retry limit preserves the Windows `wait_for`-cancel
protection while preventing infinite spin.

**Known limitation:** cancelling a task blocked in `asyncio.to_thread` does not
stop the worker thread — a prediction thread can finish after `data:quit` or a
reconnect. Pre-existing; `asyncio.gather(*pending)` only awaits the cancel, it
does not join the thread. For camera capture this is bounded by the HTTP
timeout / `VideoCapture.read()` duration.

**Consequences:** Friendlier error messages, bounded HTTP retry, clean task
shutdown, headless-safe entrypoint.

### [2026-07-30] Cross-platform audit findings

**Context:** A comprehensive cross-platform audit was performed after the
heartbeat timeout feature was implemented. Key findings and resolutions:

| Issue | Fix | Rationale |
|-------|-----|-----------|
| CI mdformat step fails on `windows-latest` | Added `shell: bash` | PowerShell doesn't expand `*.md` globs |
| PyInstaller `--icon=.ico` breaks on macOS | Made icon platform-conditional | `.ico` is Windows-only; macOS expects `.icns` |
| Hardcoded OS paths in tests | Replaced with `TemporaryDirectory` | Tests failed on non-matching platforms |
| `NamedTemporaryFile` locking on Windows | Replaced with `TemporaryDirectory` | Windows prevents reopening the file handle |
| `asyncio.get_event_loop()` deprecated | Migrated to `get_running_loop()` | Deprecated since 3.10, emits warnings in 3.12 |
| `TCP_NODELAY` before `connect()` | Moved after `connect()` | Implementation-defined on some platforms |
| `requires-python` mismatch | Bumped to `>=3.12` | Match `.python-version` and project convention |
| mdformat on Windows PowerShell | Run through pre-commit hook (`uv run pre-commit run mdformat --all-files`); CI uses `shell: bash` | PowerShell doesn't expand `*.md` globs |

**Known gaps (accepted, not fixed):**

- **`asyncio.wait_for` + `sock_recv` on Windows IOCP** — cancelling an in-flight
  `sock_recv` via `wait_for` may leave the socket in an indeterminate state on
  Windows. This is a known CPython issue. Not fixed because (a) it passes CI on
  `windows-latest`, (b) the alternative (`asyncio.open_connection` with a stream
  reader) adds complexity without measurable benefit, and (c) on timeout the
  socket is about to be closed and reconnected anyway.
- **`ai-edge-litert` missing Intel Mac wheel** — the package has no macOS x86_64
  wheel. `macos-latest` CI runner is ARM64 (Apple Silicon), so CI is unaffected.
  Intel Mac users would need to compile from source or use Docker.

### [2026-07-30] Gitignore policy for model files

**Context:** Model files (`.tflite`, `.onnx`) and `signature.json` are large
binary or user-specific configuration files that should not be version-controlled.

**Decision:** Ignore `*.tflite`, `*.onnx`, and `signature.json` in `.gitignore`.

**Rationale:**

- Model files are typically hundreds of MB — bloating the repo history
- Models are trained externally and copied into the project directory
- `signature.json` is auto-exported by Lobe/Teachable Machine and user-specific
- The required file structure is documented in README.md and this file's
  "Model directory layout (three supported layouts)" entry.

**Consequences:**

- Users must provide model files manually
- CI does not test with real models (all tests are mock-based)
- `.onnx` was added later for consistency with `.tflite`

### [2026-08-01] numpy 2.x upgrade

**Context:** The `numpy<2.0.0` pin blocked NumPy 2.x, which had been stable
for over two years. onnxruntime, opencv-python, and ai-edge-litert all support
NumPy 2.x. Dependabot offered to relax the bound but would not regenerate the
lockfile, leaving 1.26.4 installed in CI.

**Decision:** Upgrade to numpy 2.5.1 (latest stable, `requires-python >=3.12`
matching the project's own `>=3.12,<3.14`), regenerate `uv.lock`, and pin
`numpy>=2.0,<3.0`.

**Rationale:**

- 2.5.1 is the newest stable line with pre-built wheels for all supported platforms
- Full suite (107 tests, 100% coverage, all linters) passes on 2.5.1
- Forcing `>=2.0` prevents silent fallback to 1.26 in fresh installs

**Consequences:**

- `uv.lock` resolved 2.5.1 and was committed with the real version
- Dependabot's constraint-only PR (#96) was superseded and closed
- `pyproject.toml` version bumped to 2.0.0 for the first dual-backend release

### [2026-08-02] opencv 4.x defer for 2.0.0 release

**Context:** Dependabot proposed opencv-python 5.x. opencv 5 is a native-binary
major bump with migration risk, and the project was preparing the first
dual-backend release.

**Decision:** Keep `opencv-python>=4.11.0,<5.0.0`; add a Dependabot ignore for
`version-update:semver-major` so 5.x is not proposed. Re-evaluate after release.

**Consequences:** Grouped uv PRs exclude opencv 5.x; opencv minor/patch updates
(4.14) still land normally.

**Resolution (2026-08-05):** Adopted opencv-python 5.0.0.93
(`>=5.0.0.93,<6.0.0`). Verified: `cp37-abi3` wheels for all build platforms
(win_amd64, manylinux x86_64/aarch64, macOS arm64 + Intel), the `WebcamCamera`
API surface (`VideoCapture`, `cvtColor`, `COLOR_BGR2RGB`) is present and
functional, the full suite is green, and PyInstaller bundles cv2 5 (`cv2.pyd`
and the `opencv_videoio_ffmpeg500` DLL). The Dependabot
`version-update:semver-major` ignore was removed.

### [2026-08-03] Zero-filled date versioning

**Context:** The project previously used semantic feature versions (1.1.0,
2.0.0). The first modern dual-backend release was planned as 2.0.0, but the
maintainer decided all releases should use date-based versions.

**Decision:** Use zero-filled date versions for all releases. Tagged commits
carry `YY.MM.DD` (e.g. `26.08.03` for tag `v26.08.03`); `main` carries the next
date with a `.dev0` suffix (e.g. `26.08.04.dev0`).

**Rationale:**

- Date versions are inherently ordered and unambiguous
- Zero-filling (`26.08.03`) keeps tag and version strings identical, and
  normalizes to valid semver (`26.8.3`) under PEP 440
- A CI `version-check` job fails the release if the tag and `pyproject.toml`
  version disagree, preventing mis-tagged releases

**Consequences:**

- `pyproject.toml` version no longer matches a marketing version number
- Releases are tagged `vYY.MM.DD` and always created as drafts for review
- `version-check` in `python-app.yml` enforces tag/version consistency

### [2026-08-03] Release artifacts and notes conventions

**Context:** The first modern release (v26.08.03) exposed several gaps: no
publish pipeline, LLM-generated notes cluttered by dependency-bump lines, no
compare link, and ambiguous artifact filenames.

**Decisions:**

- Artifacts carry the release tag in the filename (e.g.
  `TRIKLobeServer-v26.08.03-Linux.tar.gz`) so multiple downloads don't
  collide in a user's Downloads folder.
- Inner binaries keep the version plus an extension (`TRIKLobeServer-v26.08.03.bin`
  / `.exe`) so users can identify and execute them after extraction.
- Release notes Part 2 opens with an "Updated dependencies" table instead of
  one bullet per dependency bump; then lists only major issues/PRs; then
  contributors (bots filtered, new contributors bold with `(new)`); ends with
  a GitHub compare link to the previous release.
- `mdformat-frontmatter` plugin preserves skill YAML frontmatter (mdformat
  otherwise corrupts it into a thematic break).

**Rationale:** teacher/enthusiast audience; unambiguous versioned filenames;
noise-free, human-written-feeling notes.

**Consequences:** the `release` job of `python-app.yml` implements the artifact
packaging (the single workflow file runs all 4 CI jobs with per-job guards);
the `release-notes` skill encodes the notes structure; first-release compare
base is the obsolete `v1.0.0` tag. Archive format per platform — see the
"Release archive formats" decision below.

### [2026-08-03] Release archive formats (zip/tgz per platform)

**Context:** Releases previously attached the Windows binary raw (`.exe`) and
Linux/macOS as `.tar.gz`, plus a separate `settings.ini` asset. Download size
matters for users on slow connections.

**Decision:** Ship every platform as one archive — Windows `.zip` (native
double-click extraction in Explorer), Linux and macOS `.tar.gz` (platform
standard, preserves the executable bit). Each archive contains the versioned
binary (`TRIKLobeServer-v<tag>.exe` / `.bin`) **and** `settings.ini` at the
root. The separate `settings.ini` release asset is dropped.

**Trade-off:** PyInstaller one-file binaries are already internally compressed,
so the archive saves only a few percent — the real win is **one download per
platform** that bundles the config, matching the README install flow
("download → unpack → edit settings.ini"). `.zip` is chosen for Windows
because Explorer opens it without extra tools; `.tar.gz` for Linux/macOS
because it is the standard and keeps file permissions.

**Consequences:**

- Artifact names become `TRIKLobeServer-v<tag>-Windows.zip`, `-Linux.tar.gz`,
  `-macOS.tar.gz`.
- The `release` job needs `zip` and `tar` on the runner (both preinstalled on
  `ubuntu-latest`), enforced by the "Check for all tools" step.
- Users download one archive instead of a binary + separate config.

### [2026-08-03] Pre-commit local hooks (uv)

**Context:** Pre-commit hooks pinned tool revisions separately from the project's
own dependency pins — ruff 0.15.21 in `.pre-commit-config.yaml` while the venv
ran 0.16.1 (and similarly mdformat), so pre-commit and CI could disagree about
what the code should look like. `ruff select = ["ALL"]` auto-enables rules on
bump, making the mismatch consequential.

**Decision:** Run ruff, ruff-format, and mdformat as **local hooks** with
`language: system` and `entry: uv run …`. Their versions come from `uv.lock` —
the single source of truth shared with CI.

**Rationale:** eliminates the pinned-rev-vs-venv drift class entirely; the venv
tools are already installed, so no separate hook environments to manage.

**Consequences:** fresh clones must `uv sync` before committing (local hooks
need the venv); `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, and
`uv-lock` remain remote hooks. `mdformat-frontmatter` is a project dev
dependency, so the local `uv run mdformat` hook still preserves skill
frontmatter.
