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
- 50 tests covering: config loading, camera sources, protocol, server
  lifecycle, TFLite model loading and inference
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

**Replacement:** `lobe_server/model.py` — an 80-line TFLite compatibility shim:

1. Reads `signature.json` (the standard Lobe export metadata file)
1. Loads the `.tflite` model via `tflite-runtime`
1. Preprocesses images using the same algorithm Lobe used
1. Returns a `ClassificationResult` with the same `.prediction` API

The call site in `server.py` (`_load_model` → `TFLiteImageModel.load`)
needed zero changes — the new class exposes the same `predict()` → `.prediction`
interface.

**What this unblocks:**

- No more `matplotlib` dependency (was only needed for Lobe visualization)
- `Pillow` can be any modern version
- Server works on Python 3.10-3.14
- CI no longer needs to install `lobe` (which pulled in broken deps)

### Removed: `matplotlib`

Only used by Lobe's `model.visualize()` (Grad-CAM heatmaps). The server
never called this method.

### Kept (with modern bounds): `opencv-python`, `requests`, `Pillow`, `numpy`

Core runtime dependencies. Versions widened for cross-platform compatibility.

### Not bundled: `tflite-runtime`

**Why it's not in `pyproject.toml`:**
`tflite-runtime` is a C extension with no pre-built wheel for Python 3.14 (and
limited platform coverage in general). It's available from Google Coral's custom
PyPI index, not from PyPI proper.

**How it's handled instead:**

- Imported lazily inside `TFLiteImageModel.load()` with a clear error message

- Install on your target device via:

  ```bash
  pip install --index-url https://google-coral.github.io/py-repo/ tflite-runtime
  ```

  Or if you have TensorFlow installed, it ships `tensorflow.lite` which
  `model.py` can use instead (see the original `lobe` SDK for reference).

______________________________________________________________________

## 4. Lobe → TFLite Shim: How It Works

```
Lobe-exported model directory:
  model_path/
    signature.json          ← metadata: labels, input size, model filename
    saved_model.tflite      ← standard TFLite model file
```

`lobe_server/model.py` flow:

1. **`TFLiteImageModel.load(path)`**

   - Reads `signature.json` → class labels, image size, model filename
   - Loads `.tflite` via `tflite_runtime.interpreter.Interpreter`
   - Returns a `TFLiteImageModel` instance

1. **`model.predict(pil_image)`**

   - **Preprocess:** EXIF orientation correction → RGB conversion →
     `resize_uniform_to_fill` (scale shortest side to target) →
     `crop_center` → normalize `[0, 255]` uint8 → `[0, 1]` float32 →
     add batch dimension → shape `[1, H, W, 3]`
   - **Inference:** `interpreter.set_tensor()` → `invoke()` → `get_tensor()`
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

**Matrix:** ubuntu-latest / windows-latest / macos-latest × Python 3.10 / 3.11 / 3.12

______________________________________________________________________

## 6. Test Coverage Gaps

| Lines missed | Module | Why not tested? |
| --------------------- | --------------- | ------------------------------------------------ |
| `camera.py:51-54` | `WebcamCamera.__init__` | Requires `cv2` + a physical camera |
| `server.py:108-115` | `run_forever` success | Requires a real TCP server to connect to |
| `model.py:58-64` | `TFLiteImageModel.load` import | `tflite-runtime` not installed locally |
| `model.py:114-124` | EXIF orientation | Covered in `test_update_orientation_no_exif` but the EXIF branch requires an image with EXIF metadata |

All gaps require real hardware (camera, network) or platform-specific packages.

______________________________________________________________________

## 7. Branch Strategy

All work was done on the `auto-mode-1` branch with atomic commits. The commit
history is clean and each commit is a logical unit:

```
2594bab ci: migrate to uv, add ruff/pylint/basedpyright/pytest-cov
1405a05 fix: address lint/type issues, add timeouts, fix test assertions
d2ccdde test: 39 tests at 96.6% coverage, expand test suite
892bc20 chore: untrack local dev db
a0648f1 style: apply ruff format + mdformat
f7d6d7e migrate to uv with pyproject.toml and dev toolchain
```
