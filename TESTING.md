# Testing

<!-- encoding: utf-8 -->

Scope: Test strategy, coverage targets, mocking patterns, and known gaps.
Aim: Document how tests work, what is covered, and hard-won lessons about
async testing and mocking.
Structure: Overview → Running tests → Coverage config → Coverage notes → Gaps.

## Overview

87 tests, 100% coverage. All mock-based — no real camera, network, or TFLite
runtime needed.

## Running tests

```bash
uv run pytest                         # full suite + coverage
uv run pytest --no-cov                # skip coverage (faster locally)
uv run pytest tests/test_model.py::test_onnx_model_load_with_signature_json --exitfirst  # single test
```

Coverage config is single-sourced in `pyproject.toml`:
`addopts = "--cov"`, `source = ["lobe_server"]`, `fail_under = 100`.
CI runs bare `uv run pytest`.

## Coverage notes

### Camera mocking

`WebcamCamera.__init__` requires `cv2` (native C extension). Tests bypass it
with `patch.object(WebcamCamera, "__init__", return_value=None)`.
`@patch.dict("sys.modules", {"cv2": mock_cv2})` reaches 100% coverage.

### Dead code

`load_model` had unreachable TFLite fallback code (ONNX early return). Removed,
not tested.

### Async race conditions

`_handle_connection` cancel loop requires a blocking prediction so tasks are
still pending when reader finishes. Use `threading.Event` to block
`camera.capture()` in `asyncio.to_thread`.

### Patch targets

C-level builtins (e.g. `socket.getsockname`) can't be patched on instances —
`patch.object` raises "read-only attribute". Patch the class instead:
`patch.object(socket.socket, "getsockname", ...)`.

### Silent exception swallowing

`asyncio.wait(FIRST_COMPLETED)` silently swallows task exceptions:
if task A raises but B completes first, the exception is lost and
tests appear to pass. When you need to verify a task succeeds,
`await` it directly instead of wrapping in `asyncio.wait`.

### Coverage verification

After adding tests, verify with `--cov-report=term-missing` that
the specific lines you intended to cover actually are. Passing tests
do not guarantee coverage — async race conditions can silently skip lines.

## Coverage gaps

| Lines missed | Module | Why not tested? |
|---|---|---|
| `camera.py:62-67` | `WebcamCamera.__init__` | Requires `cv2` + a physical camera |
| `server.py:106-112` | `run_forever` success branch | Requires a real TCP server to connect to |
| `model.py:150` | `ONNXImageModel.load` `:0` suffix | Only triggers on TF SavedModel models (rare) |
| `model.py:136-146` | `ONNXImageModel.load` shape inference | Rare ONNX shapes (2D, 0D, dynamic dims) |

All gaps require real hardware (camera, network) or platform-specific packages.
