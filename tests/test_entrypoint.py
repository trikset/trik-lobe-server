# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0212  # tests inspect private entrypoint helpers

import argparse
import builtins
import sys
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import TRIKMind
from trik_mind.output import StdoutOutputFormatter, UserOutputFormatter


@pytest.mark.parametrize(
    ("stdin_patch", "expected_calls"),
    [
        pytest.param(lambda: patch.object(sys.stdin, "isatty", return_value=True), 1, id="tty"),
        pytest.param(lambda: patch.object(sys.stdin, "isatty", return_value=False), 0, id="non-tty"),
        pytest.param(lambda: patch.object(sys, "stdin", None), 0, id="missing-stdin"),
    ],
)
def test_pause_gating(stdin_patch: Callable[[], Any], expected_calls: int) -> None:
    with stdin_patch(), patch.object(builtins, "input") as mock_input:
        TRIKMind._pause_for_user()
    assert mock_input.call_count == expected_calls


class TestParseArgs:
    def test_defaults(self) -> None:
        with patch.object(sys, "argv", ["prog"]):
            args = TRIKMind._parse_args()
        assert args.output_mode is None
        assert args.no_color is False
        assert args.verbose == 0

    def test_output_mode_user(self) -> None:
        with patch.object(sys, "argv", ["prog", "-o", "user"]):
            args = TRIKMind._parse_args()
        assert args.output_mode == "user"

    def test_output_mode_stdout(self) -> None:
        with patch.object(sys, "argv", ["prog", "--output-mode", "stdout"]):
            args = TRIKMind._parse_args()
        assert args.output_mode == "stdout"

    def test_no_color(self) -> None:
        with patch.object(sys, "argv", ["prog", "--no-color"]):
            args = TRIKMind._parse_args()
        assert args.no_color is True

    def test_verbose(self) -> None:
        with patch.object(sys, "argv", ["prog", "-v"]):
            args = TRIKMind._parse_args()
        assert args.verbose == 1

    def test_verbose_verbose(self) -> None:
        with patch.object(sys, "argv", ["prog", "-v", "-v"]):
            args = TRIKMind._parse_args()
        assert args.verbose == 2

    def test_demo_flag(self) -> None:
        with patch.object(sys, "argv", ["prog", "--demo"]):
            args = TRIKMind._parse_args()
        assert args.demo is True
        assert args.fps == 16.0

    def test_demo_fps_override(self) -> None:
        with patch.object(sys, "argv", ["prog", "--demo", "--fps", "8"]):
            args = TRIKMind._parse_args()
        assert args.demo is True
        assert args.fps == 8.0


class TestBuildFormatter:
    def test_stdout_mode(self) -> None:
        fmt = TRIKMind._build_formatter("stdout", color_enabled=False, verbose=1)
        assert isinstance(fmt, StdoutOutputFormatter)

    def test_user_mode(self) -> None:
        fmt = TRIKMind._build_formatter("user", color_enabled=True, verbose=0)
        assert isinstance(fmt, UserOutputFormatter)
        assert fmt._view_threshold == 0.4

    def test_user_mode_custom_view_threshold(self) -> None:
        fmt = TRIKMind._build_formatter("user", color_enabled=True, verbose=0, view_threshold=0.55)
        assert isinstance(fmt, UserOutputFormatter)
        assert fmt._view_threshold == 0.55
        assert isinstance(fmt, UserOutputFormatter)


def test_main_missing_settings_exits() -> None:
    with (
        patch.object(sys, "argv", ["prog"]),
        patch("TRIKMind.load_settings", side_effect=FileNotFoundError),
        patch.object(sys.stdin, "isatty", return_value=False),
        patch.object(builtins, "input") as mock_input,
        patch.object(sys, "exit", side_effect=SystemExit) as mock_exit,
        pytest.raises(SystemExit),
    ):
        TRIKMind.main()
    mock_exit.assert_called_once_with(1)
    mock_input.assert_not_called()


def test_main_with_stdout_output_mode() -> None:
    mock_settings = MagicMock()
    mock_settings.output_mode = "user"
    mock_settings.color_enabled = True

    with (
        patch.object(sys, "argv", ["prog", "-o", "stdout"]),
        patch("TRIKMind.load_settings", return_value=mock_settings),
        patch("TRIKMind.resolve_model_path", return_value=MagicMock()),
        patch("TRIKMind.MindServer") as mock_mind,
        patch("TRIKMind.asyncio.run", side_effect=KeyboardInterrupt),
        patch.object(sys.stdin, "isatty", return_value=False),
        patch.object(builtins, "input"),
    ):
        TRIKMind.main()

    assert mock_mind.called
    _call_kwargs = mock_mind.call_args.kwargs  # type: ignore[reportUnknownVariableType]
    formatter = _call_kwargs.get("formatter")
    assert isinstance(formatter, StdoutOutputFormatter)


def test_main_keyboard_interrupt_closes_server() -> None:
    mock_server = MagicMock()
    with (
        patch.object(sys, "argv", ["prog"]),
        patch("TRIKMind.load_settings", return_value=MagicMock()),
        patch("TRIKMind.resolve_model_path", return_value=MagicMock()),
        patch("TRIKMind.MindServer", return_value=mock_server),
        patch("TRIKMind.asyncio.run", side_effect=KeyboardInterrupt),
        patch.object(sys.stdin, "isatty", return_value=False),
        patch.object(builtins, "input") as mock_input,
    ):
        TRIKMind.main()
    mock_server.close.assert_called_once()
    mock_input.assert_not_called()


def test_run_demo_wires_formatter_and_source() -> None:
    mock_formatter = MagicMock()
    mock_source = MagicMock()
    mock_source.run.side_effect = KeyboardInterrupt
    with (
        patch("TRIKMind.UserOutputFormatter", return_value=mock_formatter),
        patch("TRIKMind.DemoSource", return_value=mock_source) as mock_demo_cls,
        patch("TRIKMind.logger"),
    ):
        TRIKMind._run_demo(argparse.Namespace(no_color=False, fps=8.0))
    mock_demo_cls.assert_called_once_with(mock_formatter, fps=8.0)
    mock_source.run.assert_called_once()
    mock_formatter.close.assert_called_once()
    mock_formatter.set_context.assert_called_once()


def test_main_demo_branch_skips_server() -> None:
    mock_formatter = MagicMock()
    mock_source = MagicMock()
    mock_source.run.side_effect = KeyboardInterrupt
    with (
        patch.object(sys, "argv", ["prog", "--demo", "--fps", "6"]),
        patch("TRIKMind.UserOutputFormatter", return_value=mock_formatter),
        patch("TRIKMind.DemoSource", return_value=mock_source) as mock_demo_cls,
        patch("TRIKMind.load_settings") as mock_load,
        patch("TRIKMind.MindServer") as mock_server,
        patch("TRIKMind.logger"),
    ):
        TRIKMind.main()
    mock_demo_cls.assert_called_once()
    mock_load.assert_not_called()
    mock_server.assert_not_called()
    mock_source.run.assert_called_once()
    mock_formatter.close.assert_called_once()
