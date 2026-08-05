# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

import configparser
import sys
from dataclasses import dataclass
from pathlib import Path

_MAX_PORT = 65535


@dataclass
class Settings:
    server_ip: str = "127.0.0.1"
    my_hull_number: int = 2
    server_port: int = 8889
    model_path: str = ""
    get_images_from_robot: bool = False
    photo_url: str = ""
    camera_number: int = 0
    username: str = ""
    password: str = ""


def _get_int(section: configparser.SectionProxy, key: str, default: int) -> int:
    raw = section.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        msg = f"Invalid {key} in settings.ini: {raw!r}"
        raise ValueError(msg) from None


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

    server_port = _get_int(s, "SERVER_PORT", 8889)
    if not 1 <= server_port <= _MAX_PORT:
        msg = f"SERVER_PORT out of range (1-{_MAX_PORT}): {server_port}"
        raise ValueError(msg)
    my_hull_number = _get_int(s, "MY_HULL_NUMBER", 2)
    if my_hull_number <= 0:
        msg = f"MY_HULL_NUMBER must be positive: {my_hull_number}"
        raise ValueError(msg)
    camera_number = _get_int(s, "CAMERA_NUMBER", 0)
    if camera_number < 0:
        msg = f"CAMERA_NUMBER must be non-negative: {camera_number}"
        raise ValueError(msg)

    return Settings(
        server_ip=s.get("SERVER_IP", "127.0.0.1"),
        my_hull_number=my_hull_number,
        server_port=server_port,
        model_path=s.get("MODEL_PATH", ""),
        get_images_from_robot=s.get("GET_IMAGES_FROM_ROBOT", "False").lower() == "true",
        photo_url=s.get("PHOTO_URL", ""),
        camera_number=camera_number,
        username=s.get("USERNAME", ""),
        password=s.get("PASSWORD", ""),
    )


def resolve_model_path(settings: Settings) -> Path:
    if settings.model_path:
        return Path(settings.model_path).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.parent.resolve()
