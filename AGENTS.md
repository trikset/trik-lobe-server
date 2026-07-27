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

## Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff check --fix` + `ruff-format` automatically.
`mdformat` runs manually or via CI only (not in pre-commit).

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

## CI quirks

### CI setup

`astral-sh/setup-uv` replaces both `actions/setup-python` and `pip install uv`:

- `setup-uv` installs uv with built-in caching on GitHub-hosted runners
- Python version is read from `.python-version` — never hardcoded in YAML
- `setup-uv` has a `python-version` input only when `.python-version` is absent or testing a non-default version

### Runner notes

- `windows-2019` and `macos-13` runners **no longer exist** on GitHub.
- Use `windows-2022`, `ubuntu-22.04`, `macos-latest` for builds.
- `macos-15-large`/`-intel` are paid "larger runners" — not on free plan.
- `macos-latest` is ARM64 (Apple Silicon).
- Build produces per-OS artifacts via PyInstaller `--onefile`.

## Guardrails

### Docs before PR

This session context is ephemeral — all state is lost when the conversation ends.
**AGENTS.md MUST be updated before any PR is created.** Never rely on chat history
to preserve decisions, rationale, or patterns. If a change affects CI, toolchain,
architecture, or conventions, document it in AGENTS.md first.
