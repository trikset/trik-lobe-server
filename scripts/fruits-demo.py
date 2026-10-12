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
from trik_mind.locale import setup_locale
from trik_mind.output import UserOutputFormatter


class FruitDemo:
    """Generates a realistic prediction stream for visual QA of the dashboard.

    Emits a sequence of curated scenarios so every part of the new stacked
    letter-bar is exercised:
    - High-conf detection (normal)          — thick winner, thin runners
    - Apple/Peach confusion (near-tie)      — "peach misread as apple" case:
      both labels mid+, nearly equal split, visible as A|P segments
    - Confident split across 3 labels       — A/B/C segments all visible
    - Hold (winner between view & send)     — shown but NOT sent to robot
    - Low-conf / uncertain (no mid label)   — dim empty bar
    - Error (simulated camera failure)      — "---" row
    """

    LABELS: ClassVar[list[str]] = ["Apple", "Peach", "Banana", "Cherry"]
    VIEW_THRESHOLD: ClassVar[float] = 0.4
    SEND_THRESHOLD: ClassVar[float] = 0.6

    def __init__(self, formatter: UserOutputFormatter) -> None:
        self._fmt = formatter
        self._running = True
        self._label_ix = 0
        self._phase = "high"
        self._phase_countdown = 0
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

    def _signal(self, *_args: object) -> NoReturn:
        self._running = False
        self._fmt.close()
        raise SystemExit(0)

    def _dist(self, ix: int, scenario: str) -> tuple[str, float, list[tuple[str, float]]]:
        """Return (label, confidence, top_labels) for the given scenario.

        Scenarios select distinct distributions over the label pool so each
        stacked-bar case is visible: clear winner, near-tie, 3-way spread,
        and low-uncertainty (no mid+ label).
        """
        if scenario == "high":
            base = [0.94, 0.14, 0.06, 0.02]
        elif scenario == "peach":
            base = [0.85, 0.78, 0.05, 0.02]
        elif scenario == "spread":
            base = [0.82, 0.70, 0.58, 0.10]
        elif scenario == "hold":
            base = [0.55, 0.42, 0.12, 0.04]
        else:  # low
            base = [0.42, 0.34, 0.22, 0.15]
        jitter = [random.uniform(-0.02, 0.02) for _ in base]
        labels = sorted(  # keep sorted desc by confidence, like a real model
            [(self.LABELS[(ix + i) % 4], max(0.01, base[i] + jitter[i])) for i in range(4)],
            key=lambda x: -x[1],
        )
        return labels[0][0], round(labels[0][1], 3), labels

    def step(self) -> None:
        """Emit one prediction frame with varying confidence distributions."""
        # Manage phases
        self._phase_countdown -= 1
        if self._phase_countdown <= 0:
            # Pick a new scenario
            r = random.random()
            if r < 0.12:  # 12% chance: error burst
                self._phase = "error"
                self._phase_countdown = int(random.uniform(1, 3))
            elif r < 0.26:  # 14% chance: low-conf uncertainty (no mid label)
                self._phase = "low"
                self._phase_countdown = int(random.uniform(3, 7))
            elif r < 0.5:  # 24% chance: apple/peach confusion (near-tie)
                self._phase = "peach"
                self._phase_countdown = int(random.uniform(5, 12))
                self._label_ix = 0  # force Apple-lead so Peach appears as runner
            elif r < 0.62:  # 12% chance: winner between view and send — shown, held back
                self._phase = "hold"
                self._phase_countdown = int(random.uniform(4, 8))
            else:  # 38% chance: normal high-conf detection
                self._phase = "high"
                self._phase_countdown = int(random.uniform(8, 16))
                self._label_ix = (self._label_ix + 1) % 4

        timing = 0.028 + random.uniform(0, 0.015)
        sleep_s = 1.0 / (10 + random.uniform(0, 7))

        if self._phase == "error":
            label, conf, labels = self._dist(self._label_ix, "low")
            self._fmt.on_error(timing, labels)
            time.sleep(sleep_s)
            return

        label, conf, labels = self._dist(self._label_ix, self._phase)
        if conf < self.VIEW_THRESHOLD:
            self._fmt.on_error(timing, labels)
        else:
            self._fmt.on_prediction(label, conf, timing, labels, sent=conf >= self.SEND_THRESHOLD)
        self._label_ix = (self._label_ix + 1) % 4
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
    fmt.set_context("fruit_classifier.onnx  |  USB@640x480  |  Ctrl+C to stop")
    if not args.no_color and not fmt._tty:  # pyright: ignore[reportPrivateUsage]  # demo probes hidden TTY state
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
