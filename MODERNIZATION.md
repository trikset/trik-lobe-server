# Modernization Log

This document explains the rationale behind every major decision made during the
modernization of this project. It is written for **human maintainers** — so you
understand *why* things are the way they are, not just *what* changed.

______________________________________________________________________

## 1. Why Modernize?

The original `trik-lobe-server` was created in 2021 for Python 3.9 and the
now-abandoned Microsoft Lobe SDK. By mid-2026 the project had:

- **Abandoned upstream dependency** — `lobe` SDK last released Feb 2022,
  Microsoft discontinued the entire Lobe product. Old pins (`pillow~=9.0.1`,
  `matplotlib~=3.5.1`) block installation on Python ≥3.12.
- **No tests** — zero coverage, zero confidence for changes.
- **No linting or type checking** — `flake8` was configured but only ran on CI.
- **`pip` + `requirements.txt`** — no lockfile, no deterministic installs.
- **GPG-signed commits** — locally configured but hung in non-interactive
  environments.

______________________________________________________________________

## 2. Toolchain Migration

### pip → uv (2025-07-10)

**What changed:**

- `pyproject.toml` replaces `requirements.txt` + `dev-requirements.txt`
- `uv sync` for deterministic, fast installs
- `uv run` for all Python commands
- `uv.lock` committed for reproducible environments

**Why uv over pip:**

- 10-100× faster dependency resolution
- Built-in lockfile (no need for `pip-tools` or `poetry`)
- Single binary, no Python dependency to install itself
- Handles platform-specific markers and custom indexes natively

### Linting & Formatting

| Tool | Replaces | Why |
| ---------- | ------------------ | -------------------------------------------------------- |
| `ruff` | `flake8` + `isort` + `black` | Single tool, 100× faster, same rules |
| `pylint` | — | Strict mode for deeper code quality analysis |
| `basedpyright` | — | Strict type checking (stricter than mypy) |
| `mdformat` | — | Consistent markdown formatting |

**Configuration philosophy:**

- `ruff` handles surface-level issues (formatting, imports, simple bugs)
- `pylint` handles deeper quality (unused vars, exceptions, complexity)
- `basedpyright` handles type safety

### Testing

- **pytest** + **pytest-cov** with `--cov-fail-under=90`
- 56 tests covering: config loading, camera sources, protocol, server
  lifecycle, ONNX model loading, TFLite auto-conversion, inference
- Mock-based: no real camera, no real network, no real TFLite runtime needed
- Coverage report shows exactly what isn't tested and why

______________________________________________________________________

## 3. Dependency Decisions

### Removed: `lobe` SDK

**Status:** Abandoned by Microsoft. Last release v0.6.2 on 2022-02-23. The
entire Microsoft Lobe product (desktop app + Python SDK) has been discontinued.

**Why it was a problem:**

- Pins `pillow~=9.0.1` — fails to build on Python 3.12+
- Pins `matplotlib~=3.5.1` — same problem, no Python 3.12+ wheel
- Only supports Python 3.7-3.10
- The `lobe` desktop app no longer exists, but exported models are still
  usable

**What the server actually used from `lobe`:**

```python
from lobe import ImageModel
model = ImageModel.load(path)        # read signature.json + load TFLite
result = model.predict(pil_image)    # preprocess + inference
prediction = result.prediction        # top class label string
```

That's it. No visualization, no Grad-CAM, no ONNX fallback, no batching.

**Replacement:** `lobe_server/model.py` — `ONNXImageModel` class:

1. Reads `signature.json` (the standard Lobe export metadata file)
1. If the model is TFLite format, auto-converts to ONNX on first load via
   `tflite2onnx` (caches `model.onnx` + updates `signature.json`)
1. Loads the `.onnx` model via `onnxruntime` for inference
1. Preprocesses images using the same algorithm Lobe used
1. Returns a `ClassificationResult` with the same `.prediction` API

The call site in `server.py` needed zero changes — the new class exposes the
same `predict()` → `.prediction` interface.

**What this unblocks:**

- No more `matplotlib` dependency (was only needed for Lobe visualization)
- `Pillow` can be any modern version
- Server works on Python 3.10-3.12
- CI no longer needs to install `lobe` (which pulled in broken deps)
- No C extension for TFLite runtime needed — `onnxruntime` has pre-built
  wheels for all platforms (including Windows ARM64)
- PyInstaller bundles cleanly: all dependencies are pure-Python or have
  standard wheels

### Added: `onnxruntime`

The sole inference backend. Chosen because:

- Pre-built wheels on PyPI for Windows / Linux / macOS (x64 + ARM64)
- Python 3.10-3.14 support with no compilation needed
- Actively maintained by Microsoft
- Bundles cleanly with PyInstaller (auto-detected)

### Added: `tflite2onnx`

Pure-Python library (42 KB) to convert TFLite models to ONNX format.
Used only for the one-time conversion of legacy Lobe TFLite models.

- Zero C extensions — no compilation risk
- PyInstaller bundles it trivially
- Fallback: if missing, user gets a clear error message with manual
  conversion instructions

### Removed: `matplotlib`

Only used by Lobe's `model.visualize()` (Grad-CAM heatmaps). The server
never called this method.

### Kept (with modern bounds): `opencv-python`, `requests`, `Pillow`, `numpy`

Core runtime dependencies. Versions widened for cross-platform compatibility.

### Removed: `tflite-runtime`

No longer needed. Previous versions of this project used `tflite-runtime`
directly, but it was:

- Unavailable on PyPI (required Google Coral's custom index)
- No pre-built wheel for Python 3.13+
- C extension that can't bundle with PyInstaller without special handling
- Replaced entirely by `tflite2onnx` + `onnxruntime`

______________________________________________________________________

## 4. Lobe → ONNX: How It Works

```
Lobe-exported model directory:
  model_path/
    signature.json          ← metadata: labels, input size, model filename
    saved_model.tflite      ← original TFLite model (kept)
    model.onnx              ← converted ONNX (written on first load)
    signature.json.tflite-backup  ← backup of original signature.json
```

`lobe_server/model.py` flow:

1. **`ONNXImageModel.load(path)`**

   - Reads `signature.json` → format, class labels, image size, model filename
   - If format is `"tf_lite"` or `"tf"`:
     - Checks if `model.onnx` exists (cached from previous conversion)
     - If not cached: calls `tflite2onnx.convert(tflite_path, onnx_path)`
     - Updates `signature.json`: `format = "onnx"`, `filename = "model.onnx"`
     - Backs up original `signature.json` → `signature.json.tflite-backup`
   - Loads `.onnx` via `onnxruntime.InferenceSession`
   - Returns an `ONNXImageModel` instance

1. **`model.predict(pil_image)`**

   - **Preprocess:** EXIF orientation correction → RGB conversion →
     `resize_uniform_to_fill` (scale shortest side to target) →
     `crop_center` → normalize `[0, 255]` uint8 → `[0, 1]` float32 →
     add batch dimension → shape `[1, H, W, 3]`
   - **Inference:** `session.run(None, {input_name: processed})`
   - **Postprocess:** zip softmax outputs with labels → sort by confidence →
     `ClassificationResult`

1. **`result.prediction`** → top label string

The preprocessing algorithm matches Lobe's `image_utils.py` (MIT licensed,
publicly available at `github.com/lobe/lobe-python`).

______________________________________________________________________

## 5. CI/CD Pipeline

GitHub Actions runs on every push and PR:

```yaml
- uv sync --frozen
- uv run ruff check .
- uv run basedpyright .
- uv run pylint lobe_server TRIKLobeServer.py tests
- uv run pytest --cov=lobe_server --cov-fail-under=90
- uv run pyinstaller TRIKLobeServer.py --onefile  # build job only
```

**Test matrix:** ubuntu-latest / windows-latest / macos-latest × Python 3.12
**Build matrix:** ubuntu-22.04 / windows-2022 / macos-latest × Python 3.12

______________________________________________________________________

## 6. Runtime Platform Notes

### Python version constraints (2026-07)

Python 3.14 breaks `onnx` — no pre-built wheel, the C++ extension fails
to compile on Windows. Pin to Python 3.12 for all production builds.

CI test matrix was narrowed from 3.10/3.11/3.12 to 3.12 only (July 2026).

### GitHub Actions runner availability (2026-07)

- `windows-2019` and `macos-13` have been fully removed by GitHub.
- `macos-15-large` / `macos-15-intel` are paid "larger runners" —
  unavailable on free public repositories.
- Standard macOS runner `macos-latest` is ARM64 (Apple Silicon), not Intel.
- Build runners used: `ubuntu-22.04`, `windows-2022`, `macos-latest`.

### PyInstaller notes

- onnxruntime is auto-detected by `hook-onnxruntime.py` from
  `pyinstaller-hooks-contrib` — no `--hidden-import` flags needed.
- Warning `Hidden import 'protobuf' not found` is harmless — protobuf is
  bundled transitively via the `onnx` dependency.

### LSP / editor notes

- LSP errors ("Cannot resolve imported module numpy") are false positives
  when the editor's Python interpreter differs from the project venv.
  For VS Code: set `python.defaultInterpreterPath` to `.venv/Scripts/python.exe`.

______________________________________________________________________

## 6. Test Coverage Gaps

| Lines missed | Module | Why not tested? |
| --------------------- | --------------- | ------------------------------------------------ |
| `camera.py:51-54` | `WebcamCamera.__init__` | Requires `cv2` + a physical camera |
| `server.py:108-114` | `run_forever` success | Requires a real TCP server to connect to |
| `model.py:78` | `ONNXImageModel.load` `:0` suffix | Only triggers on TF SavedModel models (rare) |
| `model.py:148-158` | `_ensure_converted` exception branches | `json.dump` / `shutil.copy2` edge cases |

All gaps require real hardware (camera, network) or platform-specific packages.

______________________________________________________________________

## 7. Branch Strategy

All work was done on the `auto-mode-1` branch with atomic commits. The commit
history is clean and each commit is a logical unit:

```
2594bab ci: migrate to uv, add ruff/pylint/basedpyright/pytest-cov
442f70b feat: replace abandoned lobe SDK with onnxruntime + tflite2onnx
01c770b chore: track uv.lock for deterministic CI installs
```
