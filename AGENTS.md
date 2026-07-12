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
uv run basedpyright .        # typecheck (strict mode, 0 errors expected)
uv run pylint lobe_server TRIKLobeServer.py tests  # code quality (10.00 expected)
uv run pytest --cov=lobe_server --cov-fail-under=90  # tests + coverage
uv run pyinstaller TRIKLobeServer.py --onefile --icon=trik-studio.ico
```

**Required order:** `ruff → basedpyright → pylint → pytest` — run all before commit.
Pre-commit hook runs `ruff check --fix` + `ruff-format` automatically.

## Python version
**Must use Python 3.12** — Python 3.14 breaks `onnx` (no wheel, C++ build fails).
Already pinned in `.python-version`. CI and local dev both use 3.12.

## Architecture
- `lobe_server/model.py`: `ONNXImageModel` — inference via onnxruntime.
  TFLite models auto-convert to ONNX on first load via `tflite2onnx`.
- `lobe_server/server.py`: `LobeServer` — TCP server with asyncio event loop.
- `lobe_server/camera.py`: three camera sources — `UrlCamera`, `RobotCamera`,
  `WebcamCamera`. cv2 is lazy-imported (50+ MB DLLs, only WebcamCamera needs it).
- Import shortcut: `from lobe_server import LobeServer, load_model, Settings`

## Tests
56 tests, 96% coverage. All mock-based — no real camera, network, or TFLite.
Run single test: `uv run pytest tests/test_model.py::test_onnx_model_load -x`.

## basedpyright notes
`reportMissingTypeStubs`, `reportUnknownMemberType`, etc. are set to `"none"`
because numpy/onnxruntime/pytest have no stubs. This is intentional — 0 errors
expected.

## CI quirks
- `windows-2019` and `macos-13` runners **no longer exist** on GitHub.
- Use `windows-2022`, `ubuntu-22.04`, `macos-latest` for builds.
- `macos-15-large`/`-intel` are paid "larger runners" — not on free plan.
- `macos-latest` is ARM64 (Apple Silicon).
- Build produces per-OS artifacts via PyInstaller `--onefile`.

## GPG signing
Disabled for `auto-mode-1` branch (`branch.auto-mode-1.commit.gpgsign = false`).
Other branches may sign by default — use `--no-gpg-sign` if needed.
