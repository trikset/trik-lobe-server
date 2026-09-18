# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0212  # tests inspect private output methods

import time
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from lobe_server.output import StdoutOutputFormatter, UserOutputFormatter


@contextmanager
def _tty(fmt: UserOutputFormatter) -> Generator[None, None, None]:
    """Temporarily mark a formatter's stderr as a TTY for testing."""
    with patch.object(fmt, "_tty", True):  # noqa: FBT003
        yield


class TestUserBasic:
    """Core UserOutputFormatter tests: prediction, events, errors."""

    def test_first_prediction_no_change_event(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.92, 0.05)
        stderr = capsys.readouterr().err
        assert "cat" in stderr
        assert "92.0%" in stderr
        assert self._dash() not in stderr  # no change event

    @staticmethod
    def _dash() -> str:
        return UserOutputFormatter(color_enabled=False)._glyphs.DASH

    def test_same_label_no_change_event(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.92, 0.05)
        capsys.readouterr()
        with _tty(fmt):
            fmt.on_prediction("cat", 0.88, 0.06)
        stderr = capsys.readouterr().err
        assert "cat" in stderr
        assert self._dash() * 2 not in stderr  # still no change event

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
        assert "74.0%" in stderr

    def test_on_error_shows_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_error(0.05)
        stderr = capsys.readouterr().err
        assert "camera error" in stderr

    def test_on_error_in_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        r"""Test on_error in TTY mode (uses \r prefix)."""
        fmt = UserOutputFormatter(color_enabled=False)
        fmt._tty = True
        fmt.on_error(0.05)
        stderr = capsys.readouterr().err
        assert "\r" in stderr
        assert "camera error" in stderr

    def test_close_prints_newline_in_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        with _tty(fmt):
            fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        with _tty(fmt):
            fmt.close()
        stderr = capsys.readouterr().err
        assert stderr == "\n"

    def test_close_noop_in_nontty(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        fmt.close()
        stderr = capsys.readouterr().err
        assert stderr == ""

    def test_color_enabled_wraps_label_in_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=True)
        fmt._tty = True  # force TTY mode for testing
        fmt._color = True  # force ANSI colors
        with _tty(fmt):
            fmt.on_prediction("cat", 0.92, 0.05)
        stderr = capsys.readouterr().err
        assert "\033[" in stderr  # ANSI codes present

    def test_color_disabled_no_ansi(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        with _tty(fmt):
            fmt.on_prediction("cat", 0.92, 0.05)
        stderr = capsys.readouterr().err
        assert "\033[" not in stderr  # no ANSI codes

    def test_total_count_increments(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.90, 0.05)
        fmt.on_prediction("cat", 0.90, 0.05)
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "#3" in stderr

    def test_confidence_tier_green(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        code, _block = fmt._confidence_tier(0.85)
        assert code == "\033[92m"

    def test_confidence_tier_yellow(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        code, _block = fmt._confidence_tier(0.65)
        assert code == "\033[93m"

    def test_confidence_tier_red(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        code, _block = fmt._confidence_tier(0.35)
        assert code == "\033[91m"


class TestUserAdvanced:
    """Advanced UserOutputFormatter tests: bars, fps, non-TTY, context."""

    def test_bar_high_confidence(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        result = fmt._confidence_bar(0.9, width=10)
        count = result.count("█") + result.count("#")
        assert count == 18  # 9 filled x 2 chars

    def test_bar_low_confidence(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        result = fmt._confidence_bar(0.3, width=10)
        count = result.count("█") + result.count("#")
        assert count == 6  # 3 filled x 2 chars

    def test_fps_sliding_window(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        for _ in range(10):
            fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "FPS" in stderr

    def test_non_tty_newline_each_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        r"""In non-TTY mode, each prediction gets its own \n-terminated line."""
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.90, 0.05)
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert stderr.count("\n") == 2  # two lines, each with \n

    def test_unused_code_is_detected(self) -> None:
        pass

    def test_uptime_shows_seconds(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        result = fmt._uptime_str()
        assert "s" in result
        assert "m" in result

    def test_uptime_shows_hours(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt._start_time = time.monotonic() - 7260  # 2 hours 1 minute
        result = fmt._uptime_str()
        assert "h" in result
        assert "2h" in result

    def test_context_header_printed_on_first_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.set_context("Test context")
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "Test context" in stderr

    def test_context_printed_once(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.set_context("Header")
        fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "Header" not in stderr


class TestStdoutOutputFormatter:
    def test_default_verbose_prints_on_change(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=0)
        fmt.on_prediction("cat", 0.92, 0.05)
        fmt.on_prediction("cat", 0.88, 0.05)  # same label, suppressed
        fmt.on_prediction("dog", 0.74, 0.06)  # change, printed
        stdout = capsys.readouterr().out.splitlines()
        assert len(stdout) == 2  # first + change

    def test_default_verbose_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=0)
        fmt.on_prediction("cat", 0.92, 0.05)
        stdout = capsys.readouterr().out.strip()
        assert stdout == "cat\t0.920"  # tab-separated, no timing

    def test_verbose1_adds_timing(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=1)
        fmt.on_prediction("cat", 0.92, 0.048)
        stdout = capsys.readouterr().out.strip()
        assert "48ms" in stdout
        assert stdout.startswith("cat\t0.920\t")

    def test_verbose2_prints_every_detection(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=2)
        fmt.on_prediction("cat", 0.92, 0.05)
        fmt.on_prediction("cat", 0.88, 0.05)
        stdout = capsys.readouterr().out.splitlines()
        assert len(stdout) == 2  # both printed

    def test_first_prediction_always_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=0)
        fmt.on_prediction("cat", 0.92, 0.05)
        stdout = capsys.readouterr().out.strip()
        assert stdout != ""

    def test_on_error_suppressed_at_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=0)
        fmt.on_error(0.05)
        stdout = capsys.readouterr().out.strip()
        assert stdout == ""

    def test_on_error_printed_at_verbose1(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = StdoutOutputFormatter(verbose=1)
        fmt.on_error(0.05)
        stdout = capsys.readouterr().out.strip()
        assert stdout.startswith("-1\t0.000\t50ms")

    def test_total_count_tracking(self) -> None:
        fmt = StdoutOutputFormatter()
        fmt.on_prediction("cat", 0.90, 0.05)
        fmt.on_prediction("cat", 0.88, 0.05)
        assert fmt._total_count == 2

    def test_close_noop(self) -> None:
        fmt = StdoutOutputFormatter()
        fmt.close()  # should not raise
