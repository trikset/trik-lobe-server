# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

import builtins
import sys
from unittest.mock import MagicMock, patch

import pytest

import TRIKLobeServer


def test_pause_prompts_when_tty() -> None:
    with (
        patch.object(sys.stdin, "isatty", return_value=True),
        patch.object(builtins, "input") as mock_input,
    ):
        TRIKLobeServer._pause_for_user()
    mock_input.assert_called_once()


def test_pause_skips_when_not_tty() -> None:
    with (
        patch.object(sys.stdin, "isatty", return_value=False),
        patch.object(builtins, "input") as mock_input,
    ):
        TRIKLobeServer._pause_for_user()
    mock_input.assert_not_called()


def test_pause_skips_when_stdin_missing() -> None:
    with (
        patch.object(sys, "stdin", None),
        patch.object(builtins, "input") as mock_input,
    ):
        TRIKLobeServer._pause_for_user()
    mock_input.assert_not_called()


def test_main_missing_settings_exits() -> None:
    with (
        patch("TRIKLobeServer.load_settings", side_effect=FileNotFoundError),
        patch.object(sys.stdin, "isatty", return_value=False),
        patch.object(builtins, "input") as mock_input,
        patch.object(sys, "exit", side_effect=SystemExit) as mock_exit,
        pytest.raises(SystemExit),
    ):
        TRIKLobeServer.main()
    mock_exit.assert_called_once_with(1)
    mock_input.assert_not_called()


def test_main_keyboard_interrupt_closes_server() -> None:
    mock_server = MagicMock()
    with (
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
