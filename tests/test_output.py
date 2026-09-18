# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0212  # tests inspect private output methods


import pytest

from lobe_server.output import StdoutOutputFormatter, UserOutputFormatter


class TestUserOutputFormatter:
    def test_first_prediction_no_change_event(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.92, 0.05)
        stderr = capsys.readouterr().err
        # First prediction: no change event, just the live line
        assert "cat" in stderr
        assert "92.0%" in stderr
        assert "──" not in stderr  # no change event

    def test_same_label_no_change_event(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.92, 0.05)
        capsys.readouterr()
        fmt.on_prediction("cat", 0.88, 0.06)
        stderr = capsys.readouterr().err
        assert "cat" in stderr
        assert "──" not in stderr  # still no change event

    def test_change_prints_event(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.92, 0.05)
        capsys.readouterr()
        fmt.on_prediction("dog", 0.74, 0.06)
        stderr = capsys.readouterr().err
        assert "cat → dog" in stderr
        assert "74.0%" in stderr

    def test_on_error_shows_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_error(0.05)
        stderr = capsys.readouterr().err
        assert "camera error" in stderr

    def test_close_prints_newline(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        fmt.close()
        stderr = capsys.readouterr().err
        assert stderr == "\n"

    def test_color_enabled_wraps_label(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=True)
        fmt.on_prediction("cat", 0.92, 0.05)
        stderr = capsys.readouterr().err
        assert "\033[" in stderr  # ANSI codes present

    def test_color_disabled_no_ansi(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
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

    def test_bar_high_confidence(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        result = fmt._confidence_bar(0.9, width=10)
        assert result.count("█") == 9
        assert result.count("░") == 1

    def test_bar_low_confidence(self) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        result = fmt._confidence_bar(0.3, width=10)
        assert result.count("█") == 3
        assert result.count("░") == 7

    def test_fps_sliding_window(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        for _ in range(10):
            fmt.on_prediction("cat", 0.90, 0.05)
        stderr = capsys.readouterr().err
        assert "FPS" in stderr

    def test_detections_since_change_after_change(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = UserOutputFormatter(color_enabled=False)
        fmt.on_prediction("cat", 0.90, 0.05)
        capsys.readouterr()
        fmt.on_prediction("dog", 0.80, 0.05)
        stderr = capsys.readouterr().err
        assert "cat" in stderr  # last change shows previous label


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
