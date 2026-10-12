#!/usr/bin/env python3
# ruff: noqa: N999, S311 — script filename with hyphen, demo uses random
"""
Generate ANSI demo output for screenshot pipeline.

Emits two .ansi files (dark + light) with a realistic prediction sequence
using Apple/Banana/Cherry/Dewberry labels, 10-17 FPS, 3 label changes.

Usage:
    uv run scripts/gen-demo.py                    # writes .tmp/demo-*.ansi
    uv run scripts/gen-demo.py  --out /tmp/       # custom output dir
"""

from __future__ import annotations

import io
import os
import random
import shutil
import sys
import time as _time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_LABELS = ["Apple", "Banana", "Cherry", "Dewberry"]
_TERM = os.terminal_size((81, 50))


def _top3(ix: int) -> list[tuple[str, float]]:
    return [(_LABELS[(ix + i) % 4], max(0.95 - i * 0.18, 0.01)) for i in range(3)]


def _fixed_term(*_args: object) -> os.terminal_size:
    """Pinned terminal size so screenshots are deterministic."""
    return _TERM


def capture_demo(*, color: bool) -> str:
    """Feed a realistic prediction sequence and return captured ANSI output."""
    random.seed(42)
    old_term = shutil.get_terminal_size
    shutil.get_terminal_size = _fixed_term

    cap = io.StringIO()
    cap.isatty = lambda: True
    old_stderr = sys.stderr
    sys.stderr = cap

    import trik_mind.output as m  # noqa: PLC0415

    m._HAS_UNICODE = True  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    fmt = m.UserOutputFormatter(color_enabled=color)
    fmt._raw_width = 79  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    fmt._width = 79  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    fmt.set_context("fruit_classifier.onnx  |  USB@640x480")
    fmt._change_t0 = fmt._last_change_time = _time.monotonic()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # Apple (15 frames) → Banana (8) → Cherry (6) → Apple (ends on a change)
    for _ in range(15):
        fmt.on_prediction("Apple", round(0.97 - random.uniform(0, 0.06), 3), 0.028 + random.uniform(0, 0.018), _top3(0))
        _time.sleep(0.0005)
    _time.sleep(0.002)
    fmt.on_prediction("Banana", round(0.80 + random.uniform(0, 0.04), 3), 0.031, _top3(1))
    for _ in range(8):
        fmt.on_prediction(
            "Banana", round(0.85 - random.uniform(0, 0.05), 3), 0.029 + random.uniform(0, 0.012), _top3(1)
        )
        _time.sleep(0.0005)
    _time.sleep(0.002)
    fmt.on_prediction("Cherry", round(0.70 + random.uniform(0, 0.04), 3), 0.033, _top3(2))
    for _ in range(6):
        fmt.on_prediction(
            "Cherry", round(0.73 + random.uniform(-0.03, 0.03), 3), 0.030 + random.uniform(0, 0.015), _top3(2)
        )
        _time.sleep(0.0005)
    _time.sleep(0.002)
    fmt.on_prediction("Apple", 0.95, 0.027, _top3(0))
    fmt.close()

    sys.stderr = old_stderr
    shutil.get_terminal_size = old_term
    return cap.getvalue()


def main() -> None:
    out_dir = Path(".tmp")
    if "--out" in sys.argv:
        out_dir = Path(sys.argv[sys.argv.index("--out") + 1])
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, color in [("demo-dark.ansi", True), ("demo-light.ansi", False)]:
        data = capture_demo(color=color)
        path = out_dir / name
        path.write_text(data, encoding="utf-8")
        clean = data.replace("\033[J", "").replace("\033[4A", "")
        lines = [ln for ln in clean.split("\n") if ln.strip()]
        changes = sum(1 for ln in lines if "→" in ln or "->" in ln)
        print(f"{path}: {len(lines)} lines, {changes} changes")


if __name__ == "__main__":
    main()
