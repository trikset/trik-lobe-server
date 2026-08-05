# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# pyright: reportPrivateUsage=false
# pylint: disable=W0212,E0110  # inspect privates; abstract-instantiation test

from collections.abc import Callable
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import requests

from lobe_server.camera import (
    CameraSource,
    RobotCamera,
    UrlCamera,
    WebcamCamera,
    create_camera,
)
from lobe_server.config import Settings

_CamFactory = Callable[[], UrlCamera | RobotCamera]

_HTTP_CAMERAS = [
    pytest.param(
        lambda: UrlCamera("http://example.com/snapshot", "user", "pass"),
        "http://example.com/snapshot",
        {"auth": ("user", "pass")},
        id="url",
    ),
    pytest.param(
        lambda: RobotCamera("192.168.1.10"),
        "http://192.168.1.10:8080/?action=snapshot",
        {},
        id="robot",
    ),
]

_COOLDOWN_SCENARIOS = [
    pytest.param([100.0, 100.5, 103.0], ["err", "ok"], [None, None, "ok"], id="fail"),
    pytest.param([100.0, 103.0, 104.0], ["err", "ok", "err"], [None, "ok", None], id="reset"),
]


def test_abstract() -> None:
    class Impl(CameraSource):
        pass

    with pytest.raises(TypeError):
        Impl()  # type: ignore[reportAbstractUsage]  # intentionally instantiate an abstract class to assert TypeError


@pytest.mark.parametrize(("factory", "url", "extra"), _HTTP_CAMERAS)
@patch("lobe_server.camera.requests.get")
def test_http_camera_capture(
    mock_get: MagicMock,
    factory: _CamFactory,
    url: str,
    extra: dict[str, object],
) -> None:
    mock_response = MagicMock()
    mock_response.content = _minimal_png()
    mock_get.return_value = mock_response

    im = factory().capture()

    mock_get.assert_called_once_with(url, stream=True, timeout=10, **extra)
    assert im is not None
    assert im.mode


@pytest.mark.parametrize(("factory", "url", "extra"), _HTTP_CAMERAS)
@patch("lobe_server.camera.requests.get", side_effect=requests.RequestException("timeout"))
def test_http_camera_network_error(
    mock_get: MagicMock,
    factory: _CamFactory,
    url: str,
    extra: dict[str, object],
) -> None:
    assert factory().capture() is None
    mock_get.assert_called_once_with(url, stream=True, timeout=10, **extra)


@pytest.mark.parametrize(("factory", "_url", "_extra"), _HTTP_CAMERAS)
def test_http_camera_release(factory: _CamFactory, _url: str, _extra: dict[str, object]) -> None:
    factory().release()


@pytest.mark.parametrize(("factory", "_url", "_extra"), _HTTP_CAMERAS)
@pytest.mark.parametrize(("clock", "get_seq", "expected"), _COOLDOWN_SCENARIOS)
def test_http_camera_cooldown(
    factory: _CamFactory,
    _url: str,
    _extra: dict[str, object],
    clock: list[float],
    get_seq: list[str],
    expected: list[object],
) -> None:
    mock_response = MagicMock()
    mock_response.content = _minimal_png()
    side_effect = [mock_response if kind == "ok" else requests.RequestException("timeout") for kind in get_seq]
    with (
        patch("lobe_server.camera.requests.get", side_effect=side_effect) as mock_get,
        patch("lobe_server.camera.time.monotonic", side_effect=clock),
    ):
        cam = factory()
        results = [cam.capture() for _ in expected]

    for got, want in zip(results, expected, strict=True):
        assert (got is None) is (want is None)
    assert mock_get.call_count == len(get_seq)


def test_webcam_camera() -> None:
    mock_cv2 = MagicMock()
    mock_capture = MagicMock()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_capture.read.return_value = (True, frame)
    mock_cv2.VideoCapture.return_value = mock_capture
    mock_cv2.COLOR_BGR2RGB = 4
    mock_cv2.cvtColor = _cvt_identity

    with patch.object(WebcamCamera, "__init__", return_value=None):
        cam = WebcamCamera.__new__(WebcamCamera)
        cam._cv2 = mock_cv2  # type: ignore[reportAttributeAccessIssue]
        cam._camera = mock_capture  # type: ignore[reportAttributeAccessIssue]
        im = cam.capture()

    assert im is not None
    assert im.size == (100, 100)
    cam.release()
    mock_capture.release.assert_called_once()


def test_webcam_camera_fail() -> None:
    mock_cv2 = MagicMock()
    mock_capture = MagicMock()
    mock_capture.read.return_value = (False, None)
    mock_cv2.VideoCapture.return_value = mock_capture

    with patch.object(WebcamCamera, "__init__", return_value=None):
        cam = WebcamCamera.__new__(WebcamCamera)
        cam._cv2 = mock_cv2  # type: ignore[reportAttributeAccessIssue]
        cam._camera = mock_capture  # type: ignore[reportAttributeAccessIssue]
        assert cam.capture() is None


def test_factory_url() -> None:
    settings = Settings(
        photo_url="http://example.com/snapshot",
        username="u",
        password="p",
    )
    assert isinstance(create_camera(settings, "127.0.0.1"), UrlCamera)


def test_factory_robot() -> None:
    settings = Settings(
        photo_url="",
        get_images_from_robot=True,
    )
    assert isinstance(create_camera(settings, "192.168.1.10"), RobotCamera)


def test_factory_webcam() -> None:
    settings = Settings(
        photo_url="",
        get_images_from_robot=False,
        camera_number=2,
    )
    with patch.object(WebcamCamera, "__init__", return_value=None):
        cam = create_camera(settings, "127.0.0.1")
    assert isinstance(cam, WebcamCamera)


def test_webcam_camera_init() -> None:
    mock_cv2 = MagicMock()
    mock_capture = MagicMock()
    mock_cv2.VideoCapture.return_value = mock_capture
    mock_capture.isOpened.return_value = True

    with patch.dict("sys.modules", {"cv2": mock_cv2}):
        cam = WebcamCamera(0)

    mock_cv2.VideoCapture.assert_called_once_with(0)
    assert cam._cv2 is mock_cv2
    assert cam._camera is mock_capture


def test_webcam_camera_init_not_opened() -> None:
    mock_cv2 = MagicMock()
    mock_capture = MagicMock()
    mock_cv2.VideoCapture.return_value = mock_capture
    mock_capture.isOpened.return_value = False

    with patch.dict("sys.modules", {"cv2": mock_cv2}), pytest.raises(RuntimeError, match=r"Camera #5"):
        WebcamCamera(5)


def test_url_camera_no_auth() -> None:
    assert UrlCamera("http://example.com")._auth is None


def _cvt_identity(img: object, _code: object) -> object:
    return img


def _minimal_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
        b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
