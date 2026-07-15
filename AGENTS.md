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
uv run pytest --cov=lobe_server --cov-fail-under=100  # tests + coverage
uv run pyinstaller TRIKLobeServer.py --onefile --icon=trik-studio.ico
```

**Required order:** `ruff → mdformat → basedpyright → pylint → bandit → vulture → pytest`.

## Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff check --fix` + `ruff-format` + `mdformat`
automatically on every commit. This catches formatting issues early.

## Before push / PR — MANDATORY

**Never push without running the full CI suite locally first.** Pre-commit
hooks only cover formatting. Type errors, lint violations, security issues,
and test failures must be caught before push.

Run this single command before every push:

```bash
uv run ruff check . && uv run mdformat README.md MODERNIZATION.md AGENTS.md --check && uv run basedpyright . && uv run pylint lobe_server TRIKLobeServer.py tests && uv run bandit -r lobe_server/ TRIKLobeServer.py --skip B107 && uv run vulture lobe_server/ tests/ TRIKLobeServer.py && uv run pytest --cov=lobe_server --cov-fail-under=100
```

## Python version

**Must use Python 3.12** — Python 3.14 breaks `onnx` (no wheel, C++ build fails).
Pinned in `.python-version`. CI and local dev both read from this file.

## Architecture

- `lobe_server/model.py`: Dual backend — `ONNXImageModel` (onnxruntime) and
  `TFLiteImageModel` (ai_edge_litert). Auto-detects format by scanning for
  `.onnx` or `.tflite` files. Labels from `labels.txt` (one per line), with
  fallback to `signature.json` → `classes.Label` (legacy Lobe compat).
  `ai_edge_litert` is a mandatory dependency.
- `lobe_server/server.py`: `LobeServer` — TCP server with asyncio event loop.
  `run_forever()` retries on connection failure after `RECONNECT_DELAY=3s`.

## Tests

92 tests, 100% coverage. All mock-based — no real camera, network, or TFLite.
Run single test: `uv run pytest tests/test_model.py::test_onnx_model_load_with_signature_json -x`.

After adding tests, always verify with `--cov-report=term-missing` that
the specific lines you intended to cover actually are. Passing tests do
not guarantee coverage — async race conditions can silently skip lines.

Check current count: `uv run pytest --co -q 2>&1 | tail -1`. Run testiq
overlap audit when count grows by 5+ from last audit.

`reportMissingTypeStubs`, `reportUnknownMemberType`, etc. set to `"none"` in
pyproject.toml because numpy/onnxruntime/pytest have no stubs — intentional,
0 errors expected.

## CI quirks

- `windows-2019` and `macos-13` runners **no longer exist** on GitHub.
- Build runners use **oldest free** for widest binary compatibility: `ubuntu-22.04`, `windows-2022`, `macos-14`.
- Test runners use **`-latest`** for newest OS coverage.
- `macos-latest` is ARM64 (Apple Silicon). `macos-14` is also ARM64.
- `macos-15-large`/`-intel` are paid "larger runners" — not on free plan.
- Build produces per-OS artifacts via PyInstaller `--onefile`.
