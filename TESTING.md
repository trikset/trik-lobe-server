# Testing

<!-- encoding: utf-8 -->

Scope: Test strategy, coverage targets, mocking patterns, and known gaps.
Aim: Document how tests work, what is covered, and hard-won lessons about
async testing and mocking.
Structure: Overview → Running tests → Coverage config → Coverage notes → Gaps.

## Overview

100% coverage. All mock-based — no real camera, network, or TFLite
runtime needed. Test count is a live metric — see AGENTS.md Live metrics.

## Running tests

```bash
uv run pytest                         # full suite + coverage
uv run pytest --no-cov                # skip coverage (faster locally)
uv run pytest tests/test_model.py::test_onnx_model_load_with_signature_json --exitfirst  # single test
```

### Diagnostic discipline

- **`--tb=long` during development**, `-q` only for final green check
- **Batch before re-run**: found one failure? grep for siblings and fix
  all before re-running — each re-run costs the full suite
- **Baseline first**: unexpected errors? stash changes, run same command.
  If errors persist → pre-existing (5-min timebox)

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

### Windows-specific test patterns

- **`socket.socketpair()` returns `AF_INET` on Windows** but `AF_UNIX` on
  macOS/Linux. This affects `getsockname()` return values. Tests that need
  `getsockname()` should patch it on the class, not the instance.
- **`tempfile.NamedTemporaryFile(delete=False)`** can fail on Windows because
  the OS prevents reopening a file still held by the creating handle.
  Use `TemporaryDirectory` + `Path.write_text()` instead.
- **`asyncio.get_event_loop()`** is deprecated. Use `get_running_loop()`.
  Pytest-asyncio always provides a running loop, so the replacement is safe.

### Coverage verification

After adding tests, verify with `--cov-report=term-missing` that
the specific lines you intended to cover actually are. Passing tests
do not guarantee coverage — async race conditions can silently skip lines.

### Edge case audit

Every test batch must consider and test:

- Empty/null inputs
- Boundary values (0, max length)
- Corrupt or malformed data
- Failure modes (file missing, corrupt model, permission denied)

Where edge cases emerge during testing, improve process documentation:
what was missed and how to catch it next time.

## Coverage

Coverage is 100% across all modules (`--cov-fail-under=100` enforced in CI).
All code paths are exercised via mocks — no real camera, network, or TFLite
runtime needed.

Hardware-dependent behavior is verified through mocked interfaces:

- `WebcamCamera` init and failure paths — via a mocked `cv2` module
- TCP connect / `run_forever` / reader — via `socket.socketpair()` and
  mocked sockets
- ONNX shape inference and TF `:0` input-name suffix — via mocked
  `InferenceSession` inputs

Paths that require real hardware (physical camera, real robot, real model
file) are intentionally exercised only at integration level, never in CI.
