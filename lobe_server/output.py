# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

"""
Console output formatters for per-detection feedback.

Two modes:
- UserOutputFormatter — btop-style dashboard + compact stats bar (stderr)
- StdoutOutputFormatter — tab-separated pipe-friendly output (stdout)
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import sys
import time
from collections import Counter, deque

_CONF_TIER_HIGH = 0.8
_CONF_TIER_MID = 0.5
_STATS_FREQ_HIGH = 0.5
_STATS_FREQ_MID = 0.2
_STDOUT_EVERY_DETECTION = 2
_BOX_WIDTH = 72
_MAX_WIDTH = 120  # cap to prevent panel wrapping on huge terminal buffers
_MIN_BAR_WIDTH = 10
_STATS_LINE_LABELS = 4  # labels shown on the compact stats bar
_SHORT_LABEL_LEN = 4

_WIN = os.name == "nt"
_ENCODING = getattr(sys.stderr, "encoding", "") or ""
_HAS_UNICODE = _ENCODING.lower() in ("utf-8", "utf8", "utf-16le", "utf-16", "utf-32")
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
    return _ANSI_RE.sub("", text)


def _visible_len(text: str) -> int:
    return len(_strip_ansi(text))


def _enable_vt() -> bool:  # pragma: no cover (Windows-only)
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
    """
    btop-style live dashboard (3 lines) + compact cumulative stats bar (1 line).

    The stats bar shows the top N labels with mini bars and counts. On label
    change a persistent event line prints below the panel.
    Connection status is shown as a badge on the top line.
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
        self._raw_width = _BOX_WIDTH
        self._vt_ok = True
        if _WIN:  # pragma: no cover
            self._vt_ok = _enable_vt()
            if self._color and not self._vt_ok:
                self._color = False
        if self._tty:
            with contextlib.suppress(ValueError, OSError):  # pragma: no cover
                self._raw_width = max(shutil.get_terminal_size().columns - 2, 40)
                self._width = min(self._raw_width, _MAX_WIDTH)

        self._prev_label: str | None = None
        self._total_count = 0
        self._change_t0 = time.monotonic()
        self._dets_since_change = 0
        self._inference_times: deque[float] = deque(maxlen=50)
        self._first_output = True
        self._context: str | None = None
        self._last_change_time = 0.0
        self._status: str | None = None
        self._stats: Counter[str] = Counter()
        self._buf: list[str] = []
        self._last_width_check = 0.0

    def _refresh_width(self) -> None:
        """Re-check terminal width (may change on resize). Called once per frame."""
        if not self._tty:
            return
        now = time.monotonic()
        if now - self._last_width_check < 1.0:
            return
        self._last_width_check = now
        with contextlib.suppress(ValueError, OSError):
            cols = shutil.get_terminal_size().columns - 2
            if cols >= 40:  # noqa: PLR2004  # minimum terminal width for the box to fit
                self._raw_width = cols
                self._width = min(cols, _MAX_WIDTH)

    def _diagnostic(self) -> str:
        """Compact terminal diagnostic: Wraw→capped+encoding+VT+COL."""
        enc = (getattr(sys.stderr, "encoding", "") or "?").upper().replace("-", "")
        return "+".join([f"W{self._raw_width}>{self._width}", enc, f"VT{int(self._vt_ok)}", f"COL{int(self._color)}"])

    def set_context(self, context: str) -> None:
        self._context = context

    def set_status(self, status: str | None) -> None:
        """Set a transient status shown as a badge on the top line."""
        self._status = status

    # ---- helpers ----

    def _write(self, text: str) -> None:
        if self._tty:
            sys.stderr.write(text)
            sys.stderr.flush()
        else:
            self._buf.append(text)

    def _flush_buf(self) -> None:
        if self._buf:
            sys.stderr.write("".join(self._buf))
            self._buf = []
        sys.stderr.flush()

    def _c(self, code: str, text: str) -> str:
        if not self._color:
            return text
        return f"{code}{text}{self._RESET}"

    def _cb(self, code: str, text: str) -> str:
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

    # ---- dashboard panel (3 lines) ----

    def _dash_top(self, label: str, confidence: float, fps: float) -> str:  # pylint: disable=too-many-locals
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

        status_part = ""
        if self._status:
            status_part = f"  {g.PIPE}  {self._c(self._BOLD + self._YELLOW, self._status)}"

        metrics = f" {fps_str}  {g.PIPE}  {cnt_str}"
        if self._prev_label is not None and not self._status:
            held = time.monotonic() - self._change_t0
            metrics += f"  {g.PIPE}  \u0394 {held:.1f}s"

        label_len = _visible_len(label_part)
        diag = self._diagnostic()
        diag_len = _visible_len(diag)
        inner_w = self._width - 4
        # left side: label, right side: metrics + status + diagnostic
        right_part = f"{metrics}{status_part}"
        right_len = _visible_len(right_part)
        # If room for diagnostic + separators, include it
        if label_len + right_len + diag_len + 4 <= inner_w:
            gap = max(1, inner_w - label_len - right_len - diag_len - 2)
            return f"{g.CORNER_TL}{g.DASH}{label_part}{g.DASH * gap}{right_part} {diag} {g.DASH}{g.CORNER_TR}"
        gap = max(1, inner_w - label_len - right_len)
        return f"{g.CORNER_TL}{g.DASH}{label_part}{g.DASH * gap}{right_part} {g.DASH}{g.CORNER_TR}"

    def _dash_mid(self, confidence: float, labels: list[tuple[str, float]] | None) -> str:
        g = self._glyphs
        inner_w = self._width - 4
        bar_w = inner_w
        top_str = ""
        if labels and len(labels) > 1:
            top_str = f"  {g.PIPE}  {self._top_n(labels[:2])}"
            bar_w = max(_MIN_BAR_WIDTH, inner_w - _visible_len(top_str))
        return f"{g.PIPE}{g.DASH}{self._bar(confidence, bar_w)}{top_str}{g.DASH}{g.PIPE}"

    def _pct_bar(self, ratio: float, width: int) -> str:
        """Compact bar for the stats line — colored by frequency tier."""
        filled = round(ratio * width)
        empty = max(0, width - filled)
        code = self._GREEN if ratio >= _STATS_FREQ_HIGH else (self._YELLOW if ratio >= _STATS_FREQ_MID else self._RED)
        return self._c(code, self._glyphs.BLOCK_FULL * filled + self._glyphs.BLOCK_EMPTY * empty)

    # ---- stats bar (1 line, below dashboard) ----

    def _stats_line(self) -> str:
        """Compact 1-line stats bar: top N labels with mini bars + counts."""
        g = self._glyphs
        sorted_s = sorted(self._stats.items(), key=lambda x: -x[1])
        if not sorted_s:
            return f"{g.PIPE}{'  (no data)'.ljust(self._width - 4)}{g.PIPE}"

        inner_w = self._width - 4
        slots = _STATS_LINE_LABELS
        max_c = sorted_s[0][1]
        parts: list[str] = []
        for lbl, count in sorted_s[:slots]:
            ratio = count / max_c
            per_slot = min((inner_w - 2) // slots, 16)
            short = lbl if len(lbl) <= _SHORT_LABEL_LEN else lbl[:3] + "."
            bar_w = per_slot - len(short) - 6
            bar_w = max(bar_w, 2)
            bar_str = self._pct_bar(ratio, bar_w)
            parts.append(f"{short}{bar_str}{count}")
        return f"{g.PIPE}{'  '.join(parts).ljust(inner_w)}{g.PIPE}"

    def _build_bot(self) -> str:
        g = self._glyphs
        return f"{g.CORNER_BL}{g.DASH * (self._width - 2)}{g.CORNER_BR}"

    # ---- main api ----

    def on_prediction(
        self,
        label: str,
        confidence: float,
        timing_s: float,
        top_labels: list[tuple[str, float]] | None = None,
    ) -> None:
        """Handle one prediction result."""
        self._refresh_width()
        self._total_count += 1
        self._stats[label] += 1
        self._inference_times.append(timing_s)
        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)

        change_event: str | None = None
        if self._prev_label is not None and label != self._prev_label:
            held_s = time.monotonic() - self._change_t0
            g = self._glyphs
            top_str = f"  |  {self._top_n(top_labels)}" if top_labels else ""
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

        panel = "\n".join([
            self._dash_top(label, confidence, fps),
            self._dash_mid(confidence, top_labels),
            self._stats_line(),
            self._build_bot(),
        ])

        if self._first_output:
            self._first_output = False
            g = self._glyphs
            if self._context:
                self._write(f"\n{self._context}\n{g.DASH * self._width}\n")
            self._write(f"{panel}\n")
            self._flush_buf()
            return

        if self._tty:
            self._write(f"\033[4A\033[J{panel}\n")
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
        panel = "\n".join([top, mid, self._stats_line(), self._build_bot()])  # noqa: FLY002

        if self._first_output:
            self._first_output = False
        if self._tty:
            self._write(f"\033[4A\033[J{panel}\n")
        else:
            self._write(f"\n{panel}")
            self._flush_buf()

    def close(self) -> None:
        self._flush_buf()
        if self._tty:
            sys.stderr.write("\n\n\033[J")
            sys.stderr.flush()


class StdoutOutputFormatter:
    """Tab-separated output for piping. Verbosity: 0=change;1=+timing;2=every."""

    def __init__(self, verbose: int = 0) -> None:
        self._verbose = verbose
        self._prev_label: str | None = None
        self._total_count = 0

    def set_status(self, status: str | None) -> None:
        """No-op — stdout mode has no dashboard to display status on."""

    def on_prediction(
        self, label: str, confidence: float, timing_s: float,
        top_labels: list[tuple[str, float]] | None = None,  # noqa: ARG002  # pylint: disable=unused-argument
    ) -> None:
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
        if self._verbose >= 1:
            timing_ms = round(timing_s * 1000)
            with contextlib.suppress(OSError):
                print(f"-1\t0.000\t{timing_ms}ms", file=sys.stdout)  # noqa: T201

    def close(self) -> None:
        pass
