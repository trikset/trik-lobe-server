# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pylint: disable=W0621  # pytest fixture names shadow module scope

import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from trik_mind.config import load_settings, resolve_model_path

_SAMPLE = dedent(
    """\
    [Settings]
    ROBOT_IP=192.168.1.10
    ROBOT_HULL=5
    ROBOT_PORT=9999
    ROBOT_VIDEO_PORT=8081
    MODEL_PATH=C:\\models\\mind
    CAMERA_SOURCE=0
    """
)


@pytest.fixture
def ini_path(tmp_path: Path) -> Path:
    return tmp_path / "settings.ini"


def test_load_settings_full(ini_path: Path) -> None:
    ini_path.write_text(_SAMPLE, encoding="utf-8")
    s = load_settings(ini_path)
    assert s.robot_ip == "192.168.1.10"
    assert s.my_hull_number == 5
    assert s.robot_port == 9999
    assert s.robot_video_port == 8081
    assert s.model_path == "C:\\models\\mind"
    assert s.camera_source == "0"


def test_load_settings_minimal(ini_path: Path) -> None:
    ini_path.write_text("[Settings]\nROBOT_IP=127.0.0.1\n", encoding="utf-8")
    s = load_settings(ini_path)
    assert s.robot_ip == "127.0.0.1"
    assert s.my_hull_number == 2
    assert s.robot_port == 8889
    assert s.robot_video_port == 8080


def test_load_settings_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(Path("nonexistent.ini"))


@pytest.mark.parametrize(
    ("ini_content", "match"),
    [
        ("[Other]\nfoo=1\n", r"Settings"),
        ("[Settings]\nROBOT_PORT=abc\n", r"Invalid"),
        ("[Settings]\nROBOT_PORT=70000\n", r"ROBOT_PORT"),
        ("[Settings]\nROBOT_PORT=99999\n", r"ROBOT_PORT"),
        ("[Settings]\nROBOT_VIDEO_PORT=0\n", r"ROBOT_VIDEO_PORT"),
        ("[Settings]\nROBOT_VIDEO_PORT=70000\n", r"ROBOT_VIDEO_PORT"),
        ("[Settings]\nMY_HULL_NUMBER=-1\n", r"MY_HULL_NUMBER"),
    ],
)
def test_load_settings_validation_error(ini_path: Path, ini_content: str, match: str) -> None:
    ini_path.write_text(ini_content, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_settings(ini_path)


def test_load_settings_default_path() -> None:
    with (
        patch("trik_mind.config.Path.exists", return_value=False),
        pytest.raises(FileNotFoundError, match=r"settings\.ini"),
    ):
        load_settings()


def test_load_settings_backward_compat_old_names(ini_path: Path) -> None:
    """Old config keys (SERVER_IP, MY_HULL_NUMBER, SERVER_PORT) still work."""
    content = dedent("""\
        [Settings]
        SERVER_IP=10.0.0.1
        MY_HULL_NUMBER=7
        SERVER_PORT=7777
        GET_IMAGES_FROM_ROBOT=true
    """)
    ini_path.write_text(content, encoding="utf-8")
    s = load_settings(ini_path)
    assert s.robot_ip == "10.0.0.1"
    assert s.my_hull_number == 7
    assert s.robot_port == 7777
    assert not s.camera_source  # empty means auto from ROBOT_IP


def test_load_settings_backward_compat_photo_url(ini_path: Path) -> None:
    """Old PHOTO_URL sets camera_source to URL."""
    content = dedent("""\
        [Settings]
        SERVER_IP=127.0.0.1
        PHOTO_URL=http://cam.local/snap
    """)
    ini_path.write_text(content, encoding="utf-8")
    s = load_settings(ini_path)
    assert s.camera_source == "http://cam.local/snap"


def test_load_settings_backward_compat_camera_number(ini_path: Path) -> None:
    """Old CAMERA_NUMBER sets camera_source to index string."""
    content = dedent("""\
        [Settings]
        SERVER_IP=127.0.0.1
        CAMERA_NUMBER=2
    """)
    ini_path.write_text(content, encoding="utf-8")
    s = load_settings(ini_path)
    assert s.camera_source == "2"


def test_resolve_model_path_custom() -> None:
    settings = MagicMock()
    settings.model_path = "C:\\models"
    result = resolve_model_path(settings)
    assert result == Path("C:\\models").resolve()


def test_resolve_model_path_default() -> None:
    settings = MagicMock()
    settings.model_path = ""
    result = resolve_model_path(settings)
    assert result == Path(__file__).resolve().parent.parent


def test_resolve_model_path_frozen() -> None:
    settings = MagicMock()
    settings.model_path = ""
    with (
        patch.object(sys, "frozen", new=True, create=True),
        patch.object(sys, "executable", "C:\\fake\\server.exe"),
    ):
        result = resolve_model_path(settings)
    assert result == Path("C:\\fake\\server.exe").parent.resolve()


def test_load_settings_ui_section_parsed(ini_path: Path) -> None:
    content = dedent("""\
        [Settings]
        ROBOT_IP=127.0.0.1
        [UI]
        OUTPUT_MODE=stdout
        COLOR_ENABLED=false
    """)
    ini_path.write_text(content, encoding="utf-8")
    s = load_settings(ini_path)
    assert s.output_mode == "stdout"
    assert s.color_enabled is False


def test_load_settings_ui_defaults_when_missing(ini_path: Path) -> None:
    ini_path.write_text("[Settings]\nROBOT_IP=127.0.0.1\n", encoding="utf-8")
    s = load_settings(ini_path)
    assert s.output_mode == "user"
    assert s.color_enabled is True


def test_load_settings_invalid_output_mode(ini_path: Path) -> None:
    content = dedent("""\
        [Settings]
        ROBOT_IP=127.0.0.1
        [UI]
        OUTPUT_MODE=invalid
    """)
    ini_path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=r"OUTPUT_MODE"):
        load_settings(ini_path)


def test_load_settings_threshold_defaults(ini_path: Path) -> None:
    """No threshold keys -> documented defaults (view 0.4, send 0.6)."""
    ini_path.write_text("[Settings]\nROBOT_IP=127.0.0.1\n", encoding="utf-8")
    s = load_settings(ini_path)
    assert s.view_threshold == 0.4
    assert s.send_threshold == 0.6


def test_load_settings_threshold_explicit(ini_path: Path) -> None:
    ini_path.write_text("[Settings]\nVIEW_THRESHOLD=0.35\nSEND_THRESHOLD=0.75\n", encoding="utf-8")
    s = load_settings(ini_path)
    assert s.view_threshold == 0.35
    assert s.send_threshold == 0.75


@pytest.mark.parametrize(
    ("ini_content", "match"),
    [
        ("[Settings]\nVIEW_THRESHOLD=banana\n", r"VIEW_THRESHOLD"),
        ("[Settings]\nSEND_THRESHOLD=abc\n", r"SEND_THRESHOLD"),
        ("[Settings]\nVIEW_THRESHOLD=0\n", r"VIEW_THRESHOLD"),
        ("[Settings]\nSEND_THRESHOLD=-0.5\n", r"SEND_THRESHOLD"),
        ("[Settings]\nSEND_THRESHOLD=1.5\n", r"SEND_THRESHOLD"),
        ("[Settings]\nVIEW_THRESHOLD=0.8\nSEND_THRESHOLD=0.6\n", r"VIEW_THRESHOLD"),
    ],
)
def test_load_settings_threshold_invalid(ini_path: Path, ini_content: str, match: str) -> None:
    ini_path.write_text(ini_content, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_settings(ini_path)


def test_load_settings_threshold_view_equals_send_ok(ini_path: Path) -> None:
    """View == send is a valid degenerate config (everything shown = everything sent)."""
    ini_path.write_text("[Settings]\nVIEW_THRESHOLD=0.5\nSEND_THRESHOLD=0.5\n", encoding="utf-8")
    s = load_settings(ini_path)
    assert s.view_threshold == s.send_threshold == 0.5


def test_send_on_change_only_default_false(ini_path: Path) -> None:
    """SEND_ON_CHANGE_ONLY defaults to False when not set."""
    ini_path.write_text("[Settings]\nROBOT_IP=127.0.0.1\n", encoding="utf-8")
    s = load_settings(ini_path)
    assert s.send_on_change_only is False


def test_send_on_change_only_explicit_true(ini_path: Path) -> None:
    """SEND_ON_CHANGE_ONLY=True is read correctly."""
    ini_path.write_text("[Settings]\nROBOT_IP=127.0.0.1\nSEND_ON_CHANGE_ONLY=true\n", encoding="utf-8")
    s = load_settings(ini_path)
    assert s.send_on_change_only is True
