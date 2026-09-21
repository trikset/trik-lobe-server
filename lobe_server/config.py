# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

import configparser
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_PORT = 65535


@dataclass
class Settings:
    robot_ip: str = "127.0.0.1"
    robot_port: int = 8889
    robot_video_port: int = 8080
    my_hull_number: int = 2
    model_path: str = ""
    camera_source: str = ""
    output_mode: str = "user"
    color_enabled: bool = True


def _get_int(section: configparser.SectionProxy, key: str, default: int) -> int:
    raw = section.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        msg = f"Invalid {key} in settings.ini: {raw!r}"
        raise ValueError(msg) from None


def _deprecated(section: configparser.SectionProxy, old: str, fallback: str) -> str | None:
    """Read old key as fallback, log deprecation warning."""
    val = section.get(old)
    if val is not None:
        logger.warning("settings.ini: %s is deprecated — use %s instead", old, fallback)
    return val


def _fallback_port(s: configparser.SectionProxy) -> int:
    """Read ROBOT_PORT with SERVER_PORT as backward-compat fallback."""
    port = _get_int(s, "ROBOT_PORT", 0)
    if port:
        return port
    old = _get_int(s, "SERVER_PORT", 8889)
    if old != 8889:  # noqa: PLR2004  # backward-compat: user had a custom SERVER_PORT
        _deprecated(s, "SERVER_PORT", "ROBOT_PORT")
    return old


def _fallback_hull(s: configparser.SectionProxy) -> int:
    """Read MY_HULL_NUMBER (this instance's identity) with ROBOT_HULL as backward-compat fallback."""
    hull = _get_int(s, "MY_HULL_NUMBER", 0)
    if hull:
        return hull
    old = _get_int(s, "ROBOT_HULL", 2)
    if old != 2:  # noqa: PLR2004  # backward-compat: user had a custom ROBOT_HULL
        _deprecated(s, "ROBOT_HULL", "MY_HULL_NUMBER")
    return old


def _fallback_camera_source(s: configparser.SectionProxy) -> str:
    """Read CAMERA_SOURCE with old keys (GET_IMAGES_FROM_ROBOT, PHOTO_URL, CAMERA_NUMBER) as fallback."""
    src = (s.get("CAMERA_SOURCE") or "").strip()
    if src:
        return src
    if s.get("GET_IMAGES_FROM_ROBOT", "false").lower() == "true":
        _deprecated(s, "GET_IMAGES_FROM_ROBOT", "CAMERA_SOURCE (unset)")
        return ""
    if s.get("PHOTO_URL"):
        _deprecated(s, "PHOTO_URL", "CAMERA_SOURCE")
        return s.get("PHOTO_URL", "")
    cam = _get_int(s, "CAMERA_NUMBER", -1)
    if cam >= 0:
        _deprecated(s, "CAMERA_NUMBER", "CAMERA_SOURCE")
        return str(cam)
    return ""


def load_settings(path: Path | None = None) -> Settings:
    if path is None:
        path = Path("settings.ini")

    if not path.exists():
        msg = f"settings.ini not found at {path.resolve()}"
        raise FileNotFoundError(msg)

    config = configparser.ConfigParser()
    config.read(str(path), encoding="utf8")
    if "Settings" not in config:
        msg = f"settings.ini at {path.resolve()} is missing the [Settings] section."
        raise ValueError(msg)
    s = config["Settings"]

    robot_ip = s.get("ROBOT_IP") or _deprecated(s, "SERVER_IP", "ROBOT_IP") or "127.0.0.1"

    robot_port = _fallback_port(s)
    if not 1 <= robot_port <= _MAX_PORT:
        msg = f"ROBOT_PORT out of range (1-{_MAX_PORT}): {robot_port}"
        raise ValueError(msg)

    robot_video_port = _get_int(s, "ROBOT_VIDEO_PORT", 8080)
    if not 1 <= robot_video_port <= _MAX_PORT:
        msg = f"ROBOT_VIDEO_PORT out of range (1-{_MAX_PORT}): {robot_video_port}"
        raise ValueError(msg)

    my_hull_number = _fallback_hull(s)
    if my_hull_number <= 0:
        msg = f"MY_HULL_NUMBER must be positive: {my_hull_number}"
        raise ValueError(msg)

    camera_source = _fallback_camera_source(s)

    ui = config["UI"] if "UI" in config else config["Settings"]
    output_mode = ui.get("OUTPUT_MODE", "user")
    if output_mode not in ("user", "stdout"):
        msg = f"Invalid OUTPUT_MODE in settings.ini: {output_mode!r}"
        raise ValueError(msg)
    color_enabled = ui.get("COLOR_ENABLED", "true").lower() == "true"

    return Settings(
        robot_ip=robot_ip,
        robot_port=robot_port,
        robot_video_port=robot_video_port,
        my_hull_number=my_hull_number,
        model_path=s.get("MODEL_PATH", ""),
        camera_source=camera_source,
        output_mode=output_mode,
        color_enabled=color_enabled,
    )


def resolve_model_path(settings: Settings) -> Path:
    if settings.model_path:
        return Path(settings.model_path).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.parent.resolve()
