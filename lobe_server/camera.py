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

_FAILURE_COOLDOWN = 2.0


def _within_cooldown(last_failure: float | None) -> bool:
    return last_failure is not None and time.monotonic() - last_failure < _FAILURE_COOLDOWN


class CameraSource(ABC):
    @abstractmethod
    def capture(self) -> Image.Image | None: ...

    @abstractmethod
    def release(self) -> None: ...


class UrlCamera(CameraSource):
    def __init__(self, url: str, username: str = "", password: str = "") -> None:  # nosec B107
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
    def __init__(self, server_ip: str, port: int = 8080) -> None:
        self._url = f"http://{server_ip}:{port}/?action=snapshot"
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
    def __init__(self, source: int | str) -> None:
        import cv2 as _cv2  # noqa: PLC0415

        self._cv2 = _cv2
        self._camera = _cv2.VideoCapture(source)
        if not self._camera.isOpened():
            msg = f"Camera source {source!r} not found or busy. Check CAMERA_SOURCE in settings.ini."
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


def create_camera(settings: Settings) -> CameraSource:
    src = (settings.camera_source or "").strip()

    if not src:
        if settings.robot_ip:
            return RobotCamera(settings.robot_ip, settings.robot_video_port)
        return WebcamCamera(0)

    if src.startswith(("http://", "https://")):
        return UrlCamera(src)

    if src.startswith("rtsp://"):
        return WebcamCamera(src)

    try:
        return WebcamCamera(int(src))
    except ValueError:
        return WebcamCamera(src)
