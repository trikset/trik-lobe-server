# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0212  # tests inspect private entrypoint helpers

import builtins
import sys
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import TRIKLobeServer
from lobe_server.output import StdoutOutputFormatter, UserOutputFormatter


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
        TRIKLobeServer._pause_for_user()
    assert mock_input.call_count == expected_calls


class TestParseArgs:
    def test_defaults(self) -> None:
        with patch.object(sys, "argv", ["prog"]):
            args = TRIKLobeServer._parse_args()
        assert args.output_mode is None
        assert args.no_color is False
        assert args.verbose == 0

    def test_output_mode_user(self) -> None:
        with patch.object(sys, "argv", ["prog", "-o", "user"]):
            args = TRIKLobeServer._parse_args()
        assert args.output_mode == "user"

    def test_output_mode_stdout(self) -> None:
        with patch.object(sys, "argv", ["prog", "--output-mode", "stdout"]):
            args = TRIKLobeServer._parse_args()
        assert args.output_mode == "stdout"

    def test_no_color(self) -> None:
        with patch.object(sys, "argv", ["prog", "--no-color"]):
            args = TRIKLobeServer._parse_args()
        assert args.no_color is True

    def test_verbose(self) -> None:
        with patch.object(sys, "argv", ["prog", "-v"]):
            args = TRIKLobeServer._parse_args()
        assert args.verbose == 1

    def test_verbose_verbose(self) -> None:
        with patch.object(sys, "argv", ["prog", "-v", "-v"]):
            args = TRIKLobeServer._parse_args()
        assert args.verbose == 2


class TestBuildFormatter:
    def test_stdout_mode(self) -> None:
        fmt = TRIKLobeServer._build_formatter("stdout", color_enabled=False, verbose=1)
        assert isinstance(fmt, StdoutOutputFormatter)

    def test_user_mode(self) -> None:
        fmt = TRIKLobeServer._build_formatter("user", color_enabled=True, verbose=0)
        assert isinstance(fmt, UserOutputFormatter)


def test_main_missing_settings_exits() -> None:
    with (
        patch.object(sys, "argv", ["prog"]),
        patch("TRIKLobeServer.load_settings", side_effect=FileNotFoundError),
        patch.object(sys.stdin, "isatty", return_value=False),
        patch.object(builtins, "input") as mock_input,
        patch.object(sys, "exit", side_effect=SystemExit) as mock_exit,
        pytest.raises(SystemExit),
    ):
        TRIKLobeServer.main()
    mock_exit.assert_called_once_with(1)
    mock_input.assert_not_called()


def test_main_with_stdout_output_mode() -> None:
    mock_settings = MagicMock()
    mock_settings.output_mode = "user"
    mock_settings.color_enabled = True

    with (
        patch.object(sys, "argv", ["prog", "-o", "stdout"]),
        patch("TRIKLobeServer.load_settings", return_value=mock_settings),
        patch("TRIKLobeServer.resolve_model_path", return_value=MagicMock()),
        patch("TRIKLobeServer.LobeServer") as mock_lobe,
        patch("TRIKLobeServer.asyncio.run", side_effect=KeyboardInterrupt),
        patch.object(sys.stdin, "isatty", return_value=False),
        patch.object(builtins, "input"),
    ):
        TRIKLobeServer.main()

    assert mock_lobe.called
    _call_kwargs = mock_lobe.call_args.kwargs  # type: ignore[reportUnknownVariableType]
    formatter = _call_kwargs.get("formatter")
    assert isinstance(formatter, StdoutOutputFormatter)


def test_main_keyboard_interrupt_closes_server() -> None:
    mock_server = MagicMock()
    with (
        patch.object(sys, "argv", ["prog"]),
        patch("TRIKLobeServer.load_settings", return_value=MagicMock()),
        patch("TRIKLobeServer.resolve_model_path", return_value=MagicMock()),
        patch("TRIKLobeServer.LobeServer", return_value=mock_server),
        patch("TRIKLobeServer.asyncio.run", side_effect=KeyboardInterrupt),
        patch.object(sys.stdin, "isatty", return_value=False),
        patch.object(builtins, "input") as mock_input,
    ):
        TRIKLobeServer.main()
    mock_server.close.assert_called_once()
    mock_input.assert_not_called()
