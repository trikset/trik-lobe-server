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
from lobe_server.output import UserOutputFormatter


def _fruit_sequence(label_ix: int) -> list[tuple[str, float]]:
    """Top-3 labels around the given index with declining confidence."""
    labels = ["Apple", "Banana", "Cherry", "Dewberry"]
    return [(labels[(label_ix + i) % 4], max(0.95 - i * 0.18, 0.01)) for i in range(3)]


class FruitDemo:
    """Generates a realistic prediction stream for visual QA of the dashboard."""

    LABELS: ClassVar[list[str]] = ["Apple", "Banana", "Cherry", "Dewberry"]

    def __init__(self, formatter: UserOutputFormatter) -> None:
        self._fmt = formatter
        self._running = True
        self._label_ix = 0
        self._same = 0
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

    def _signal(self, *_args: object) -> NoReturn:
        self._running = False
        self._fmt.close()
        raise SystemExit(0)

    def step(self) -> None:
        """Emit one prediction frame and sleep to simulate 10-17 FPS."""
        if self._same >= 8 + int(random.uniform(0, 7)):
            self._label_ix = (self._label_ix + 1) % 4
            self._same = 0

        label = self.LABELS[self._label_ix]
        conf = round(0.95 - random.uniform(0, 0.12), 3)
        timing = 0.028 + random.uniform(0, 0.015)
        self._fmt.on_prediction(label, conf, timing, _fruit_sequence(self._label_ix))
        self._same += 1
        time.sleep(1.0 / (10 + random.uniform(0, 7)))

    def run(self, duration: float | None) -> None:
        """Run predictions for *duration* seconds (None = forever)."""
        start = time.monotonic()
        while self._running:
            self.step()
            if duration is not None and time.monotonic() - start >= duration:
                break
        self._fmt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fruit classifier live dashboard demo")
    parser.add_argument(
        "--unlimit",
        action="store_true",
        help="Run continuously (default: 3 seconds)",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    args = parser.parse_args()

    fmt = UserOutputFormatter(color_enabled=not args.no_color)
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
