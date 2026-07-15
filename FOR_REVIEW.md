# FOR_REVIEW.md — Undocumented Decisions

Audit results: 49 findings across 10 files. Each item includes the code
location, what it does, and why it needs documentation. Items are
organized by file and severity (HIGH = agent would misunderstand code,
MEDIUM = agent would question the choice, LOW = nice-to-have).

Action for each: move to inline comment, AGENTS.md, MODERNIZATION.md,
or reject (already documented elsewhere / too trivial).

## 1. `lobe_server/config.py`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 1 | 11 | `my_hull_number: int = 2` | "Hull number" is TRIK jargon. No explanation of valid range or meaning. | MEDIUM |
| 2 | 12 | `server_port: int = 8889` | Protocol constant, not explained in source. | MEDIUM |
| 3 | 16 | `camera_number: int = 0` | 0 = first V4L2/DirectShow device. Platform convention. | LOW |
| 4 | 32-41 vs 9-18 | Duplicated defaults | Dataclass defaults vs `load_settings()` defaults — intentional duplication, not obvious why. | MEDIUM |
| 5 | 48 | `getattr(sys, "frozen", False)` | PyInstaller idiom. Non-obvious to anyone unfamiliar with PyInstaller. | LOW |
| 6 | 50 | `Path(__file__).parent.parent.resolve()` | Double-parent navigates from `lobe_server/config.py` to project root. | LOW |

## 2. `lobe_server/server.py`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 7 | 18 | `KEEPALIVE_INTERVAL = 5` | Why 5s? Protocol timeout? | MEDIUM |
| 8 | 19 | `PREDICTION_INTERVAL = 0.2` | Why 0.2s (5 FPS)? Latency vs CPU trade-off. | MEDIUM |
| 9 | 20 | `RECONNECT_DELAY = 3` | Why 3s? Fixed backoff, not exponential. | LOW |
| 10 | 21 | `SOCKET_TIMEOUT = 10` | Why 10s? Should never trigger on LAN. | LOW |
| 11 | 22 | `BUFFER_SIZE = 255` | Why 255? Protocol message size limit? | MEDIUM |
| 12 | 44-45 | `return "-1"` | Magic string sentinel. Protocol convention, not obvious. | **HIGH** |
| 13 | 65 | `await asyncio.sleep(0.1)` | Prevents tight-loop on persistent errors. Value arbitrary. | LOW |
| 14 | 72 | `await asyncio.sleep(0)` | Yield to event loop. Without comment, looks like a no-op. | LOW |
| 15 | 93 | `TCP_NODELAY` | Low-latency for robot commands. Trade-off undocumented. | MEDIUM |
| 16 | 95 | `setblocking(False)` | Two-phase: blocking for connect, non-blocking for async I/O. | MEDIUM |
| 17 | 81-86 | `FIRST_COMPLETED` | Reader completing = stop everything. Pattern needs why. | LOW |

## 3. `lobe_server/model.py`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 18 | 118-121 | NCHW detection heuristic | Fragile heuristic. Assumes channels are 1 or 3, spatial dim is not 3. | **HIGH** |
| 19 | 131 | `isinstance(d, (int, float)) and d != -1` | ONNX convention: -1 = dynamic dim. Non-obvious. | MEDIUM |
| 20 | 133-134 | `dims = dims[1:]` | Strips assumed batch dim. ONNX convention, not stated. | MEDIUM |
| 21 | 136-139 | NHWC/NCHW 3D heuristic | Second heuristic separate from `_is_nchw`. Interaction undocumented. | **HIGH** |
| 22 | 143 | `224, 224` | ImageNet standard. May be wrong for non-ImageNet models. | LOW |
| 23 | 147-148 | `input_name.endswith(":0")` | TF export compat. Completely opaque without comment. | MEDIUM |
| 24 | 161 | `strict=False` | Lenient truncation vs crash. Trade-off undocumented. | MEDIUM |
| 25 | 181-182 | `_, h, w, _ = shape` | TFLite hardcoded 4-dim NHWC. No guard (unlike ONNX path). | **HIGH** |
| 26 | 204 | `/ 255.0` | [0,1] normalization. Matches Lobe convention but not universal. | MEDIUM |
| 27 | 209 | `scale = max(...)` | Cover-resize + crop vs fit + pad. Significant preprocessing choice. | MEDIUM |

## 4. `lobe_server/camera.py`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 28 | 32, 49 | `timeout=10` | HTTP timeout. Same magic number in two places. | LOW |
| 29 | 44-45 | `http://{server_ip}:8080/?action=snapshot` | TRIK robot camera API. Hardcoded, not configurable. | **HIGH** |
| 30 | 65 | `_cv2.VideoCapture(camera_number)` | Eager open = holds device for server lifetime. Trade-off undocumented. | MEDIUM |
| 31 | 66-70 | `logger.critical(...)` no raise | Silent degradation vs fail-fast. Server starts but `capture()` always returns None. | MEDIUM |

## 5. `lobe_server/protocol.py`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 32 | 1-10 | No module docstring | Wire format completely undocumented. Agent cannot understand any function. | **HIGH** |
| 33 | 2 | `len(msg)` in format | Character count (not byte count). Same for ASCII, different for non-ASCII. | MEDIUM |
| 34 | 10 | `"9:data:quit" in data` | `9` = length of `"data:quit"`. Substring match (not exact). Both opaque. | **HIGH** |

## 6. `lobe_server/__init__.py`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 35 | 2 | Exports `ImageModel` Protocol | It's a Protocol, not a class. Can't instantiate it. | LOW |

## 7. `TRIKLobeServer.py`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 36 | 34 | `except FileNotFoundError as _` | Unused binding `_`. Unusual pattern. | LOW |
| 37 | 37 | `sys.exit(0)` on missing config | Exit code 0 = success. Missing config is a failure. PyInstaller UX choice. | MEDIUM |
| 38 | 36, 49-50 | `input("Press any key...")` | PyInstaller Windows workaround — without it, console closes instantly. | MEDIUM |

## 8. `pyproject.toml`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 39 | 5 | `requires-python = ">=3.10"` | Contradicts AGENTS.md "Python 3.12 required". Floor vs recommended. | MEDIUM |
| 40 | 10 | `numpy>=1.26.0,<2.0.0` | NumPy 2.0 breaking changes. Upper bound intentional but undocumented. | MEDIUM |
| 41 | 47 | N8xx naming rules all disabled | No comment explains why PEP8 naming is entirely suppressed. | MEDIUM |
| 42 | 62 | `extension-pkg-allow-list` | C extension introspection workaround. Non-obvious purpose. | LOW |
| 43 | 68 | `min-similarity-lines = 4` | Threshold choice. MODERNIZATION.md §12.9 has rationale, not inline. | LOW |

## 9. `AGENTS.md`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 44 | 11 | "Python 3.12 required" | Contradicts `pyproject.toml` `>=3.10`. "Required" vs "recommended". | MEDIUM |
| 45 | 73 | "92 tests" | Hardcoded count. Stale risk as tests grow. | LOW |

## 10. `.github/workflows/python-app.yml`

| # | Lines | Code | Why document? | Severity |
|---|-------|------|---------------|----------|
| 46 | 11 | `fail-fast: false` | Overriding default. Gets full cross-platform results even on failure. | LOW |
| 47 | 44 | Build only on push/dispatch | No build on PR. Avoids duplicate builds. Reasoning undocumented. | MEDIUM |
| 48 | 56 | `benjlevesque/short-sha@v4.0` | Third-party action, pinned to tag not SHA. Supply-chain risk unnoted. | MEDIUM |
| 49 | 71-72 | `settings.ini` in artifact | Bundles config with defaults (admin/admin). Security implications. | MEDIUM |
| 50 | 3-4 | Trigger on push AND PR | Every PR gets two test runs (known GH Actions behavior). | LOW |

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| **HIGH** | 7 | Must document — agent would fundamentally misunderstand code |
| **MEDIUM** | 26 | Should document — agent would question the choice |
| **LOW** | 16 | Nice-to-have — improves completeness |

HIGH items to prioritize:

1. **#12** `server.py:44-45` — `"-1"` sentinel
1. **#18** `model.py:118-121` — NCHW detection heuristic
1. **#21** `model.py:136-139` — NHWC/NCHW 3D heuristic
1. **#25** `model.py:181-182` — TFLite unguarded 4-dim assumption
1. **#29** `camera.py:44-45` — TRIK robot camera API
1. **#32** `protocol.py` — entire file needs module docstring
1. **#34** `protocol.py:10` — `9:data:quit` magic string
