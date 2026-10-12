# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0212  # tests inspect private output methods

import os
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from trik_mind.output import StdoutOutputFormatter, UserOutputFormatter


@contextmanager
def _tty(fmt: UserOutputFormatter) -> Generator[None, None, None]:
    with patch.object(fmt, "_tty", True):  # noqa: FBT003
        yield


class TestUserBasic:
    """Core UserOutputFormatter tests: prediction, events, errors."""

    def test_first_prediction_shows_label(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.92, 0.05)
        stderr = capsys.readouterr().err
        assert "cat" in stderr
        assert "92" in stderr
        assert "→" not in stderr  # no change event arrow

    def test_same_label_no_change_event(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.92, 0.05)
        capsys.readouterr()
        with _tty(fmt):
            fmt.on_prediction("cat", 0.88, 0.06)
        stderr = capsys.readouterr().err
        assert "cat" in stderr
        assert "→" not in stderr  # no change arrow when same label

    def test_change_prints_event(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        with _tty(fmt):
            fmt.on_prediction("cat", 0.92, 0.05)
        capsys.readouterr()
        with _tty(fmt):
            fmt.on_prediction("dog", 0.74, 0.06)
        stderr = capsys.readouterr().err
        assert "cat" in stderr
        assert "dog" in stderr
        assert "74" in stderr

    def test_on_error_shows_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_error(0.05)
        stderr = capsys.readouterr().err
        assert "---" in stderr

    def test_on_error_in_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        r"""Test on_error in TTY mode (uses home+clear redraw)."""
        fmt = UserOutputFormatter(color_enabled=False)
        fmt._first_output = False  # simulate already-active session
        fmt._tty = True
        fmt.on_error(0.05)
        stderr = capsys.readouterr().err
        assert "\033[H\033[J" in stderr

    def test_close_releases(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        with _tty(fmt):
            fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        with _tty(fmt):
            fmt.close()
        # Close outputs newlines in TTY mode
        assert capsys.readouterr().err != ""

    def test_color_enabled_wraps_label(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=True)
        fmt._tty = True
        fmt._color = True
        with _tty(fmt):
            fmt.on_prediction("cat", 0.92, 0.05)
        stderr = capsys.readouterr().err
        assert "\033[" in stderr

    def test_color_disabled_no_ansi(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.92, 0.05)
        stderr = capsys.readouterr().err
        assert "\033[" not in stderr

    def test_total_count_increments(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.90, 0.05)
        fmt.on_prediction("cat", 0.90, 0.05)
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "#3" in stderr


class TestUserAdvanced:
    """Advanced UserOutputFormatter tests: fps, context, status badge."""

    def test_tier_green(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        code = fmt._tier(0.85)
        assert code == "\033[92m"

    def test_tier_yellow(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        code = fmt._tier(0.65)
        assert code == "\033[93m"

    def test_tier_red(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        code = fmt._tier(0.35)
        assert code == "\033[91m"

    def test_fps_in_panel(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        for _ in range(10):
            fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "fps:" in stderr

    def test_context_header_printed_once(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.set_context("Test context")
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "Test context" in stderr

    def test_context_not_repeated(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Context appears in Current box header, not as a separate line."""
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.set_context("my_model.onnx")
        fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "my_model.onnx" in stderr  # in the box header

    def test_set_status_shows_badge(self, capsys: pytest.CaptureFixture[str]) -> None:
        """set_status() shows a badge on the dashboard top line."""
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.set_status("connecting")
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "connecting" in stderr

    def test_set_status_none_hides_badge(self, capsys: pytest.CaptureFixture[str]) -> None:
        """set_status(None) removes the badge."""
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.set_status("reconnecting")
        fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        fmt.set_status(None)
        fmt.on_prediction("cat", 0.90, 0.05)
        assert "reconnecting" not in capsys.readouterr().err

    def test_panel_has_borders(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The btop-style panel should have corner characters."""
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        g = fmt._glyphs
        assert g.CORNER_TL in stderr
        assert g.CORNER_BL in stderr

    def test_change_prints_top_labels(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Change shows the new label with its percentage on the label line."""
        fmt = UserOutputFormatter(color_enabled=False)
        labels = [("cat", 0.92), ("dog", 0.74), ("bird", 0.51)]
        with _tty(fmt):
            fmt.on_prediction("cat", 0.92, 0.05, top_labels=labels)
        capsys.readouterr()
        with _tty(fmt):
            fmt.on_prediction("dog", 0.74, 0.06, top_labels=labels)
        stderr = capsys.readouterr().err
        assert "dog  74.0%" in stderr  # label line: current label + pct

    def test_mid_line_with_labels(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Middle panel line shows top-2 labels when available."""
        fmt = UserOutputFormatter(color_enabled=False)
        labels = [("cat", 0.92), ("dog", 0.74), ("bird", 0.51)]
        fmt.on_prediction("cat", 0.92, 0.05, top_labels=labels)
        stderr = capsys.readouterr().err
        assert "dog(74%)" in stderr

    def test_change_flash_in_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        """★ flash appears on change in TTY mode with colors."""
        fmt = UserOutputFormatter(color_enabled=True)
        fmt._tty = True
        fmt._color = True
        labels = [("cat", 0.92), ("dog", 0.74)]
        with _tty(fmt):
            fmt.on_prediction("cat", 0.92, 0.05, top_labels=labels)
        capsys.readouterr()
        with _tty(fmt):
            fmt.on_prediction("dog", 0.74, 0.06, top_labels=labels)
        stderr = capsys.readouterr().err
        assert "★" in stderr

    def test_tty_redraw_multiple(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Multiple predictions in TTY: each redraws in-place."""
        fmt = UserOutputFormatter(color_enabled=False)
        with _tty(fmt):
            fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        with _tty(fmt):
            fmt.on_prediction("cat", 0.88, 0.06)
        stderr = capsys.readouterr().err
        assert "\033[H\033[J" in stderr  # home+clear escape

    def test_width_caps_at_120(self) -> None:
        """When terminal reports huge buffer width, formatter caps no higher than 120."""
        fmt = UserOutputFormatter(color_enabled=False)
        with (
            patch.object(fmt, "_tty", True),  # noqa: FBT003
            patch("shutil.get_terminal_size", return_value=os.terminal_size((300, 24))),
        ):
            fmt._refresh_width()
        assert fmt._raw_width == 298  # 300 - 2 (stderr margin)
        assert fmt._width == 120

    def test_diagnostic_shows_capped_width(self) -> None:
        """Diagnostic string shows raw to capped width mapping."""
        fmt = UserOutputFormatter(color_enabled=False)
        with (
            patch.object(fmt, "_tty", True),  # noqa: FBT003
            patch("shutil.get_terminal_size", return_value=os.terminal_size((300, 24))),
        ):
            fmt._refresh_width()
        diag = fmt._diagnostic()
        assert "W298" in diag
        assert ">120" in diag

    def test_diagnostic_goes_to_title(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Diagnostic moves to OSC window title, not panel."""
        fmt = UserOutputFormatter(color_enabled=False)
        capsys.readouterr()
        with (
            patch.object(fmt, "_tty", True),  # noqa: FBT003
            patch("shutil.get_terminal_size", return_value=os.terminal_size((150, 24))),
        ):
            fmt._refresh_width()
        stderr = capsys.readouterr().err
        # Must appear as OSC title escape — format: TRIK Mind  ...  W148
        assert "\033]0;TRIK Mind " in stderr
        assert "W148" in stderr

    def test_update_title_cache_hit(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Second title write with same diagnostic is suppressed."""
        fmt = UserOutputFormatter(color_enabled=False)
        capsys.readouterr()  # discard init write
        fmt._update_title()  # second call — diagnostic unchanged (cache hit)
        stderr = capsys.readouterr().err
        assert stderr == ""  # no new title write

    def test_title_includes_source(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Window title combines source + diagnostic when source is set."""
        fmt = UserOutputFormatter(color_enabled=False)
        capsys.readouterr()  # discard init write
        fmt.set_context("model.onnx  |  USB@640x480  |  Ctrl+C to quit")
        fmt._update_title()
        stderr = capsys.readouterr().err
        assert "model.onnx" in stderr
        assert "Ctrl+C to quit" not in stderr  # hint stripped from source
        assert "W" in stderr  # diagnostic prefix still present

    def test_box_top_without_props(self) -> None:
        """Box top with no props: title + fill, no pipe section."""
        fmt = UserOutputFormatter(color_enabled=False)
        top = fmt._box_top("Hi", 10)
        assert top.startswith("╭")
        assert top.endswith("╮")
        assert "Hi" in top
        assert "│" not in top

    def test_stats_wrap_uses_multiple_lines(self) -> None:
        """Long uniform labels wrap into more than one Stats line."""
        fmt = UserOutputFormatter(color_enabled=False)
        labels = [
            "Antidisestablishmentarian",
            "Bourgeoisification",
            "Cryptographically",
            "Deoxyribonucleotide",
            "Electroencephalogram",
            "Floccinaucinihilipilification",
        ]
        for i, lbl in enumerate(labels, start=1):
            fmt._stats[lbl] += i
        fmt._width = 40  # narrow enough to force wrapping
        lines = fmt._build_stats_lines()
        assert len(lines) > 1
        assert "Antidisest" in " ".join(lines)  # 8-char truncated label


class TestStdoutOutputFormatter:
    """Tests for tab-separated pipe-friendly output."""

    def test_default_prints_on_change(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=0)
        fmt.on_prediction("cat", 0.92, 0.05)
        fmt.on_prediction("cat", 0.88, 0.05)
        fmt.on_prediction("dog", 0.74, 0.06)
        stdout = capsys.readouterr().out.splitlines()
        assert len(stdout) == 2  # first + change

    def test_default_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=0)
        fmt.on_prediction("cat", 0.92, 0.05)
        assert capsys.readouterr().out.strip() == "cat\t0.920"

    def test_verbose1_adds_timing(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=1)
        fmt.on_prediction("cat", 0.92, 0.048)
        stdout = capsys.readouterr().out.strip()
        assert "48ms" in stdout

    def test_verbose2_every_detection(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=2)
        fmt.on_prediction("cat", 0.92, 0.05)
        fmt.on_prediction("cat", 0.88, 0.05)
        assert len(capsys.readouterr().out.splitlines()) == 2

    def test_first_always_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=0)
        fmt.on_prediction("cat", 0.92, 0.05)
        assert capsys.readouterr().out.strip() != ""

    def test_on_error_suppressed_at_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=0)
        fmt.on_error(0.05)
        assert capsys.readouterr().out.strip() == ""

    def test_on_error_at_verbose1(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=1)
        fmt.on_error(0.05)
        assert capsys.readouterr().out.strip().startswith("-1\t0.000\t50ms")

    def test_total_count_tracking(self) -> None:
        fmt = StdoutOutputFormatter()
        fmt.on_prediction("cat", 0.90, 0.05)
        fmt.on_prediction("cat", 0.88, 0.05)
        assert fmt._total_count == 2

    def test_close_noop(self) -> None:
        fmt = StdoutOutputFormatter()
        fmt.close()
