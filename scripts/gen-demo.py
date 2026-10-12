#!/usr/bin/env python3
# ruff: noqa: N999, S311 — script filename with hyphen, demo uses random
# pylint: disable=W0212  # demo pins output internals for deterministic screenshots
"""
Generate ANSI demo output for screenshot pipeline.

Emits two .ansi files (dark + light) with a realistic prediction sequence
exercising the threshold UI: high-conf detection, Apple/Peach near-tie
letter-bar, a hold row (shown, not sent) and sent rows.

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

_LABELS = ["Apple", "Peach", "Banana", "Cherry"]
_TERM = os.terminal_size((81, 50))
_VIEW = 0.4
_SEND = 0.6


def _dist(ix: int, scenario: str) -> list[tuple[str, float]]:
    base = {
        "high": [0.94, 0.14, 0.06, 0.02],
        "peach": [0.85, 0.78, 0.05, 0.02],
        "spread": [0.82, 0.70, 0.58, 0.10],
        "hold": [0.55, 0.42, 0.12, 0.04],
    }[scenario]
    jitter = [random.uniform(-0.02, 0.02) for _ in base]  # nosec B311 — demo jitter
    return sorted(
        [(_LABELS[(ix + i) % 4], max(0.01, base[i] + jitter[i])) for i in range(4)],
        key=lambda x: -x[1],
    )


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
    fmt = m.UserOutputFormatter(color_enabled=color, view_threshold=_VIEW)
    fmt._raw_width = 79  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    fmt._width = 79  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    fmt.set_context("fruit_classifier.onnx  |  USB@640x480")
    fmt._change_t0 = fmt._last_change_time = _time.monotonic()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def emit(scenario: str, ix: int, frames: int) -> None:
        for _ in range(frames):
            labels = _dist(ix, scenario)
            label, conf = labels[0][0], labels[0][1]
            if conf < _VIEW:
                fmt.on_error(0.028, labels)
            else:
                fmt.on_prediction(label, conf, 0.028, labels, sent=conf >= _SEND)
            _time.sleep(0.0005)

    # Apple (high) → Banana (hold) → Peach near-tie → Apple high (final, single label)
    emit("high", 0, 9)
    _time.sleep(0.002)
    emit("hold", 1, 6)
    _time.sleep(0.002)
    emit("peach", 0, 3)
    _time.sleep(0.002)
    emit("high", 0, 2)
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
        holds = sum(1 for ln in lines if "×" in ln or "x" in ln)  # noqa: RUF001
        sents = sum(1 for ln in lines if "↑" in ln or "^" in ln)
        print(f"   -> {holds} hold rows, {sents} sent rows")


if __name__ == "__main__":
    main()
