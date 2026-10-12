# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# ruff: noqa: S311, PLR2004  # demo RNG + hardcoded scenario thresholds (curated for visual QA)

"""
Fake fruit-classifier predictions for the standalone --demo dashboard.

The real pipeline (TRIKMind) feeds live model output into
``UserOutputFormatter``. This module simulates that stream so the dashboard
can be demoed without a camera, a model or a robot connection.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from trik_mind.output import UserOutputFormatter


class DemoSource:
    """
    Generates realistic fake predictions to exercise the dashboard.

    Emits curated scenarios so every stacked letter-bar case is visible:
    high-conf detection, Apple/Peach near-tie, 3-way spread, hold (shown but
    not sent), low-uncertainty (below view threshold) and camera errors.

    The pipeline polls the fake camera every frame but inference finishes
    once per :data:`FRAMES_PER_DETECTION`, so events arrive at
    ``fps / FRAMES_PER_DETECTION`` per second while the fps counter reads
    ~``fps``.
    """

    LABELS: ClassVar[list[str]] = ["Apple", "Peach", "Banana", "Cherry"]
    VIEW_THRESHOLD: ClassVar[float] = 0.4
    SEND_THRESHOLD: ClassVar[float] = 0.6
    FRAMES_PER_DETECTION: ClassVar[int] = 5

    def __init__(self, formatter: UserOutputFormatter, fps: float = 16.0) -> None:
        self._fmt = formatter
        self._fps = fps
        self._label_ix = 0
        self._phase = "high"
        self._phase_countdown = 0
        self._frames_left = 1

    def _dist(self, ix: int, scenario: str) -> tuple[str, float, list[tuple[str, float]]]:
        """
        Return (label, confidence, top_labels) for the given scenario.

        Scenarios select distinct distributions over the label pool so each
        stacked-bar case is visible: clear winner, near-tie, 3-way spread,
        low-uncertainty (winner below the view threshold) and hold (winner
        between view and send).
        """
        if scenario == "high":
            base = [0.94, 0.14, 0.06, 0.02]
        elif scenario == "peach":
            base = [0.85, 0.78, 0.05, 0.02]
        elif scenario == "spread":
            base = [0.82, 0.70, 0.58, 0.10]
        elif scenario == "hold":
            base = [0.55, 0.42, 0.12, 0.04]
        else:  # low — winner below the view threshold
            base = [0.36, 0.30, 0.22, 0.15]
        jitter = [random.uniform(-0.02, 0.02) for _ in base]  # nosec B311 — demo jitter
        labels = sorted(
            [(self.LABELS[(ix + i) % 4], max(0.01, base[i] + jitter[i])) for i in range(4)],
            key=lambda x: -x[1],
        )
        return labels[0][0], round(labels[0][1], 3), labels

    def step(self) -> None:
        """Advance the pipeline one frame; emit a detection every N frames."""
        period = 1.0 / self._fps
        self._frames_left -= 1
        if self._frames_left > 0:
            time.sleep(period)
            return
        self._frames_left = self.FRAMES_PER_DETECTION

        # Manage phases
        self._phase_countdown -= 1
        if self._phase_countdown <= 0:
            r = random.random()  # nosec B311 — demo phase picker
            if r < 0.12:  # 12% chance: error burst
                self._phase = "error"
                self._phase_countdown = int(random.uniform(1, 3))  # nosec B311 — demo pacing
            elif r < 0.26:  # 14% chance: low-conf uncertainty (below view threshold)
                self._phase = "low"
                self._phase_countdown = int(random.uniform(3, 7))  # nosec B311 — demo pacing
            elif r < 0.5:  # 24% chance: apple/peach confusion (near-tie)
                self._phase = "peach"
                self._phase_countdown = int(random.uniform(5, 12))  # nosec B311 — demo pacing
                self._label_ix = 0  # force Apple-lead so Peach appears as runner
            elif r < 0.62:  # 12% chance: winner between view and send — shown, held back
                self._phase = "hold"
                self._phase_countdown = int(random.uniform(4, 8))  # nosec B311 — demo pacing
            else:  # 38% chance: normal high-conf detection
                self._phase = "high"
                self._phase_countdown = int(random.uniform(8, 16))  # nosec B311 — demo pacing
                self._label_ix = (self._label_ix + 1) % 4

        # Mean per-frame inference time settles at 1/fps (fps counter reads
        # ~fps); each frame slot lasts exactly 1/fps, so detection frames land
        # at fps/5 per second (see class doc).
        timing = max(0.002, period + random.uniform(-0.15 * period, 0.15 * period))  # nosec B311 — demo jitter

        if self._phase == "error":
            label, conf, labels = self._dist(self._label_ix, "low")
            self._fmt.on_error(timing, labels)
            time.sleep(period)
            return

        label, conf, labels = self._dist(self._label_ix, self._phase)
        if conf < self.VIEW_THRESHOLD:
            self._fmt.on_error(timing, labels)
        else:
            self._fmt.on_prediction(label, conf, timing, labels, sent=conf >= self.SEND_THRESHOLD)
        self._label_ix = (self._label_ix + 1) % 4
        time.sleep(period)

    def run(self) -> None:
        """Run the demo dashboard until KeyboardInterrupt (Ctrl+C)."""
        while True:
            self.step()
