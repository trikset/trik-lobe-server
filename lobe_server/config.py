import configparser
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    # Defaults are intentional for TRIK hardware — not security issues (bandit B107)
    server_ip: str = "127.0.0.1"
    my_hull_number: int = 2
    server_port: int = 8889
    model_path: str = ""
    get_images_from_robot: bool = False
    photo_url: str = ""
    camera_number: int = 0
    username: str = ""
    password: str = ""


def load_settings(path: Path | None = None) -> Settings:
    if path is None:
        path = Path("settings.ini")

    if not path.exists():
        msg = f"settings.ini not found at {path.resolve()}"
        raise FileNotFoundError(msg)

    config = configparser.ConfigParser()
    config.read(str(path), encoding="utf8")
    s = config["Settings"]
    return Settings(
        server_ip=s.get("SERVER_IP", "127.0.0.1"),
        my_hull_number=int(s.get("MY_HULL_NUMBER", "2")),
        server_port=int(s.get("SERVER_PORT", "8889")),
        model_path=s.get("MODEL_PATH", ""),
        get_images_from_robot=s.get("GET_IMAGES_FROM_ROBOT", "False").lower() == "true",
        photo_url=s.get("PHOTO_URL", ""),
        camera_number=int(s.get("CAMERA_NUMBER", "0")),
        username=s.get("USERNAME", ""),
        password=s.get("PASSWORD", ""),
    )


def resolve_model_path(settings: Settings) -> Path:
    if settings.model_path:
        return Path(settings.model_path).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.parent.resolve()
