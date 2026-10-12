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
_STDOUT_EVERY_DETECTION = 2
_BOX_WIDTH = 72
_MAX_WIDTH = 120
_HIST_COL_PCT = 5
_HIST_COL_NUM = 4
_HIST_COL_LBL = 10
_HIST_COL_EVT = 3
_HIST_COL_SP = 1
_HIST_BAR_MIN = 10
_HIST_BAR_MAX = 50
_BAR_COLORS = ("\x1b[92m", "\x1b[94m", "\x1b[95m", "\x1b[2m")

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
    TJUNCTION_L = "├"  # ├
    TJUNCTION_R = "┤"  # ┤


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
    TJUNCTION_L = "|"  # fallback to plain pipe
    TJUNCTION_R = "|"


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
    Full-screen btop-style live dashboard.

    Layout (top to bottom):
      ┌─ Current ──┐    — label + fps/Δ, coloured legend
      ├─ History ──┤    — process-list, newest at top
      ├─ Stats ────┤    — cumulative per-label counts
      ╰──────────────┐

    History rows are capped to fit the terminal without scrolling.
    """

    _GREEN = "\033[92m"
    _YELLOW = "\033[93m"
    _RED = "\033[91m"
    _BOLD = "\033[1m"
    _RESET = "\033[0m"
    _DIM = "\033[2m"
    _BLUE = "\033[94m"
    _PURPLE = "\033[95m"
    _GREY = "\033[90m"

    PREDICTION_INTERVAL = 0.2

    def __init__(self, *, color_enabled: bool = True) -> None:
        self._color = color_enabled and sys.stderr.isatty()
        self._tty = sys.stderr.isatty()
        self._glyphs = _Unicode if _HAS_UNICODE else _ASCII
        self._width = _BOX_WIDTH
        self._raw_width = _BOX_WIDTH
        self._lines = 24  # default terminal height
        self._vt_ok = True
        if _WIN:  # pragma: no cover
            self._vt_ok = _enable_vt()
            if self._color and not self._vt_ok:
                self._color = False
        if self._tty:
            with contextlib.suppress(ValueError, OSError):  # pragma: no cover
                ts = shutil.get_terminal_size()
                self._raw_width = max(ts.columns - 2, 40)
                self._width = min(self._raw_width, _MAX_WIDTH)
                self._lines = max(ts.lines, 10)

        self._prev_label: str | None = None
        self._total_count = 0
        self._change_t0 = time.monotonic()
        self._dets_since_change = 0
        self._inference_times: deque[float] = deque(maxlen=50)
        self._first_output = True
        self._context: str | None = None
        self._source: str = ""
        self._last_change_time = 0.0
        self._status: str | None = None
        self._stats: Counter[str] = Counter()
        self._buf: list[str] = []
        self._last_width_check = 0.0
        self._last_title: str | None = None
        # Ring buffer of recent predictions: deque of (index, label, confidence, fps, timing_s,
        # is_change, prev_label) — oldest first, newest last.
        self._history: deque[tuple[int, str, float, float, float, bool, str | None]] = deque(maxlen=50)
        self._update_title()

    def _refresh_width(self) -> None:
        """Re-check terminal width (may change on resize). Called once per frame."""
        if not self._tty:
            return
        now = time.monotonic()
        if now - self._last_width_check < 1.0:
            return
        self._last_width_check = now
        with contextlib.suppress(ValueError, OSError):
            ts = shutil.get_terminal_size()
            self._lines = max(ts.lines, 10)
            cols = ts.columns - 2
            if cols >= 40:  # noqa: PLR2004  # minimum terminal width for the box to fit
                self._raw_width = cols
                self._width = min(cols, _MAX_WIDTH)
                self._update_title()

    def _diagnostic(self) -> str:
        """Compact terminal diagnostic: Wraw→capped+encoding+VT+COL."""
        enc = (getattr(sys.stderr, "encoding", "") or "?").upper().replace("-", "")
        return "+".join([f"W{self._raw_width}>{self._width}", enc, f"VT{int(self._vt_ok)}", f"COL{int(self._color)}"])

    def _update_title(self) -> None:
        """Push model + source + diagnostic to window/tab title (OSC 0)."""
        title = self._diagnostic()
        if self._source:
            title = f"{self._source}  |  {title}"
        if title == self._last_title:
            return
        self._last_title = title
        sys.stderr.write(f"\033]0;TRIK Lobe  {title}\007")
        sys.stderr.flush()

    def set_context(self, context: str) -> None:
        self._context = context
        # Model/source for header — everything before Ctrl+C hint, pipes compacted
        src = re.sub(r"  \|  Ctrl\+C.*$", "", context).strip() or context
        src = re.sub(r"\s*\|\s*", "\u2502", src)  # normalize pipes to │
        self._source = src

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
        return text

    def _tier(self, confidence: float) -> str:
        if confidence >= _CONF_TIER_HIGH:
            return self._GREEN
        if confidence >= _CONF_TIER_MID:
            return self._YELLOW
        return self._RED



    def _box_line(self, content: str) -> str:
        """│  content  │ — padded to _width by visible length (ANSI-safe)."""
        g = self._glyphs
        vis = _visible_len(content)
        pad = max(0, self._width - 2 - vis)
        return f"{g.PIPE}{content}{' ' * pad}{g.PIPE}"

    def _section_header(self, title: str, width: int) -> str:
        """├─ title ──┤ separator."""
        g = self._glyphs
        return f"{g.TJUNCTION_L}{g.DASH} {title} {g.DASH * (width - 5 - len(title))}{g.TJUNCTION_R}"

    def _box_top(self, title: str, width: int, props: str = "") -> str:
        """╭─Title──info──╮ compact box top — no spaces, dashes fill to right."""
        g = self._glyphs
        if not props:
            return f"{g.CORNER_TL}{g.DASH}{title}{g.DASH * (width - 3 - len(title))}{g.CORNER_TR}"
        # Visual: ╭(1) + ─Title──(1+len+2) + props + ─╮(2)
        prefix_vis = 1 + len(title) + 2
        suffix_vis = 2
        avail = width - 1 - prefix_vis - _visible_len(props) - suffix_vis
        return f"{g.CORNER_TL}{g.DASH}{title}{g.DASH}{g.DASH}{props}{g.DASH * max(0, avail)}{g.DASH}{g.CORNER_TR}"

    def _box_bot(self, width: int) -> str:
        """╰──────────╯ box bottom."""
        g = self._glyphs
        return f"{g.CORNER_BL}{g.DASH * (width - 2)}{g.CORNER_BR}"

    def _available_history_rows(self) -> int:
        """Return how many history rows fit the terminal."""
        return max(2, self._lines - 4 - 1 - 3 - 1)

    def _header_props(self) -> str:
        """Static info for the Current box header — compact, pipe-separated."""
        parts = [self._diagnostic()]
        if self._source:
            parts.insert(0, self._source)
        return "│".join(parts)

    def _redraw(self, panel: str) -> None:
        """Write panel with full-screen clear (TTY) or append (pipe)."""
        nl = "\n"
        if self._first_output:
            self._first_output = False
            ctx = f"{nl}{self._context}{nl}" if self._context else nl
            self._write(f"{ctx}{panel}{nl}")
            self._flush_buf()
            return
        if self._tty:
            self._write(f"\033[H\033[J{panel}{nl}")
        else:
            self._write(f"{nl}{panel}")
            self._flush_buf()

    def _build_current(self, label: str, confidence: float, fps: float,
                       top_labels: list[tuple[str, float]] | None) -> list[str]:
        """Build the current detection box: label + metrics + coloured legend."""
        g = self._glyphs
        tier = self._tier(confidence)
        is_fresh = self._last_change_time and time.monotonic() - self._last_change_time < 1.0
        lbl = (
            self._c(self._BOLD + tier, f"{g.STAR} {label}")
            if is_fresh and self._color
            else self._cb(tier, label)
        )
        lines = [self._box_top("Current", self._width, self._header_props())]
        # ── label + confidence + metrics on one line ──
        pct = self._c(tier, f"{confidence * 100:.1f}%")
        metrics = f"fps:{fps:.0f}  #{self._total_count}"
        if self._prev_label is not None and not self._status:
            held = time.monotonic() - self._change_t0
            metrics += f"  \u0394 {held:.1f}s"
        if self._status:
            metrics = f"{self._c(self._BOLD + self._YELLOW, self._status)}  {metrics}"
        lp = f" {lbl}  {pct} "
        mp = f" {metrics} "
        pad = max(1, self._width - 2 - _visible_len(lp) - _visible_len(mp))
        lines.append(self._box_line(f"{lp}{' ' * pad}{mp}"))
        # ── candidate labels (skip current, show top 3 others) ──
        all_labels = top_labels or [(label, confidence)]
        lm = dict(all_labels)
        lm[label] = max(lm.get(label, 0), confidence)
        sorted_lbls = sorted(lm.items(), key=lambda x: -x[1])
        cands = [self._c(_BAR_COLORS[min(i, 3)], f"{lb[:_HIST_COL_LBL]}({c*100:.0f}%)")
                 for i, (lb, c) in enumerate(sorted_lbls) if i > 0][:3]
        if cands:
            lines.append(self._box_line(f"  {'  '.join(cands)}  "))
        lines.append(self._section_header("History", self._width))
        return lines

    def _build_history(self, max_rows: int) -> list[str]:
        """Process-list style history with fixed column widths — bar first."""
        g = self._glyphs
        lines: list[str] = []
        fixed = _HIST_COL_PCT + _HIST_COL_NUM + _HIST_COL_LBL + _HIST_COL_EVT + _HIST_COL_SP * 4
        bar_w = max(_HIST_BAR_MIN, min(self._width - 2 - fixed, _HIST_BAR_MAX))

        # Column header aligned to data columns
        header = (
            f"{'Bar':<{bar_w}}"
            f"{'%':>{_HIST_COL_PCT}} "
            f"{'#':>{_HIST_COL_NUM}} "
            f"{'Label':<{_HIST_COL_LBL}} "
            f"{'Evt':>{_HIST_COL_EVT}}"
        )
        lines.append(self._box_line(header))

        for entry in reversed(list(self._history)[-max_rows:]):
            idx, lbl, conf, _fps, _timing, is_change, _pl = entry
            tier = self._tier(conf)
            filled = round(conf * bar_w)
            bar = self._c(tier, g.BLOCK_FULL * filled + g.BLOCK_EMPTY * max(0, bar_w - filled))
            pct = self._c(tier, f"{conf*100:.0f}%".rjust(_HIST_COL_PCT))
            num = self._c(tier, f"{idx}".rjust(_HIST_COL_NUM))
            cl = f"  {lbl:<8}"[:_HIST_COL_LBL]
            evt = f"  {g.ARROW_R}" if is_change else "   "
            lines.append(self._box_line(f"{bar} {pct} {num} {cl} {evt}"))

        for _ in range(max_rows - min(max_rows, len(self._history))):
            d = self._DIM
            blank = self._c(d, g.BLOCK_EMPTY * bar_w)
            bp = self._c(d, "---".rjust(_HIST_COL_PCT))
            bn = self._c(d, "---".rjust(_HIST_COL_NUM))
            bl = "  ---     "[:_HIST_COL_LBL]
            lines.append(self._box_line(f"{blank} {bp} {bn} {bl}   "))
        return lines

    def _build_stats_lines(self) -> list[str]:
        """Per-label counts — all labels, wrapped to multiple lines."""
        sorted_s = sorted(self._stats.items(), key=lambda x: x[0])
        if not sorted_s:
            return [self._box_line(_("  (no data)"))]

        lines: list[str] = []
        row: list[str] = []
        left = self._width - 2
        for lbl, count in sorted_s:
            short = lbl[:_HIST_COL_LBL]
            entry = f" {short} {count}"
            if len(entry) > left and row:
                lines.append(self._box_line("  ".join(row)))
                row = []
                left = self._width - 2
            row.append(entry)
            left -= len(entry) + 2
        if row:
            lines.append(self._box_line("  ".join(row)))
        return lines

    # ---- main api ----

    def on_prediction(
        self,
        label: str,
        confidence: float,
        timing_s: float,
        top_labels: list[tuple[str, float]] | None = None,
    ) -> None:
        """Handle one prediction result — btop-style multi-zone layout."""
        self._refresh_width()
        self._total_count += 1
        self._stats[label] += 1
        self._inference_times.append(timing_s)
        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)

        # Detect label change
        is_change = self._prev_label is not None and label != self._prev_label
        if is_change:
            self._change_t0 = time.monotonic()
            self._dets_since_change = 0
            self._last_change_time = time.monotonic()
        elif self._prev_label is None:
            self._change_t0 = time.monotonic()

        prev = self._prev_label
        self._dets_since_change += 1
        self._prev_label = label

        # Append to history ring buffer
        self._history.append((self._total_count, label, confidence, fps, timing_s, is_change, prev))

        # ── Build multi-zone layout ──
        panel_lines: list[str] = []

        # Top zone: current detection (always same position)
        panel_lines += self._build_current(label, confidence, fps, top_labels)

        # History zone: fill available space
        avail = max(2, self._lines - 4 - 1 - 3 - 1)
        panel_lines += self._build_history(avail)

        # Stats zone: all labels with counts
        panel_lines.append(self._section_header("Stats", self._width))
        panel_lines += self._build_stats_lines()
        panel_lines.append(self._box_bot(self._width))

        panel = "\n".join(panel_lines)

        if self._first_output:
            self._first_output = False
            ctx = f"\n{self._context}\n" if self._context else "\n"
            self._write(f"{ctx}{panel}\n")
            self._flush_buf()
            return

        if self._tty:
            # Full-screen redraw — pan lives at the top of the terminal, no cursor-up chaos
            self._write(f"\033[H\033[J{panel}\n")
        else:
            self._write(f"\n{panel}")
            self._flush_buf()

    def on_error(
        self,
        timing_s: float,
        top_labels: list[tuple[str, float]] | None = None,  # noqa: ARG002  # pylint: disable=unused-argument
    ) -> None:
        self._total_count += 1
        self._inference_times.append(timing_s)
        fps = len(self._inference_times) / (sum(self._inference_times) or 1e-9)
        self._history.append((self._total_count, "---", 0.0, fps, timing_s, False, None))

        panel_lines = list(self._build_current("---", 0.0, fps, None))
        panel_lines += self._build_history(self._available_history_rows())
        panel_lines.append(self._section_header("Stats", self._width))
        panel_lines += self._build_stats_lines()
        panel_lines.append(self._box_bot(self._width))

        self._redraw("\n".join(panel_lines))

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
