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
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
        f.write(sample_ini)
        tmp = Path(f.name)

    try:
        s = load_settings(tmp)
        assert s.server_ip == "192.168.1.10"
        assert s.my_hull_number == 5
        assert s.server_port == 9999
        assert s.model_path == "C:\\models\\lobe"
        assert s.photo_url == "http://camera.local/snapshot"
        assert s.get_images_from_robot is False
        assert s.camera_number == 1
        assert s.username == "user"
        assert s.password == "pass"
    finally:
        tmp.unlink()


def test_load_settings_minimal(minimal_ini: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
        f.write(minimal_ini)
        tmp = Path(f.name)

    try:
        s = load_settings(tmp)
        assert s.server_ip == "127.0.0.1"
        assert s.my_hull_number == 2
        assert s.server_port == 8889
    finally:
        tmp.unlink()


def test_load_settings_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(Path("nonexistent.ini"))


def test_load_settings_default_path() -> None:
    with patch("lobe_server.config.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError, match="settings.ini"):
            load_settings()


def test_resolve_model_path_custom() -> None:
    settings = MagicMock()
    settings.model_path = "/custom/path"
    result = resolve_model_path(settings)
    assert result == Path("/custom/path").resolve()


def test_resolve_model_path_default() -> None:
    settings = MagicMock()
    settings.model_path = ""
    result = resolve_model_path(settings)
    expected = Path(__file__).resolve().parent.parent
    assert result == expected


def test_resolve_model_path_frozen() -> None:
    settings = MagicMock()
    settings.model_path = ""
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "executable", "/usr/local/bin/server.exe"),
    ):
        result = resolve_model_path(settings)
    assert result == Path("/usr/local/bin").resolve()
