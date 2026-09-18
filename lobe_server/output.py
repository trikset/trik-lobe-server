# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

"""
Console output formatters for per-detection feedback.

Two modes:
- UserOutputFormatter — ANSI-colored live line + change events (stderr)
- StdoutOutputFormatter — tab-separated pipe-friendly output (stdout)

Auto-detects TTY, ANSI, and Unicode support for cross-platform robustness.
"""

from __future__ import annotations

import os
import sys
import time
from collections import deque

_CONF_TIER_HIGH = 0.8
_CONF_TIER_MID = 0.5
_STDOUT_EVERY_DETECTION = 2

_WIN = os.name == "nt"
_ENCODING = getattr(sys.stderr, "encoding", "") or ""
_HAS_UNICODE = _ENCODING.lower() in ("utf-8", "utf8", "utf-16le", "utf-16", "utf-32")


class _Unicode:
    BLOCK_FULL = "██"
    BLOCK_EMPTY = "░░"
    PIPE = "│"
    ARROW_R = "→"
    DASH = "─"
    CIRCLE_S = "⎡"
    CIRCLE_E = "⎤"


class _ASCII:
    BLOCK_FULL = "##"
    BLOCK_EMPTY = "··"
    PIPE = "|"
    ARROW_R = "->"
    DASH = "-"
    CIRCLE_S = "["
    CIRCLE_E = "]"


def _enable_vt() -> None:  # pragma: no cover (Windows-only)
    """Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING on Windows 10+."""
    if not _WIN:
        return
    try:
        import ctypes as _ct  # noqa: PLC0415

        kernel32 = _ct.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE = -11
        mode = _ct.c_ulong(0)
        if kernel32.GetConsoleMode(handle, _ct.byref(mode)):
            mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, mode)
    except Exception:  # noqa: BLE001,S110  # nosec  # best-effort on any Windows version; may lack ctypes
        pass  # Windows too old or not a console — ANSI won't work, proceed without it


class UserOutputFormatter:
    r"""
    Terminal output for human readers.

    Uses ANSI colors, Unicode glyphs, and a ``\r``-refreshed live line when
    connected to a capable terminal. Falls back to plain text per-detection
    lines when the terminal lacks Unicode, ANSI, or is not a TTY.
    """

    _COLOR_GREEN = "\033[92m"
    _COLOR_YELLOW = "\033[93m"
    _COLOR_RED = "\033[91m"
    _COLOR_BOLD = "\033[1m"
    _COLOR_RESET = "\033[0m"

    def __init__(self, *, color_enabled: bool = True) -> None:
        self._color = color_enabled and sys.stderr.isatty()
        self._tty = sys.stderr.isatty()
        self._glyphs = _Unicode if _HAS_UNICODE else _ASCII
        if _WIN and self._color:  # pragma: no cover (Windows-only)
            _enable_vt()

        self._prev_label: str | None = None
        self._total_count = 0
        self._start_time = time.monotonic()
        self._change_t0 = time.monotonic()
        self._dets_since_change = 0
        self._inference_times: deque[float] = deque(maxlen=50)
        self._first_output = True
        self._context: str | None = None

    def set_context(self, context: str) -> None:
        """Set a header line printed once before the first live output."""
        self._context = context

    def _w(self, text: str) -> None:
        """Write text to stderr."""
        sys.stderr.write(text)
        sys.stderr.flush()

    def _c(self, code: str, text: str) -> str:
        """Wrap text in ANSI code if color is enabled."""
        if not self._color:
            return text
        return f"{code}{text}{self._COLOR_RESET}"

    def _confidence_tier(self, confidence: float) -> tuple[str, str]:
        """Return (ANSI_code, block_char) for a confidence level."""
        if confidence >= _CONF_TIER_HIGH:
            return self._COLOR_GREEN, self._glyphs.BLOCK_FULL
        if confidence >= _CONF_TIER_MID:
            return self._COLOR_YELLOW, self._glyphs.BLOCK_FULL
        return self._COLOR_RED, self._glyphs.BLOCK_FULL

    def _confidence_bar(self, confidence: float, width: int = 10) -> str:
        """Build 10-block confidence bar (1 block = 10%)."""
        filled = round(confidence * width)
        empty = width - filled
        code, block = self._confidence_tier(confidence)
        bar_str = block * filled + self._glyphs.BLOCK_EMPTY * empty
        return self._c(code, bar_str)

    def _uptime_str(self) -> str:
        """Format session uptime as a compact string."""
        elapsed = time.monotonic() - self._start_time
        mins, secs = divmod(int(elapsed), 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"\u2191 {hours}h {mins}m"
        return f"\u2191 {mins}m {secs}s"

    def on_prediction(self, label: str, confidence: float, timing_s: float) -> None:
        """Handle one prediction result. Writes to stderr."""
        self._total_count += 1
        self._inference_times.append(timing_s)

        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)

        # Change detection
        change_event: str | None = None
        if self._prev_label is not None and label != self._prev_label:
            held_s = time.monotonic() - self._change_t0
            g = self._glyphs
            change_event = (
                f"{g.DASH * 2} {self._prev_label} {g.ARROW_R} {label}  "
                f"{confidence * 100:.1f}%  "
                f"(held {held_s:.1f}s, {self._dets_since_change} detections) {g.DASH * 2}"
            )
            self._change_t0 = time.monotonic()
            self._dets_since_change = 0
        elif self._prev_label is None:
            self._change_t0 = time.monotonic()

        self._dets_since_change += 1

        # Build output line
        pct = confidence * 100
        tier_code, _ = self._confidence_tier(confidence)
        label_display = self._c(self._COLOR_BOLD + tier_code, label)
        pct_display = self._c(tier_code, f"{pct:.1f}%")
        bar_display = self._confidence_bar(confidence)

        g = self._glyphs

        self._prev_label = label

        line = (
            f"{g.CIRCLE_S} {label_display} {g.CIRCLE_E}  "
            f"{pct_display}  {bar_display}  {g.PIPE}  "
            f"FPS {fps:.1f}  {g.PIPE}  #{self._total_count}  {g.PIPE}  {self._uptime_str()}"
        )

        # On first output: print context header, then the first live line
        if self._first_output:
            self._first_output = False
            if self._context:
                self._w(f"\n{self._context}\n{g.DASH * 40}\n")
            if self._tty:
                self._w(f"\r{line}")
                self._w("\n")  # header + first line, then return for subsequent updates
                return
            self._w(line.rstrip() + "\n")
            return

        if change_event:
            self._w(f"\n{change_event}\n")

        if self._tty:
            self._w(f"\r{line}")
        else:
            self._w(line.rstrip() + "\n")

    def on_error(self, timing_s: float) -> None:
        """Camera failure: show error in the output."""
        self._total_count += 1
        self._inference_times.append(timing_s)
        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)
        g = self._glyphs

        line = (
            f"{g.CIRCLE_S} --- {g.CIRCLE_E}  ---  {g.PIPE}  "
            f"FPS {fps:.1f}  {g.PIPE}  #{self._total_count}  {g.PIPE}  camera error"
        )

        if self._tty:
            sys.stderr.write(f"\r{line}")
        else:
            sys.stderr.write(line.rstrip() + "\n")
        sys.stderr.flush()

    def close(self) -> None:
        """Release the live line by printing a final newline."""
        if self._tty:
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
