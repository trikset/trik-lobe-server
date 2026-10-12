#!/usr/bin/env python3
# ruff: noqa: N999 — script filename with hyphen is intentional
"""
Render ANSI terminal output as a PNG screenshot.

Parses ANSI colour codes, renders block characters as filled/dotted
rectangles, and outputs a PNG that looks like a real terminal window.

Usage:
    uv run scripts/render-screenshots.py <input.ansi> <output.png> [--dark]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import NamedTuple, TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from collections.abc import Generator

# ANSI SGR colour maps (8-colour foreground/background, keyed by code digit)
_SGR_FG: dict[str, tuple[int, int, int]] = {
    "30": (0, 0, 0),
    "31": (0xCC, 0, 0),
    "32": (0, 0xCC, 0),
    "33": (0xCC, 0xCC, 0),
    "34": (0x66, 0x66, 0xCC),
    "35": (0xCC, 0, 0xCC),
    "36": (0, 0xCC, 0xCC),
    "37": (0xCC, 0xCC, 0xCC),
    "90": (0x66, 0x66, 0x66),
    "91": (0xFF, 0, 0),
    "92": (0, 0xFF, 0),
    "93": (0xFF, 0xFF, 0),
    "94": (0x33, 0x33, 0xFF),
    "95": (0xFF, 0, 0xFF),
    "96": (0, 0xFF, 0xFF),
    "97": (0xFF, 0xFF, 0xFF),
}
_SGR_BG: dict[str, tuple[int, int, int]] = {
    "41": (0xCC, 0, 0),
    "42": (0, 0xCC, 0),
    "43": (0xCC, 0xCC, 0),
    "44": (0x33, 0x33, 0xFF),
    "45": (0xCC, 0, 0xCC),
}

_ANSI_ESC = re.compile(r"\033\[([0-9;]*)m")
_FULL_BLOCK = "\u2588"  # █
_LIGHT_SHADE = "\u2591"  # ░

_THEMES = {
    "dark": {"bg": (0x1E, 0x1E, 0x2E), "fg": (0xC0, 0xC0, 0xC0)},
    "light": {"bg": (0xF5, 0xF5, 0xF5), "fg": (0x20, 0x20, 0x20)},
}

_TERM_ROWS = 41
_TERM_COLS = 81
_PAD = 16
_FONT_SIZE = 15
_FONT_PATH = "/usr/share/fonts/truetype/andale/Andale_Mono.ttf"


def _segments(text: str) -> Generator[tuple[str, tuple[int, int, int] | None, tuple[int, int, int] | None], None, None]:
    """Yield (char, fg_colour, bg_colour) for each visible character, consuming ANSI codes."""
    fg: tuple[int, int, int] | None = None
    bg: tuple[int, int, int] | None = None
    i = 0
    while i < len(text):
        m = _ANSI_ESC.match(text, i)
        if m:
            params, i = m.group(1), m.end()
            if not params or params == "0":
                fg = None
                bg = None
                continue
            for p in params.split(";"):
                if p in _SGR_FG:
                    fg = _SGR_FG[p]
                elif p in _SGR_BG:
                    bg = _SGR_BG[p]
            continue
        yield text[i], fg, bg
        i += 1


def _load_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(_FONT_PATH, _FONT_SIZE)
    except OSError:
        return ImageFont.load_default()


_Cell = NamedTuple("_Cell", [("char", str), ("fg", tuple[int, int, int] | None), ("bg", tuple[int, int, int] | None), ("x", int), ("y", int), ("x_end", int), ("y_end", int), ("font", "ImageFont.FreeTypeFont | ImageFont.ImageFont"), ("fg_default", tuple[int, int, int]), ("bg_default", tuple[int, int, int])])  # type: ignore[no-any-expr]  # pyright: ignore[reportUnknownVariableType,reportMissingTypeArgument]


def _draw_cell(draw: ImageDraw.ImageDraw, cell: _Cell) -> None:
    """Paint one terminal cell: optional bg fill, then block/dot/text glyph."""
    colour = cell.fg if cell.fg is not None else cell.fg_default
    if cell.bg is not None:
        draw.rectangle([cell.x, cell.y, cell.x_end, cell.y_end], fill=cell.bg)
        if cell.fg is None or cell.fg == cell.bg_default:
            # dark text on bright background for letter-bars in colour mode
            colour = (0, 0, 0) if cell.bg_default[0] > 0x80 else (0xFF, 0xFF, 0xFF)
    if cell.char == _FULL_BLOCK:
        draw.rectangle([cell.x, cell.y, cell.x_end, cell.y_end], fill=colour)
    elif cell.char == _LIGHT_SHADE:
        dot = tuple(v // 3 + base // 2 for v, base in zip(colour, cell.bg_default, strict=True))
        for dx in range(0, cell.x_end - cell.x + 1, 2):
            for dy in range(0, cell.y_end - cell.y + 1, 3):
                draw.point((cell.x + dx, cell.y + dy), fill=dot)
    else:
        draw.text((cell.x, cell.y), cell.char, fill=colour, font=cell.font)


def render(input_path: str, output_path: str, *, dark: bool) -> None:
    """Read *input_path* (ANSI), render last _TERM_ROWS rows as PNG."""
    theme = _THEMES["dark" if dark else "light"]
    raw = Path(input_path).read_text(encoding="utf-8")

    # Strip OSC title escapes, rebuild terminal scrollback
    text = re.sub(r"\033\]0;[^\007]*\007", "", raw)
    parts = re.split(r"\033\[\d+A", text)
    all_lines: list[str] = []
    for seg in parts:
        all_lines.extend(line for line in seg.replace("\033[J", "").replace("\r", "").split("\n"))

    lines = all_lines[-_TERM_ROWS:] if len(all_lines) > _TERM_ROWS else all_lines + [""] * (_TERM_ROWS - len(all_lines))
    max_cols = min(max((len(line) for line in lines), default=_TERM_COLS), _TERM_COLS)

    # Font and cell metrics
    font = _load_font()
    dd = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = dd.textbbox((0, 0), "M", font=font)
    cw = max(int(bbox[2] - bbox[0]), 7)
    ch = max(int(bbox[3] - bbox[1]), 14)

    # Canvas
    iw = max_cols * cw + _PAD * 2
    ih = _TERM_ROWS * ch + _PAD * 2
    img = Image.new("RGB", (iw, ih), theme["bg"])
    draw = ImageDraw.Draw(img)

    for ri, line in enumerate(lines[:_TERM_ROWS]):
        for ci, (char, fg, bg) in enumerate(_segments(line)):
            if ci >= max_cols:
                break
            _draw_cell(
                draw,
                _Cell(
                    char,
                    fg,
                    bg,
                    _PAD + ci * cw,
                    _PAD + ri * ch,
                    _PAD + ci * cw + cw - 1,
                    _PAD + ri * ch + ch - 1,
                    font,
                    theme["fg"],
                    theme["bg"],
                ),
            )

    img.save(output_path)
    print(f"Saved {output_path}  {iw}x{ih}, {len(lines)} rows, {max_cols} cols")


def main() -> None:
    ap = argparse.ArgumentParser(description="Render ANSI terminal dump as PNG screenshot")
    ap.add_argument("input", help="Input .ansi file")
    ap.add_argument("output", help="Output .png file")
    ap.add_argument("--dark", action="store_true", help="Use dark theme")
    args = ap.parse_args()
    render(args.input, args.output, dark=args.dark)


if __name__ == "__main__":
    main()
