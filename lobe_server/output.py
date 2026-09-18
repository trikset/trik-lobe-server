# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

"""
Console output formatters for per-detection feedback.

Two modes:
- UserOutputFormatter — ANSI-colored live line + change events (stderr)
- StdoutOutputFormatter — tab-separated pipe-friendly output (stdout)
"""

from __future__ import annotations

import sys
import time
from collections import deque

_CONF_TIER_HIGH = 0.8
_CONF_TIER_MID = 0.5
_STDOUT_EVERY_DETECTION = 2


class UserOutputFormatter:
    r"""
    ANSI-colored live terminal output, refreshed in-place via ``\r``.

    Prints a compact status line to stderr on every prediction. On label
    change, prints a persistent event line above the live line.
    """

    _COLOR_GREEN = "\033[92m"
    _COLOR_YELLOW = "\033[93m"
    _COLOR_RED = "\033[91m"
    _COLOR_BOLD = "\033[1m"
    _COLOR_RESET = "\033[0m"

    def __init__(self, *, color_enabled: bool = True) -> None:
        self._color = color_enabled
        self._prev_label: str | None = None
        self._total_count = 0
        self._change_t0 = time.monotonic()
        self._dets_since_change = 0
        self._inference_times: deque[float] = deque(maxlen=50)

    def _c(self, code: str, text: str) -> str:
        """Wrap text in ANSI code if color is enabled."""
        if not self._color:
            return text
        return f"{code}{text}{self._COLOR_RESET}"

    def _confidence_tier(self, confidence: float) -> tuple[str, str]:
        """Return (ANSI_code, block_char) for a confidence level."""
        if confidence >= _CONF_TIER_HIGH:
            return self._COLOR_GREEN, "█"
        if confidence >= _CONF_TIER_MID:
            return self._COLOR_YELLOW, "█"
        return self._COLOR_RED, "█"

    def _confidence_bar(self, confidence: float, width: int = 10) -> str:
        """Build 10-block confidence bar (1 block = 10%)."""
        filled = round(confidence * width)
        empty = width - filled
        code, block = self._confidence_tier(confidence)
        bar_str = block * filled + "░" * empty
        return self._c(code, bar_str)

    def on_prediction(self, label: str, confidence: float, timing_s: float) -> None:
        """Handle one prediction result. May print to stderr."""
        self._total_count += 1
        self._inference_times.append(timing_s)

        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)

        # Change detection
        change_event: str | None = None
        if self._prev_label is not None and label != self._prev_label:
            held_s = time.monotonic() - self._change_t0
            change_event = (
                f"── {self._prev_label} → {label}  "
                f"{confidence * 100:.1f}%  "
                f"(held {held_s:.1f}s, {self._dets_since_change} detections) ──"
            )
            self._change_t0 = time.monotonic()
            self._dets_since_change = 0
        elif self._prev_label is None:
            self._change_t0 = time.monotonic()

        self._dets_since_change += 1

        # Build the live line
        pct = confidence * 100
        tier_code, _ = self._confidence_tier(confidence)
        label_display = self._c(self._COLOR_BOLD + tier_code, label)
        pct_display = self._c(tier_code, f"{pct:.1f}%")
        bar_display = self._confidence_bar(confidence)

        last_change = ""
        if self._prev_label is not None:
            last_change = f"⤴ {self._prev_label} ({self._dets_since_change * self.PREDICTION_INTERVAL:.1f}s ago)"

        self._prev_label = label

        line = (
            f"⎡ {label_display} ⎤  {pct_display}  {bar_display}  │  "
            f"FPS {fps:.1f}  │  #{self._total_count}  │  {last_change}"
        )

        # Print change event first (persistent), then the live line (overwrites)
        file = sys.stderr
        if change_event:
            file.write(f"\n{change_event}\n")
        file.write(f"\r{line}")
        file.flush()

    def on_error(self, timing_s: float) -> None:
        """Camera failure — still show the error in the live line."""
        self._total_count += 1
        self._inference_times.append(timing_s)
        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)

        line = f"⎡ {'---'} ⎤  {'---'}  │  FPS {fps:.1f}  │  #{self._total_count}  │  camera error"
        sys.stderr.write(f"\r{line}")
        sys.stderr.flush()

    def close(self) -> None:
        """Release the live line by printing a final newline."""
        sys.stderr.write("\n")
        sys.stderr.flush()

    PREDICTION_INTERVAL = 0.2  # used for time-since-change display


class StdoutOutputFormatter:
    """
    Tab-separated output for piping, printed to stdout.

    Verbosity levels (``-v`` / ``-vv``):
        0 — label + confidence on label change
        1 — label + confidence + timing on label change
        2 — label + confidence + timing on every detection
    """

    def __init__(self, verbose: int = 0) -> None:
        self._verbose = verbose
        self._prev_label: str | None = None
        self._total_count = 0

    def on_prediction(self, label: str, confidence: float, timing_s: float) -> None:
        """Handle one prediction result. May print to stdout."""
        self._total_count += 1
        is_change = self._prev_label is not None and label != self._prev_label
        self._prev_label = label

        if self._verbose >= _STDOUT_EVERY_DETECTION or is_change or self._total_count == 1:
            timing_ms = round(timing_s * 1000)
            if self._verbose >= 1:
                print(f"{label}\t{confidence:.3f}\t{timing_ms}ms", file=sys.stdout)  # noqa: T201
            else:
                print(f"{label}\t{confidence:.3f}", file=sys.stdout)  # noqa: T201

    def on_error(self, timing_s: float) -> None:
        """Camera failure. Suppressed unless verbose."""
        if self._verbose >= 1:
            timing_ms = round(timing_s * 1000)
            print(f"-1\t0.000\t{timing_ms}ms", file=sys.stdout)  # noqa: T201

    def close(self) -> None:
        """No-op — stdout needs no newline release."""
