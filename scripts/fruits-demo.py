# ruff: noqa: S311, SLF001, N999
"""Fruit classifier demo — runs the live dashboard with fake predictions.

Usage:
    uv run scripts/fruits-demo.py          # 3-second demo
    uv run scripts/fruits-demo.py --unlimit  # run until Ctrl+C
"""

from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from typing import ClassVar, NoReturn

sys.path.insert(0, "")
from lobe_server.locale import setup_locale
from lobe_server.output import UserOutputFormatter


class FruitDemo:
    """Generates a realistic prediction stream for visual QA of the dashboard.

    Emits three types of events:
    - High‑conf detection (normal)
    - Low‑conf / uncertain (simulates no clear label)
    - Error (simulates camera / model failure)
    """

    LABELS: ClassVar[list[str]] = ["Apple", "Banana", "Cherry", "Dewberry"]

    def __init__(self, formatter: UserOutputFormatter) -> None:
        self._fmt = formatter
        self._running = True
        self._label_ix = 0
        self._same = 0
        self._phase = "high"
        self._phase_countdown = 0
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

    def _signal(self, *_args: object) -> NoReturn:
        self._running = False
        self._fmt.close()
        raise SystemExit(0)

    def _top(self, ix: int, base: float = 0.95) -> list[tuple[str, float]]:
        """Top‑3 labels with declining confidence from *base*."""
        return [(self.LABELS[(ix + i) % 4], max(base - i * 0.18, 0.01)) for i in range(3)]

    def step(self) -> None:
        """Emit one prediction frame with varying confidence levels."""
        # Manage phases
        self._phase_countdown -= 1
        if self._phase_countdown <= 0:
            # Pick a new phase
            r = random.random()
            if r < 0.15:          # 15% chance: error burst
                self._phase = "error"
                self._phase_countdown = int(random.uniform(1, 3))
            elif r < 0.30:        # 15% chance: low‑conf uncertainty
                self._phase = "low"
                self._phase_countdown = int(random.uniform(3, 7))
            else:                  # 70% chance: normal high‑conf detection
                self._phase = "high"
                self._phase_countdown = int(random.uniform(8, 16))
                self._label_ix = (self._label_ix + 1) % 4
                self._same = 0

        timing = 0.028 + random.uniform(0, 0.015)
        sleep_s = 1.0 / (10 + random.uniform(0, 7))

        if self._phase == "error":
            self._fmt.on_error(timing, self._top(self._label_ix, 0.1))
            time.sleep(sleep_s)
            return

        if self._phase == "low":
            # All labels have similar low confidence — model is uncertain
            low_base = 0.1 + random.uniform(0, 0.15)
            label = self.LABELS[self._label_ix]
            conf = round(low_base + random.uniform(0, 0.08), 3)
            self._fmt.on_prediction(label, conf, timing, self._top(self._label_ix, low_base))
            time.sleep(sleep_s)
            return

        # High‑conf normal detection
        if self._same >= 8 + int(random.uniform(0, 7)):
            self._label_ix = (self._label_ix + 1) % 4
            self._same = 0
        label = self.LABELS[self._label_ix]
        conf = round(0.95 - random.uniform(0, 0.12), 3)
        self._fmt.on_prediction(label, conf, timing, self._top(self._label_ix, 0.95))
        self._same += 1
        time.sleep(sleep_s)

    def run(self, duration: float | None) -> None:
        """Run predictions for *duration* seconds (None = forever)."""
        start = time.monotonic()
        while self._running:
            self.step()
            if duration is not None and time.monotonic() - start >= duration:
                break
        self._fmt.close()


def main() -> None:
    setup_locale()  # install _() builtin so formatter can translate strings
    parser = argparse.ArgumentParser(description="Fruit classifier live dashboard demo")
    parser.add_argument(
        "--unlimit",
        action="store_true",
        help="Run continuously (default: 3 seconds)",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    args = parser.parse_args()

    fmt = UserOutputFormatter(color_enabled=not args.no_color)
    fmt.set_context("fruit_classifier.onnx  |  USB @ 640x480  |  Ctrl+C to stop")
    if not args.no_color and not fmt._tty:
        print("Note: color disabled (stderr is not a TTY)", file=sys.stderr)

    demo = FruitDemo(fmt)
    duration = None if args.unlimit else 3.0
    try:
        demo.run(duration)
        print("\nDemo finished.", file=sys.stderr)
    except KeyboardInterrupt:
        fmt.close()
        print("\nInterrupted.", file=sys.stderr)


if __name__ == "__main__":
    main()
