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
- 82 tests covering: config loading, camera sources (including error paths), protocol, server
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

**Replacement:** `lobe_server/model.py` — dual backend `ONNXImageModel` + `TFLiteImageModel`:

1. Auto-detects model format by scanning directory for `.tflite` or `.onnx` files
1. Labels loaded from `labels.txt` (priority) or `signature.json` → `classes.Label`
1. `signature.json` may optionally contain `filename` to specify model file explicitly
1. Preprocesses images the same way Lobe did (resize + center crop + normalize)
1. Returns a `ClassificationResult` with the same `.prediction` API

The call site in `server.py` needed zero changes — both model classes expose the
same `predict()` → `.prediction` interface.

**What this unblocks:**

- No more `matplotlib` dependency (was only needed for Lobe visualization)
- `Pillow` can be any modern version
- Server works on Python 3.10-3.12
- CI no longer needs to install `lobe` (which pulled in broken deps)
- Both ONNX and TFLite are first-class citizens with no conversion step

### Added: `onnxruntime`

Runs ONNX models. Chosen because:

- Pre-built wheels on PyPI for Windows / Linux / macOS (x64 + ARM64)
- Python 3.10-3.14 support with no compilation needed
- Actively maintained by Microsoft
- Bundles cleanly with PyInstaller (auto-detected)

### Added: `ai-edge-litert` (LiteRT)

Runs TFLite models natively. Replaces both the old `tflite-runtime` (abandoned,
no PyPI wheels for Python 3.12+) and `tflite2onnx` (brittle conversion layer).

- Google-maintained successor to TensorFlow Lite runtime
- Pre-built wheels on PyPI for Windows / Linux / macOS (all Python 3.10-3.14)
- Fully backward compatible with all `.tflite` models (tested on 12 VOLK models)
- Same API as `tflite_runtime.interpreter` — zero code changes needed
- C extension, bundles with PyInstaller without special handling

### Removed: `tflite2onnx`

No longer needed. The conversion step introduced a fragile dependency and
added latency on first load. TFLite models now run natively.

### Removed: `tflite-runtime`

Abandoned by Google (last release Oct 2023). Required a custom PyPI index,
had no Python 3.12+ wheels. Replaced by `ai-edge-litert`.

### Removed: `matplotlib`

Only used by Lobe's `model.visualize()` (Grad-CAM heatmaps). The server
never called this method.

### Kept (with modern bounds): `opencv-python`, `requests`, `Pillow`, `numpy`

Core runtime dependencies. Versions widened for cross-platform compatibility.

______________________________________________________________________

## 4. Dual Backend (ONNX + TFLite): How It Works

### Model directory layout (three supported layouts):

```
A) labels.txt + model.onnx (рекомендуется):
    model_path/
        model.onnx              ← ONNX модель
        labels.txt              ← одна строка на класс

B) labels.txt + model.tflite (рекомендуется для TFLite):
    model_path/
        model.tflite      ← TFLite модель
        labels.txt              ← одна строка на класс

C) Microsoft Lobe legacy:
    model_path/
        signature.json          ← метаданные (читается только classes.Label + filename)
        model.tflite      ← TFLite модель
```

### `lobe_server/model.py` flow:

1. **`load_model(path)`**

   - Reads `signature.json` if present → extracts optional `filename`
   - If `filename` is set → uses that file
   - Otherwise → auto-detects first `.tflite` or `.onnx` file
   - Dispatches to `ONNXImageModel.load()` or `TFLiteImageModel.load()`

1. **`ONNXImageModel.load(path)`**

   - Loads model via `onnxruntime.InferenceSession`
   - Infers `input_name` and `input_size` from ONNX graph
   - Reads labels from `_read_labels()` (labels.txt → signature.json)

1. **`TFLiteImageModel.load(path)`**

   - Loads model via `ai_edge_litert.interpreter.Interpreter`
   - Reads input size from TFLite flatbuffer
   - Reads labels from `_read_labels()` (labels.txt → signature.json)

1. **`model.predict(pil_image)`**

   - **Preprocess:** RGB conversion → `resize_uniform_to_fill` →
     `crop_center` → normalize `[0, 255]` uint8 → `[0, 1]` float32 →
     add batch dimension → shape `[1, H, W, 3]`
   - **Inference:** backend-specific (onnxruntime `session.run` or TFLite
     `set_tensor` + `invoke`)
   - **Postprocess:** zip softmax outputs with labels → sort by confidence →
     `ClassificationResult`

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

## 7. labels.txt → Signature Priority (2026-07)

### Problem

`signature.json` was a Lobe-ism. For non-Lobe models (Teachable Machine,
Azure Custom Vision, Edge Impulse), users had to create a JSON file with
`classes.Label`. Many platforms export `labels.txt` instead — one label
per line, a simpler format.

### Solution

`_read_labels(model_path)` now has two paths, in priority order:

1. **labels.txt exists** — read labels from file (one per line)
   - UTF-8 BOM handling: `encoding="utf-8-sig"`
   - Empty line filtering: blank lines are stripped
1. **No labels.txt, signature.json exists** — extract `classes.Label`

### What this unblocks

- **Teachable Machine / Edge Impulse / Azure CV**: export labels.txt, drop
  it next to the model, no signature.json needed
- **Backward compatible**: every existing Lobe model still works via
  signature.json → classes.Label

______________________________________________________________________

## 8. Test Coverage Gaps

| Lines missed | Module | Why not tested? |
|---|---|---|
| `camera.py:61-70` | `WebcamCamera.__init__` | Requires `cv2` + a physical camera |
| `server.py:106-112` | `run_forever` success branch | Requires a real TCP server to connect to |
| `model.py:150` | `ONNXImageModel.load` `:0` suffix | Only triggers on TF SavedModel models (rare) |
| `model.py:136-146` | `ONNXImageModel.load` shape inference | Rare ONNX shapes (2D, 0D, dynamic dims) |

All gaps require real hardware (camera, network) or platform-specific packages.
