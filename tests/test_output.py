# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0212  # tests inspect private output methods

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from lobe_server.output import StdoutOutputFormatter, UserOutputFormatter


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
        assert "camera error" in stderr

    def test_on_error_in_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        r"""Test on_error in TTY mode (uses cursor-up redraw)."""
        fmt = UserOutputFormatter(color_enabled=False)
        fmt._tty = True
        fmt.on_error(0.05)
        stderr = capsys.readouterr().err
        assert "\033[4A" in stderr

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
    """Advanced UserOutputFormatter tests: bars, fps, non-TTY, context."""

    def test_bar_high_confidence(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        result = fmt._bar(0.9, width=10)
        assert result.count("█") + result.count("#") == 9

    def test_bar_low_confidence(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        result = fmt._bar(0.3, width=10)
        assert result.count("█") + result.count("#") == 3

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
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.set_context("Header")
        fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        fmt.on_prediction("cat", 0.90, 0.05)
        assert "Header" not in capsys.readouterr().err

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
        """Change event shows top-N labels."""
        fmt = UserOutputFormatter(color_enabled=False)
        labels = [("cat", 0.92), ("dog", 0.74), ("bird", 0.51)]
        with _tty(fmt):
            fmt.on_prediction("cat", 0.92, 0.05, top_labels=labels)
        capsys.readouterr()
        with _tty(fmt):
            fmt.on_prediction("dog", 0.74, 0.06, top_labels=labels)
        stderr = capsys.readouterr().err
        assert "cat(92%)" in stderr
        assert "dog(74%)" in stderr

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
        """Multiple predictions in TTY mode use cursor-up redraw."""
        fmt = UserOutputFormatter(color_enabled=False)
        with _tty(fmt):
            fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        with _tty(fmt):
            fmt.on_prediction("cat", 0.88, 0.06)
        stderr = capsys.readouterr().err
        assert "\033[4A" in stderr  # cursor-up escape


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
