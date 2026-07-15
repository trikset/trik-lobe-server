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


def test_abstract() -> None:
    class Impl(CameraSource):
        pass

    with pytest.raises(TypeError):
        Impl()  # type: ignore[reportAbstractUsage]


@patch("lobe_server.camera.requests.get")
def test_url_camera(mock_get: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.content = _minimal_png()
    mock_get.return_value = mock_response

    cam = UrlCamera("http://example.com/snapshot", "user", "pass")
    im = cam.capture()

    mock_get.assert_called_once_with(
        "http://example.com/snapshot",
        stream=True,
        auth=("user", "pass"),
        timeout=10,
    )
    assert im is not None
    assert im.mode


@patch("lobe_server.camera.requests.get")
def test_robot_camera(mock_get: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.content = _minimal_png()
    mock_get.return_value = mock_response

    cam = RobotCamera("192.168.1.10")
    im = cam.capture()

    mock_get.assert_called_once_with(
        "http://192.168.1.10:8080/?action=snapshot",
        stream=True,
        timeout=10,
    )
    assert im is not None


def test_url_camera_release() -> None:
    cam = UrlCamera("http://example.com")
    cam.release()


def test_robot_camera_release() -> None:
    cam = RobotCamera("192.168.1.1")
    cam.release()


def test_webcam_camera() -> None:
    mock_cv2 = MagicMock()
    mock_capture = MagicMock()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_capture.read.return_value = (True, frame)
    mock_cv2.VideoCapture.return_value = mock_capture
    mock_cv2.COLOR_BGR2RGB = 4
    mock_cv2.cvtColor = lambda img, _: img

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
    cam = create_camera(settings, "127.0.0.1")
    assert isinstance(cam, UrlCamera)


def test_factory_robot() -> None:
    settings = Settings(
        photo_url="",
        get_images_from_robot=True,
    )
    cam = create_camera(settings, "192.168.1.10")
    assert isinstance(cam, RobotCamera)


def test_factory_webcam() -> None:
    settings = Settings(
        photo_url="",
        get_images_from_robot=False,
        camera_number=2,
    )
    with patch.object(WebcamCamera, "__init__", return_value=None):
        cam = create_camera(settings, "127.0.0.1")
    assert isinstance(cam, WebcamCamera)


def test_url_camera_no_auth() -> None:
    cam = UrlCamera("http://example.com")
    assert cam._auth is None


@patch("lobe_server.camera.requests.get")
def test_url_camera_connection_error(mock_get: MagicMock) -> None:
    mock_get.side_effect = requests.ConnectionError("connection refused")
    cam = UrlCamera("http://example.com/snapshot")
    im = cam.capture()
    assert im is None


@patch("lobe_server.camera.requests.get")
def test_url_camera_timeout(mock_get: MagicMock) -> None:
    mock_get.side_effect = requests.Timeout("timed out")
    cam = UrlCamera("http://example.com/snapshot")
    im = cam.capture()
    assert im is None


@patch("lobe_server.camera.requests.get")
def test_url_camera_http_error(mock_get: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    mock_get.return_value = mock_response
    cam = UrlCamera("http://example.com/snapshot")
    im = cam.capture()
    assert im is None


@patch("lobe_server.camera.requests.get")
def test_robot_camera_connection_error(mock_get: MagicMock) -> None:
    mock_get.side_effect = requests.ConnectionError("connection refused")
    cam = RobotCamera("192.168.1.10")
    im = cam.capture()
    assert im is None


@patch("lobe_server.camera.requests.get")
def test_robot_camera_timeout(mock_get: MagicMock) -> None:
    mock_get.side_effect = requests.Timeout("timed out")
    cam = RobotCamera("192.168.1.10")
    im = cam.capture()
    assert im is None


@patch("lobe_server.camera.requests.get")
def test_robot_camera_http_error(mock_get: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    mock_get.return_value = mock_response
    cam = RobotCamera("192.168.1.10")
    im = cam.capture()
    assert im is None


def _minimal_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
        b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
