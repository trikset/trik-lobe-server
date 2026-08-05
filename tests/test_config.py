# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

import sys
import tempfile
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from lobe_server.config import load_settings, resolve_model_path


@pytest.fixture
def sample_ini() -> str:
    return dedent("""\
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
    """)


@pytest.fixture
def minimal_ini() -> str:
    return dedent("""\
        [Settings]
        SERVER_IP=127.0.0.1
    """)


def test_load_settings_full(sample_ini: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "settings.ini"
        tmp.write_text(sample_ini, encoding="utf-8")
        s = load_settings(tmp)
        assert s.server_ip == "192.168.1.10"
        assert s.my_hull_number == 5
        assert s.server_port == 9999
        assert s.model_path == "C:\\models\\lobe"
        assert s.photo_url == "http://camera.local/snapshot"
        assert s.get_images_from_robot is False
        assert s.camera_number == 1
        assert s.username == "user"
        assert s.password == "pass"  # noqa: S105


def test_load_settings_minimal(minimal_ini: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "settings.ini"
        tmp.write_text(minimal_ini, encoding="utf-8")
        s = load_settings(tmp)
        assert s.server_ip == "127.0.0.1"
        assert s.my_hull_number == 2
        assert s.server_port == 8889


def test_load_settings_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(Path("nonexistent.ini"))


def test_load_settings_missing_section() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "settings.ini"
        tmp.write_text("[Other]\nfoo=1\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"Settings"):
            load_settings(tmp)


def test_load_settings_invalid_int() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "settings.ini"
        tmp.write_text("[Settings]\nMY_HULL_NUMBER=abc\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"MY_HULL_NUMBER"):
            load_settings(tmp)


def test_load_settings_port_out_of_range() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "settings.ini"
        tmp.write_text("[Settings]\nSERVER_PORT=70000\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"SERVER_PORT"):
            load_settings(tmp)


def test_load_settings_port_zero() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "settings.ini"
        tmp.write_text("[Settings]\nSERVER_PORT=0\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"SERVER_PORT"):
            load_settings(tmp)


def test_load_settings_hull_not_positive() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "settings.ini"
        tmp.write_text("[Settings]\nMY_HULL_NUMBER=0\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"MY_HULL_NUMBER"):
            load_settings(tmp)


def test_load_settings_camera_number_negative() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "settings.ini"
        tmp.write_text("[Settings]\nCAMERA_NUMBER=-1\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"CAMERA_NUMBER"):
            load_settings(tmp)


def test_load_settings_default_path() -> None:
    with (
        patch("lobe_server.config.Path.exists", return_value=False),
        pytest.raises(FileNotFoundError, match=r"settings\.ini"),
    ):
        load_settings()


def test_resolve_model_path_custom() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = MagicMock()
        settings.model_path = tmpdir
        result = resolve_model_path(settings)
        assert result == Path(tmpdir).resolve()


def test_resolve_model_path_default() -> None:
    settings = MagicMock()
    settings.model_path = ""
    result = resolve_model_path(settings)
    expected = Path(__file__).resolve().parent.parent
    assert result == expected


def test_resolve_model_path_frozen() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = MagicMock()
        settings.model_path = ""
        fake_exe = str(Path(tmpdir) / "server.exe")
        with (
            patch.object(sys, "frozen", new=True, create=True),
            patch.object(sys, "executable", fake_exe),
        ):
            result = resolve_model_path(settings)
        assert result == Path(tmpdir).resolve()
