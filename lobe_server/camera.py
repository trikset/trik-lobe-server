# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from io import BytesIO
from typing import TYPE_CHECKING

import requests
from PIL import Image

if TYPE_CHECKING:
    from lobe_server.config import Settings

logger = logging.getLogger(__name__)

_FAILURE_COOLDOWN = 2.0  # skip HTTP fetch for this long after a failure


def _within_cooldown(last_failure: float | None) -> bool:
    return last_failure is not None and time.monotonic() - last_failure < _FAILURE_COOLDOWN


class CameraSource(ABC):
    @abstractmethod
    def capture(self) -> Image.Image | None: ...

    @abstractmethod
    def release(self) -> None: ...


class UrlCamera(CameraSource):
    def __init__(self, url: str, username: str = "", password: str = "") -> None:  # nosec B107  # empty-string default, not a secret
        self._url = url
        self._auth: tuple[str, str] | None = None
        if username and password:
            self._auth = (username, password)
        self._last_failure: float | None = None

    def capture(self) -> Image.Image | None:
        if _within_cooldown(self._last_failure):
            return None
        try:
            resp = requests.get(self._url, stream=True, auth=self._auth, timeout=10)
            resp.raise_for_status()
            self._last_failure = None
            return Image.open(BytesIO(resp.content))
        except requests.RequestException:
            logger.exception("Failed to fetch image from URL camera: %s", self._url)
            self._last_failure = time.monotonic()
            return None

    def release(self) -> None:
        pass


class RobotCamera(CameraSource):
    def __init__(self, server_ip: str) -> None:
        self._url = f"http://{server_ip}:8080/?action=snapshot"
        self._last_failure: float | None = None

    def capture(self) -> Image.Image | None:
        if _within_cooldown(self._last_failure):
            return None
        try:
            resp = requests.get(self._url, stream=True, timeout=10)
            resp.raise_for_status()
            self._last_failure = None
            return Image.open(BytesIO(resp.content))
        except requests.RequestException:
            logger.exception("Failed to fetch image from robot camera: %s", self._url)
            self._last_failure = time.monotonic()
            return None

    def release(self) -> None:
        pass


class WebcamCamera(CameraSource):
    def __init__(self, camera_number: int) -> None:
        import cv2 as _cv2  # noqa: PLC0415  # lazy: 50+ MB native DLLs, only WebcamCamera needs it

        self._cv2 = _cv2
        self._camera = _cv2.VideoCapture(camera_number)
        if not self._camera.isOpened():
            msg = f"Camera #{camera_number} not found or busy. Check CAMERA_NUMBER in settings.ini."
            raise RuntimeError(msg)

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
