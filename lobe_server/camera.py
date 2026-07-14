from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from io import BytesIO

import requests
from PIL import Image

from lobe_server.config import Settings

logger = logging.getLogger(__name__)


class CameraSource(ABC):
    @abstractmethod
    def capture(self) -> Image.Image | None: ...

    @abstractmethod
    def release(self) -> None: ...


class UrlCamera(CameraSource):
    def __init__(self, url: str, username: str = "", password: str = ""):
        self._url = url
        self._auth: tuple[str, str] | None = None
        if username and password:
            self._auth = (username, password)

    def capture(self) -> Image.Image | None:
        resp = requests.get(self._url, stream=True, auth=self._auth, timeout=10)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content))

    def release(self) -> None:
        pass


class RobotCamera(CameraSource):
    def __init__(self, server_ip: str):
        self._url = f"http://{server_ip}:8080/?action=snapshot"

    def capture(self) -> Image.Image | None:
        resp = requests.get(self._url, stream=True, timeout=10)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content))

    def release(self) -> None:
        pass


class WebcamCamera(CameraSource):
    def __init__(self, camera_number: int):
        import cv2 as _cv2  # lazy: 50+ MB native DLLs, only WebcamCamera needs it

        self._cv2 = _cv2
        self._camera = _cv2.VideoCapture(camera_number)
        if not self._camera.isOpened():
            logger.critical(
                "Camera #%d not found or busy. Check CAMERA_NUMBER in settings.ini.",
                camera_number,
            )

    def capture(self) -> Image.Image | None:
        ret, frame = self._camera.read()
        if not ret:
            logger.error("Failed to read frame from camera.")
            return None
        color_converted = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        return Image.fromarray(color_converted)

    def release(self) -> None:
        self._camera.release()


def create_camera(settings: Settings, server_ip: str) -> CameraSource:
    if settings.photo_url:
        return UrlCamera(settings.photo_url, settings.username, settings.password)
    if settings.get_images_from_robot:
        return RobotCamera(server_ip)
    return WebcamCamera(settings.camera_number)
