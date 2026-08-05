# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from lobe_server.config import load_settings, resolve_model_path

_SAMPLE = dedent(
    """\
    [Settings]
    SERVER_IP=192.168.1.10
    MY_HULL_NUMBER=5
    SERVER_PORT=9999
    MODEL_PATH=C:\\models\\lobe
    PHOTO_URL=http://camera.local/snapshot
    GET_IMAGES_FROM_ROBOT=False
    CAMERA_NUMBER=1
    USERNAME=user
    PASSWORD=pass
    """
)


@pytest.fixture
def ini_path(tmp_path: Path) -> Path:
    return tmp_path / "settings.ini"


def test_load_settings_full(ini_path: Path) -> None:
    ini_path.write_text(_SAMPLE, encoding="utf-8")
    s = load_settings(ini_path)
    assert s.server_ip == "192.168.1.10"
    assert s.my_hull_number == 5
    assert s.server_port == 9999
    assert s.model_path == "C:\\models\\lobe"
    assert s.photo_url == "http://camera.local/snapshot"
    assert s.get_images_from_robot is False
    assert s.camera_number == 1
    assert s.username == "user"
    assert s.password == "pass"  # noqa: S105


def test_load_settings_minimal(ini_path: Path) -> None:
    ini_path.write_text("[Settings]\nSERVER_IP=127.0.0.1\n", encoding="utf-8")
    s = load_settings(ini_path)
    assert s.server_ip == "127.0.0.1"
    assert s.my_hull_number == 2
    assert s.server_port == 8889


def test_load_settings_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(Path("nonexistent.ini"))


@pytest.mark.parametrize(
    ("ini_content", "match"),
    [
        ("[Other]\nfoo=1\n", r"Settings"),
        ("[Settings]\nMY_HULL_NUMBER=abc\n", r"MY_HULL_NUMBER"),
        ("[Settings]\nSERVER_PORT=70000\n", r"SERVER_PORT"),
        ("[Settings]\nSERVER_PORT=0\n", r"SERVER_PORT"),
        ("[Settings]\nMY_HULL_NUMBER=0\n", r"MY_HULL_NUMBER"),
        ("[Settings]\nCAMERA_NUMBER=-1\n", r"CAMERA_NUMBER"),
    ],
)
def test_load_settings_validation_error(ini_path: Path, ini_content: str, match: str) -> None:
    ini_path.write_text(ini_content, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_settings(ini_path)


def test_load_settings_default_path() -> None:
    with (
        patch("lobe_server.config.Path.exists", return_value=False),
        pytest.raises(FileNotFoundError, match=r"settings\.ini"),
    ):
        load_settings()


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
