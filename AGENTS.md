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
uv run pytest --cov=lobe_server --cov-fail-under=90  # tests + coverage
uv run pyinstaller TRIKLobeServer.py --onefile --icon=trik-studio.ico
```

**Required order:** `ruff → mdformat → basedpyright → pylint → bandit → vulture → pytest`.

## Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff check --fix` + `ruff-format` automatically.
`mdformat` runs manually or via CI only (not in pre-commit).

## Python version

**Must use Python 3.12** — Python 3.14 breaks `onnx` (no wheel, C++ build fails).
Already pinned in `.python-version`. CI and local dev both use 3.12.

## Architecture

- `lobe_server/model.py`: Dual backend — `ONNXImageModel` (onnxruntime) and
  `TFLiteImageModel` (ai_edge_litert). Auto-detects format by scanning for
  `.onnx` or `.tflite` files. Labels from `labels.txt` (one per line), with
  fallback to `signature.json` → `classes.Label` (legacy Lobe compat).
  `ai_edge_litert` is a mandatory dependency.
- `lobe_server/server.py`: `LobeServer` — TCP server with asyncio event loop.
  `run_forever()` retries on connection failure after `RECONNECT_DELAY=3s`.

## Tests

82 tests, 93% coverage. All mock-based — no real camera, network, or TFLite.
Run single test: `uv run pytest tests/test_model.py::test_onnx_model_load_with_signature_json -x`.

`reportMissingTypeStubs`, `reportUnknownMemberType`, etc. set to `"none"` in
pyproject.toml because numpy/onnxruntime/pytest have no stubs — intentional,
0 errors expected.

## CI quirks

- `windows-2019` and `macos-13` runners **no longer exist** on GitHub.
- Use `windows-2022`, `ubuntu-22.04`, `macos-latest` for builds.
- `macos-15-large`/`-intel` are paid "larger runners" — not on free plan.
- `macos-latest` is ARM64 (Apple Silicon).
- Build produces per-OS artifacts via PyInstaller `--onefile`.
