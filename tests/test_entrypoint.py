# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

import builtins
import sys
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import TRIKLobeServer


@pytest.mark.parametrize(
    ("stdin_patch", "expected"),
    [
        pytest.param(lambda: patch.object(sys.stdin, "isatty", return_value=True), True, id="tty"),
        pytest.param(lambda: patch.object(sys.stdin, "isatty", return_value=False), False, id="non-tty"),
        pytest.param(lambda: patch.object(sys, "stdin", None), False, id="missing-stdin"),
    ],
)
def test_pause_gating(stdin_patch: Callable[[], Any], expected: bool) -> None:  # noqa: FBT001
    with stdin_patch(), patch.object(builtins, "input") as mock_input:
        TRIKLobeServer._pause_for_user()
    assert mock_input.called is expected


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
