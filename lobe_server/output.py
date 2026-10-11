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
        """Push diagnostic to window/tab title (OSC 0). Only writes on actual change."""
        title = self._diagnostic()
        if title == self._last_title:
            return
        self._last_title = title
        # OSC 0 escape — sets window/tab title on all modern terminals (Linux,
        # macOS, Windows Terminal, iTerm2, etc.). On old cmd.exe this silently
        # does nothing; no wider effect.
        sys.stderr.write(f"\033]0;TRIK Lobe [{title}]\007")
        sys.stderr.flush()

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
        return text

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

    # ── btop‑style meter (htop inspired) ─────────────────────────

    def _meter(self, confidence: float, text: str, bar_max: int, total_width: int) -> str:
        """htop-style meter: [|||  text] — bar fills up to bar_max within total_width."""
        filled = round(confidence * bar_max)
        bar = self._glyphs.BLOCK_FULL * filled
        rest_w = max(0, total_width - filled)
        txt = text[:rest_w]
        rest = self._glyphs.BLOCK_EMPTY * max(0, rest_w - len(txt))
        code = self._tier(confidence)
        return f"[{self._c(code, bar)}{txt}{rest}]"

    def _box_line(self, content: str) -> str:
        """│  content  │ — pads to _width by visible length (ANSI‑safe)."""
        g = self._glyphs
        vis = _visible_len(content)
        pad = max(0, self._width - 2 - vis)
        return f"{g.PIPE}{content}{' ' * pad}{g.PIPE}"

    def _build_current(self, label: str, confidence: float, fps: float,
                       top_labels: list[tuple[str, float]] | None) -> list[str]:
        """Current detection box — stacked bar with all labels, colored legend."""
        g = self._glyphs
        tier = self._tier(confidence)
        is_fresh = self._last_change_time and time.monotonic() - self._last_change_time < 1.0
        lbl_display = (
            self._c(self._BOLD + tier, f"{g.STAR} {label}")
            if is_fresh and self._color
            else self._cb(tier, label)
        )
        inner = self._width - 2
        lines: list[str] = [
            f"{g.CORNER_TL}{g.DASH} Current {g.DASH * (inner - 10)}{g.CORNER_TR}",
        ]
        # ── label + metrics on one line (metrics right‑aligned) ──
        metrics = f"fps:{fps:.0f}  #{self._total_count}"
        if self._prev_label is not None:
            held = time.monotonic() - self._change_t0
            metrics += f"  \u0394 {held:.1f}s"
        label_content = f" {lbl_display} "
        metrics_str = f" {metrics} "
        pad = max(1, self._width - 2 - _visible_len(label_content) - _visible_len(metrics_str))
        lines.append(self._box_line(f"{label_content}{' ' * pad}{metrics_str}"))

        # ── legend: colored labels with percentages ──
        all_labels = top_labels or [(label, confidence)]
        label_map = {l: c for l, c in all_labels}
        label_map[label] = max(label_map.get(label, 0), confidence)
        sorted_lbls = sorted(label_map.items(), key=lambda x: -x[1])
        bar_colors = [self._GREEN, self._BLUE, self._PURPLE, self._DIM]
        legend = "  ".join(
            f"{self._c(bar_colors[min(i, len(bar_colors)-1)], f'{lbl}({c*100:.0f}%)')}"
            for i, (lbl, c) in enumerate(sorted_lbls[:4])
        )
        lines.append(self._box_line(f"  {legend}  "))

        # ── separator ──
        lines.append(f"{g.TJUNCTION_L}{g.DASH} History {g.DASH * (inner - 10)}{g.TJUNCTION_R}")
        return lines

    def _build_history(self, max_rows: int) -> list[str]:
        """Process‑list style history with fixed column widths — bar first."""
        g = self._glyphs
        lines: list[str] = []
        inner = self._width - 2

        # Fixed column widths (in characters)
        COL_PCT = 5    # " 89%"
        COL_NUM = 4    # " 35"
        COL_LBL = 10   # "  Cherry  " (left)
        COL_EVT = 3    # " →" or "   "
        SP = 1         # space between columns
        fixed = COL_PCT + COL_NUM + COL_LBL + COL_EVT + SP * 4
        bar_w = max(10, min(inner - fixed, 50))  # cap bar at 50 to avoid overbloat

        # Column header aligned to data columns
        header = (
            f"{'Bar':<{bar_w}}"
            f"{'%':>{COL_PCT}} "
            f"{'#':>{COL_NUM}} "
            f"{'Label':<{COL_LBL}} "
            f"{'Evt':>{COL_EVT}}"
        )
        lines.append(self._box_line(header))

        for entry in reversed(list(self._history)[-max_rows:]):
            idx, lbl, conf, _fps, _timing, is_change, prev_lbl = entry
            tier = self._tier(conf)
            # Bar (colored)
            filled = round(conf * bar_w)
            bar_color = self._c(tier, g.BLOCK_FULL * filled + g.BLOCK_EMPTY * max(0, bar_w - filled))
            # Percentage (same color as bar)
            pct = self._c(tier, f"{conf*100:.0f}%".rjust(COL_PCT))
            # Number (same color as bar)
            num = self._c(tier, f"{idx}".rjust(COL_NUM))
            # Label
            label = f"  {lbl:<8}"[:COL_LBL]
            # Event marker
            evt = f" {g.ARROW_R}" if is_change else "   "
            row = f"{bar_color} {pct} {num} {label} {evt}"
            lines.append(self._box_line(row))

        # Pad with dim placeholder rows so stats sits at the bottom
        for _ in range(max_rows - min(max_rows, len(self._history))):
            dim = self._DIM
            blank_bar = self._c(dim, g.BLOCK_EMPTY * bar_w)
            blank_pct = self._c(dim, "---".rjust(COL_PCT))
            blank_num = self._c(dim, "---".rjust(COL_NUM))
            blank_lbl = "  ---     "[:COL_LBL]
            lines.append(self._box_line(f"{blank_bar} {blank_pct} {blank_num} {blank_lbl}   "))
        return lines

    def _build_stats_line(self) -> str:
        """htop Mem-style stats bar: [Label ████████ count]."""
        g = self._glyphs
        sorted_s = sorted(self._stats.items(), key=lambda x: x[0])
        if not sorted_s:
            return self._box_line(_("  (no data)"))

        max_c = sorted_s[0][1]
        inner = self._width - 2
        parts: list[str] = []
        left = inner
        for lbl, count in sorted_s[:4]:
            slot = f" {lbl} "
            bar_w = max(2, round((count / max_c) * (min(left - len(slot) - 4, 16))))
            filled = round((count / max_c) * bar_w)
            code = self._GREEN if (count / max_c) >= 0.5 else (self._YELLOW if (count / max_c) >= 0.2 else self._RED)
            bar = self._c(code, g.BLOCK_FULL * filled + g.BLOCK_EMPTY * max(0, bar_w - filled))
            entry = f"{slot}{bar} {count}"
            if len(entry) > left:
                break
            parts.append(entry)
            left -= len(entry) + 2
        return self._box_line("  ".join(parts))

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
        g = self._glyphs
        panel_lines: list[str] = []

        # Top zone: current detection (always same position)
        panel_lines += self._build_current(label, confidence, fps, top_labels)

        # History zone: recent predictions (fill available space, leave 1 line for prompt)
        current_h = 4      # top + label/metrics + legend + separator
        col_header = 1
        stats_h = 3         # separator + line + bottom
        avail = max(2, self._lines - current_h - col_header - stats_h - 1)
        panel_lines += self._build_history(avail)

        # Stats zone: cummulative counts (htop Mem-style bar)
        g2 = self._glyphs
        inner_w = self._width - 2
        sep = f"{g2.TJUNCTION_L}{g2.DASH} Stats {g2.DASH * (inner_w - 8)}{g2.TJUNCTION_R}"
        panel_lines.append(sep)
        panel_lines.append(self._build_stats_line())
        panel_lines.append(f"{g2.CORNER_BL}{g2.DASH * (self._width - 2)}{g2.CORNER_BR}")

        panel = "\n".join(panel_lines)

        if self._first_output:
            self._first_output = False
            ctx = f"\n{self._context}\n" if self._context else "\n"
            self._write(f"{ctx}{panel}\n")
            self._flush_buf()
            return

        if self._tty:
            # Full-screen redraw — pan lives at the top of the terminal, no cursor‑up chaos
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

        g = self._glyphs
        panel_lines: list[str] = []
        panel_lines += self._build_current("---", 0.0, fps, None)
        panel_lines += self._build_history(max(2, self._lines - 13))
        panel = "\n".join(panel_lines)

        if self._first_output:
            self._first_output = False
        if self._tty:
            self._write(f"\033[H\033[J{panel}\n")
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
