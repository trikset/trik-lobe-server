# Design Decisions

<!-- encoding: utf-8 -->

Scope: Technology and implementation choices made during development.
Aim: Explain *why* things are the way they are, not just *what* changed.
Structure: Dated entries, each with context → decision → rationale → consequences.
Cross-reference: Testing strategy → `TESTING.md`, CI setup → `AGENTS.md`.

## [2025-07-10] pip → uv

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

## [2026-07-14] Remove lobe SDK

**Context:** The `lobe` SDK (Microsoft Lobe) was last released Feb 2022;
the entire Lobe product has been discontinued. Old pins (`pillow~=9.0.1`,
`matplotlib~=3.5.1`) blocked installation on Python ≥3.12.

**Decision:** Remove the `lobe` dependency entirely. Replace with a custom
dual-backend model loader.

**What the server actually used from `lobe`:**

```python
from lobe import ImageModel
model = ImageModel.load(path)        # read signature.json + load TFLite
result = model.predict(pil_image)    # preprocess + inference
prediction = result.prediction        # top class label string
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

## [2026-07-14] Add ONNX runtime

**Context:** Needed a reliable ONNX inference backend for the new model loader.

**Decision:** Add `onnxruntime`.

**Rationale:**

- Pre-built wheels on PyPI for all platforms (x64 + ARM64)
- Python 3.10-3.14 support with no compilation needed
- Actively maintained by Microsoft
- Bundles cleanly with PyInstaller (auto-detected)

## [2026-07-14] Add ai-edge-litert (LiteRT)

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

## [2026-07-14] Remove matplotlib

**Context:** Only used by Lobe's `model.visualize()` (Grad-CAM heatmaps).
The server never called this method.

**Decision:** Remove `matplotlib`.

## [2026-07-14] Add labels.txt → signature.json priority

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

## [2026-07-14] Toolchain: ruff, pylint, basedpyright, mdformat

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

## [2026-07-14] Testing with pytest

**Context:** Zero test coverage, zero confidence for changes.

**Decision:** Add `pytest` + `pytest-cov` with `--cov-fail-under=100`.

**Coverage history:**

- Initial: 56 tests, 96% coverage
- Current: 87 tests, 100% coverage
- Mock-based: no real camera, no real network, no real TFLite runtime needed
- See `TESTING.md` for full details and known gaps.

## [2026-07-14] PyInstaller notes

- `onnxruntime` is auto-detected by `hook-onnxruntime.py` from
  `pyinstaller-hooks-contrib` — no `--hidden-import` flags needed.
- Warning `Hidden import 'protobuf' not found` is harmless — protobuf is
  bundled transitively via the `onnx` dependency.

## [2026-07-14] LSP / editor notes

- LSP errors ("Cannot resolve imported module numpy") are false positives
  when the editor's Python interpreter differs from the project venv.
  For VS Code: set `python.defaultInterpreterPath` to `.venv/Scripts/python.exe`.

## [2026-07-14] Model directory layout (three supported layouts)

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

## [2026-07-30] Connection protocol architecture

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

## [2026-07-30] Connection health detection strategy

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

## [2026-07-30] Cross-platform audit findings

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
| mdformat command in AGENTS.md | Changed to Python glob | Cross-platform: `*.md` not expanded by PowerShell |

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

## [2026-07-30] Gitignore policy for model files

**Context:** Model files (`.tflite`, `.onnx`) and `signature.json` are large
binary or user-specific configuration files that should not be version-controlled.

**Decision:** Ignore `*.tflite`, `*.onnx`, and `signature.json` in `.gitignore`.

**Rationale:**
- Model files are typically hundreds of MB — bloating the repo history
- Models are trained externally and copied into the project directory
- `signature.json` is auto-exported by Lobe/Teachable Machine and user-specific
- The required file structure is documented in README.md and DESIGN_DECISIONS.md

**Consequences:**
- Users must provide model files manually
- CI does not test with real models (all tests are mock-based)
- `.onnx` was added later for consistency with `.tflite`

## [2026-08-01] numpy 2.x upgrade

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
