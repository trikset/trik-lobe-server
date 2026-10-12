#!/usr/bin/env python3
# ruff: noqa: N999 — script filename with hyphen is intentional
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
from typing import NamedTuple

_Term = NamedTuple("TermSize", ("columns", "lines"))(81, 50)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_LABELS = ["Apple", "Banana", "Cherry", "Dewberry"]
_TERM = Namedtuple("TermSize", ("columns", "lines"))(81, 50)


def _top3(ix: int) -> list[tuple[str, float]]:
    return [(_LABELS[(ix + i) % 4], max(0.95 - i * 0.18, 0.01)) for i in range(3)]


def capture_demo(color: bool) -> str:
    """Feed a realistic prediction sequence through UserOutputFormatter and return ANSI."""
    random.seed(42)
    old_term = shutil.get_terminal_size
    shutil.get_terminal_size = lambda f=(): _TERM

    cap = io.StringIO()
    cap.isatty = lambda: True
    old_stderr = sys.stderr
    sys.stderr = cap

    import lobe_server.output as m  # noqa: PLC0415 — import after stderr swap

    m._HAS_UNICODE = True  # noqa: SLF001 — force Unicode glyphs for the screenshot
    fmt = m.UserOutputFormatter(color_enabled=color)
    fmt._raw_width = 79  # noqa: SLF001
    fmt._width = 79  # noqa: SLF001

    fmt.set_context("fruit_classifier.onnx  |  USB@640x480")
    fmt._change_t0 = fmt._last_change_time = _time.monotonic()  # noqa: SLF001

    # Apple high-conf (15 frames) → Banana (8) → Cherry (6) → Apple (change, ends)
    for _ in range(15):
        fmt.on_prediction("Apple", round(0.97 - random.uniform(0, 0.06), 3),
                          0.028 + random.uniform(0, 0.018), _top3(0))
        _time.sleep(0.0005)
    _time.sleep(0.002)
    fmt.on_prediction("Banana", round(0.80 + random.uniform(0, 0.04), 3), 0.031, _top3(1))
    for _ in range(8):
        fmt.on_prediction("Banana", round(0.85 - random.uniform(0, 0.05), 3),
                          0.029 + random.uniform(0, 0.012), _top3(1))
        _time.sleep(0.0005)
    _time.sleep(0.002)
    fmt.on_prediction("Cherry", round(0.70 + random.uniform(0, 0.04), 3), 0.033, _top3(2))
    for _ in range(6):
        fmt.on_prediction("Cherry", round(0.73 + random.uniform(-0.03, 0.03), 3),
                          0.030 + random.uniform(0, 0.015), _top3(2))
        _time.sleep(0.0005)
    _time.sleep(0.002)
    fmt.on_prediction("Apple", 0.95, 0.027, _top3(0))  # ends on a change
    fmt.close()

    sys.stderr = old_stderr
    shutil.get_terminal_size = old_term
    return cap.getvalue()


def main() -> None:
    out_dir = ".tmp"
    if "--out" in sys.argv:
        out_dir = sys.argv[sys.argv.index("--out") + 1]
    os.makedirs(out_dir, exist_ok=True)

    for name, color in [("demo-dark.ansi", True), ("demo-light.ansi", False)]:
        data = capture_demo(color=color)
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        clean = data.replace("\033[J", "").replace("\033[4A", "")
        lines = [l for l in clean.split("\n") if l.strip()]
        changes = sum(1 for l in lines if "→" in l or "->" in l)
        print(f"{path}: {len(lines)} lines, {changes} changes")


if __name__ == "__main__":
    main()
