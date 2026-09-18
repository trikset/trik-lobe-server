# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

"""
Console output formatters for per-detection feedback.

Two modes:
- UserOutputFormatter — btop/htop-style dashboard with box-drawing (stderr)
- StdoutOutputFormatter — tab-separated pipe-friendly output (stdout)

Auto-detects TTY, ANSI, and Unicode support for cross-platform robustness.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import sys
import time
from collections import deque

_CONF_TIER_HIGH = 0.8
_CONF_TIER_MID = 0.5
_STDOUT_EVERY_DETECTION = 2
_BOX_WIDTH = 72
_MIN_BAR_WIDTH = 10

_WIN = os.name == "nt"
_ENCODING = getattr(sys.stderr, "encoding", "") or ""
_HAS_UNICODE = _ENCODING.lower() in ("utf-8", "utf8", "utf-16le", "utf-16", "utf-32")

# Strip all ANSI escape sequences
_ANSI_RE = re.compile(r"\033\[[0-9;]*[mK]")


class _Unicode:
    BLOCK_FULL = "█"
    BLOCK_EMPTY = "░"
    PIPE = "│"
    ARROW_R = "→"
    DASH = "─"
    CORNER_TL = "╭"
    CORNER_TR = "╮"
    CORNER_BL = "╰"
    CORNER_BR = "╯"
    STAR = "★"


class _ASCII:
    BLOCK_FULL = "#"
    BLOCK_EMPTY = "·"
    PIPE = "|"
    ARROW_R = "->"
    DASH = "-"
    CORNER_TL = "+"
    CORNER_TR = "+"
    CORNER_BL = "+"
    CORNER_BR = "+"
    STAR = "*"


def _strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from a string."""
    return _ANSI_RE.sub("", text)


def _visible_len(text: str) -> int:
    """Length of text ignoring ANSI escape sequences."""
    return len(_strip_ansi(text))


def _enable_vt() -> bool:  # pragma: no cover (Windows-only)
    """
    Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING on Windows 10+.

    Returns True if successful, False otherwise.
    """
    if not _WIN:
        return True
    try:
        import ctypes as _ct  # noqa: PLC0415

        kernel32 = _ct.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = _ct.c_ulong(0)
        if kernel32.GetConsoleMode(handle, _ct.byref(mode)):
            mode.value |= 0x0004
            kernel32.SetConsoleMode(handle, mode)
            return True
    except Exception:  # noqa: BLE001,S110  # nosec
        pass
    return False


class UserOutputFormatter:
    r"""
    btop/htop-style dashboard with box-drawing, colored bars, and top-N.

    Prints a compact 3-line panel to stderr on every prediction. On label
    change, appends a persistent event line below the panel.
    """

    _GREEN = "\033[92m"
    _YELLOW = "\033[93m"
    _RED = "\033[91m"
    _BOLD = "\033[1m"
    _RESET = "\033[0m"
    _DIM = "\033[2m"
    _BLUE = "\033[94m"

    PREDICTION_INTERVAL = 0.2

    def __init__(self, *, color_enabled: bool = True) -> None:
        self._color = color_enabled and sys.stderr.isatty()
        self._tty = sys.stderr.isatty()
        self._glyphs = _Unicode if _HAS_UNICODE else _ASCII
        self._width = _BOX_WIDTH
        if _WIN and self._color and not _enable_vt():
            self._color = False  # pragma: no cover  # ANSI not available on older Windows
        if self._tty:
            with contextlib.suppress(ValueError, OSError):  # pragma: no cover (CI/headless terminal size)
                self._width = max(shutil.get_terminal_size().columns - 2, 40)

        self._prev_label: str | None = None
        self._total_count = 0
        self._change_t0 = time.monotonic()
        self._dets_since_change = 0
        self._inference_times: deque[float] = deque(maxlen=50)
        self._first_output = True
        self._context: str | None = None
        self._last_change_time = 0.0
        # Buffer non-TTY lines for batched writes
        self._buf: list[str] = []

    def set_context(self, context: str) -> None:
        """Set context header shown above the dashboard on first output."""
        self._context = context

    # ---- helpers ----

    def _write(self, text: str) -> None:
        """Write text to stderr, buffering in non-TTY mode."""
        if self._tty:
            sys.stderr.write(text)
            sys.stderr.flush()
        else:
            self._buf.append(text)

    def _flush_buf(self) -> None:
        """Flush non-TTY buffer as a single write."""
        if self._buf:
            sys.stderr.write("".join(self._buf))
            self._buf = []
        sys.stderr.flush()

    def _c(self, code: str, text: str) -> str:
        if not self._color:
            return text
        return f"{code}{text}{self._RESET}"

    def _cb(self, code: str, text: str) -> str:
        """Bold + color wrap."""
        if self._color:
            return self._c(self._BOLD, self._c(code, text))
        return f"*{text}*"

    def _tier(self, confidence: float) -> str:
        if confidence >= _CONF_TIER_HIGH:
            return self._GREEN
        if confidence >= _CONF_TIER_MID:
            return self._YELLOW
        return self._RED

    def _bar(self, confidence: float, width: int) -> str:
        filled = round(confidence * width)
        empty = max(0, width - filled)
        code = self._tier(confidence)
        return self._c(code, self._glyphs.BLOCK_FULL * filled + self._glyphs.BLOCK_EMPTY * empty)

    def _top_n(self, labels: list[tuple[str, float]], n: int = 3) -> str:
        parts: list[str] = []
        for lbl, conf in labels[:n]:
            pct = conf * 100
            parts.append(self._c(self._tier(conf), f"{lbl}({pct:.0f}%)"))
        return "  ".join(parts)

    # ---- panel builders ----

    def _build_top_line(self, label: str, confidence: float, fps: float) -> str:  # pylint: disable=too-many-locals
        g = self._glyphs
        tier = self._tier(confidence)
        pct = self._c(tier, f"{confidence * 100:.1f}%")

        is_fresh = self._last_change_time and time.monotonic() - self._last_change_time < 1.0
        lbl = (
            self._c(self._BOLD + tier, f"{g.STAR} {label}")
            if is_fresh and self._color
            else self._cb(tier, label)
        )

        fps_str = f"fps:{fps:.1f}"
        cnt_str = f"#{self._total_count}"

        label_part = f" {lbl}  {pct} "
        metrics = f" {fps_str}  {g.PIPE}  {cnt_str}"
        if self._prev_label is not None:
            held = time.monotonic() - self._change_t0
            metrics += f"  {g.PIPE}  \u0394 {held:.1f}s"

        label_len = _visible_len(label_part)
        gap = max(2, self._width - 4 - label_len - _visible_len(metrics))

        return f"{g.CORNER_TL}{g.DASH}{label_part}{g.DASH * gap}{metrics} {g.DASH}{g.CORNER_TR}"

    def _build_mid_line(self, confidence: float, labels: list[tuple[str, float]] | None) -> str:
        g = self._glyphs
        inner_w = self._width - 4
        bar_w = inner_w
        top_str = ""
        if labels and len(labels) > 1:
            top_str = f"  {g.PIPE}  {self._top_n(labels[:2])}"
            bar_w = max(_MIN_BAR_WIDTH, inner_w - _visible_len(top_str))
        bar_str = self._bar(confidence, bar_w)
        return f"{g.PIPE}{g.DASH}{bar_str}{top_str}{g.DASH}{g.PIPE}"

    def _build_bot_line(self) -> str:
        g = self._glyphs
        return f"{g.CORNER_BL}{g.DASH * (self._width - 2)}{g.CORNER_BR}"

    def _build_panel(
        self, label: str, confidence: float, fps: float, labels: list[tuple[str, float]] | None
    ) -> str:
        top = self._build_top_line(label, confidence, fps)
        mid = self._build_mid_line(confidence, labels)
        bot = self._build_bot_line()
        return f"{top}\n{mid}\n{bot}"

    # ---- main api ----

    def on_prediction(
        self,
        label: str,
        confidence: float,
        timing_s: float,
        top_labels: list[tuple[str, float]] | None = None,
    ) -> None:
        """Handle one prediction result. Writes the btop dashboard to stderr."""
        self._total_count += 1
        self._inference_times.append(timing_s)
        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)

        change_event: str | None = None
        if self._prev_label is not None and label != self._prev_label:
            held_s = time.monotonic() - self._change_t0
            g = self._glyphs
            top_str = ""
            if top_labels:
                top_str = f"  |  {self._top_n(top_labels)}"
            change_event = (
                f"{g.DASH * 2} {self._prev_label} {g.ARROW_R} {label}  "
                f"{confidence * 100:.1f}%  "
                f"(held {held_s:.1f}s, {self._dets_since_change} detections)"
                f"{top_str} {g.DASH * 2}"
            )
            self._change_t0 = time.monotonic()
            self._dets_since_change = 0
            self._last_change_time = time.monotonic()
        elif self._prev_label is None:
            self._change_t0 = time.monotonic()

        self._dets_since_change += 1
        self._prev_label = label

        panel = self._build_panel(label, confidence, fps, top_labels)

        if self._first_output:
            self._first_output = False
            g = self._glyphs
            if self._context:
                self._write(f"\n{self._context}\n{g.DASH * self._width}\n")
            if self._tty:
                self._write(f"{panel}\n")
            else:
                self._write(f"{panel}\n")
                self._flush_buf()
        elif self._tty:
            self._write(f"\033[3A\033[J{panel}")
        else:
            self._write(f"\n{panel}")
            self._flush_buf()

        if change_event:
            self._write(f"\n{change_event}\n")
            self._flush_buf()

    def on_error(
        self,
        timing_s: float,
        top_labels: list[tuple[str, float]] | None = None,  # noqa: ARG002  # pylint: disable=unused-argument
    ) -> None:
        # pylint: disable=too-many-locals
        """Camera failure: show error in the dashboard."""
        self._total_count += 1
        self._inference_times.append(timing_s)
        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)
        g = self._glyphs

        err = self._c(self._RED, "---")
        fstr = f"fps:{fps:.1f}"
        cstr = f"#{self._total_count}"
        label_part = f" {err}  {err} "
        metrics = f" {fstr}  {g.PIPE}  {cstr}"
        label_len = _visible_len(label_part)
        gap = max(2, self._width - 4 - label_len - _visible_len(metrics))

        top = f"{g.CORNER_TL}{g.DASH}{label_part}{g.DASH * gap}{metrics} {g.DASH}{g.CORNER_TR}"
        bar_chars = self._c(self._RED, self._glyphs.BLOCK_FULL * _MIN_BAR_WIDTH)
        mid = f"{g.PIPE}{g.DASH}{bar_chars}  camera error{g.DASH}{g.PIPE}"
        bot = f"{g.CORNER_BL}{g.DASH * (self._width - 2)}{g.CORNER_BR}"
        panel = f"{top}\n{mid}\n{bot}"

        if self._tty:
            self._write(f"\033[3A\033[J{panel}")
        else:
            self._write(f"\n{panel}")
            self._flush_buf()

    def close(self) -> None:
        """Release the display by moving below the panel."""
        self._flush_buf()
        if self._tty:
            sys.stderr.write("\n\n\033[J")
            sys.stderr.flush()


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

    def on_prediction(
        self,
        label: str,
        confidence: float,
        timing_s: float,
        top_labels: list[tuple[str, float]] | None = None,  # noqa: ARG002  # pylint: disable=unused-argument
    ) -> None:
        """Handle one prediction result. May print to stdout."""
        self._total_count += 1
        is_change = self._prev_label is not None and label != self._prev_label
        self._prev_label = label

        if self._verbose >= _STDOUT_EVERY_DETECTION or is_change or self._total_count == 1:
            timing_ms = round(timing_s * 1000)
            with contextlib.suppress(OSError):
                if self._verbose >= 1:
                    print(f"{label}\t{confidence:.3f}\t{timing_ms}ms", file=sys.stdout)  # noqa: T201
                else:
                    print(f"{label}\t{confidence:.3f}", file=sys.stdout)  # noqa: T201
                sys.stdout.flush()

    def on_error(self, timing_s: float, top_labels: list[tuple[str, float]] | None = None) -> None:  # noqa: ARG002  # pylint: disable=unused-argument
        """Camera failure. Suppressed unless verbose."""
        if self._verbose >= 1:
            timing_ms = round(timing_s * 1000)
            with contextlib.suppress(OSError):
                print(f"-1\t0.000\t{timing_ms}ms", file=sys.stdout)  # noqa: T201

    def close(self) -> None:
        """No-op — stdout needs no newline release."""
