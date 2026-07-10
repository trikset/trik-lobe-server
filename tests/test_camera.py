from unittest.mock import MagicMock, patch

import pytest

from lobe_server.camera import CameraSource, RobotCamera, UrlCamera, WebcamCamera, create_camera
from lobe_server.config import Settings


def test_abstract() -> None:
    class Impl(CameraSource):
        pass

    with pytest.raises(TypeError):
        Impl()


@patch("lobe_server.camera.requests.get")
def test_url_camera(mock_get) -> None:
    mock_response = MagicMock()
    mock_response.content = _minimal_png()
    mock_get.return_value = mock_response

    cam = UrlCamera("http://example.com/snapshot", "user", "pass")
    im = cam.capture()

    mock_get.assert_called_once_with(
        "http://example.com/snapshot",
        stream=True,
        auth=("user", "pass"),
    )
    assert im is not None
    assert im.mode


@patch("lobe_server.camera.requests.get")
def test_robot_camera(mock_get) -> None:
    mock_response = MagicMock()
    mock_response.content = _minimal_png()
    mock_get.return_value = mock_response

    cam = RobotCamera("192.168.1.10")
    im = cam.capture()

    mock_get.assert_called_once_with(
        "http://192.168.1.10:8080/?action=snapshot",
        stream=True,
    )
    assert im is not None


def test_webcam_camera() -> None:
    pytest.importorskip("cv2")

    with patch("lobe_server.camera._cv2", create=True) as mock_cv2:
        mock_capture = MagicMock()
        mock_capture.read.return_value = (True, MagicMock())
        mock_cv2.VideoCapture.return_value = mock_capture

        cam = WebcamCamera(0)
        im = cam.capture()

        mock_cv2.VideoCapture.assert_called_once_with(0)
        assert im is not None
        cam.release()
        mock_capture.release.assert_called_once()


def test_webcam_camera_fail() -> None:
    pytest.importorskip("cv2")

    with patch("lobe_server.camera._cv2", create=True) as mock_cv2:
        mock_capture = MagicMock()
        mock_capture.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_capture

        cam = WebcamCamera(0)
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


def test_factory_webcam_raises() -> None:
    settings = Settings(
        photo_url="",
        get_images_from_robot=False,
        camera_number=2,
    )
    with pytest.raises(ModuleNotFoundError):
        create_camera(settings, "127.0.0.1")


def _minimal_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
