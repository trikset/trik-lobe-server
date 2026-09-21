#!/usr/bin/env python3
"""
Copyright 2021 Andrei Khodko, CyberTech Labs Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from lobe_server.config import Settings, load_settings, resolve_model_path
from lobe_server.output import StdoutOutputFormatter, UserOutputFormatter
from lobe_server.server import LobeServer

_LOG_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
_LOG_FILE = _LOG_DIR / "lobe_server.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _setup_file_logging(log_path: Path | None = None) -> None:
    target = log_path or _LOG_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(target), encoding="utf-8", mode="a")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
    except OSError:
        pass


def _get_version() -> str:
    try:
        from importlib.metadata import version as _version  # noqa: PLC0415
        return _version("trik-lobe-server")
    except Exception:  # noqa: BLE001
        return "0.0.0"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TRIK Lobe ML inference server")
    parser.add_argument(
        "-o", "--output-mode",
        choices=["user", "stdout"],
        help="Output mode (overrides settings.ini)",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument(
        "-v", "--verbose",
        action="count", default=0,
        help="Increase output verbosity (stackable: -v -v)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_get_version()}")
    parser.add_argument(
        "--log-file", type=str, default=None,
        help="Path to log file (default: lobe_server.log next to executable)",
    )
    parser.add_argument(
        "--robot-ip", type=str, default=None,
        help="Robot IP address (overrides settings.ini)",
    )
    parser.add_argument(
        "--robot-port", type=int, default=None,
        help="Robot TCP port for predictions (overrides settings.ini)",
    )
    parser.add_argument(
        "--robot-video-port", type=int, default=None,
        help="Robot MJPEG video HTTP port (overrides settings.ini)",
    )
    parser.add_argument(
        "--camera-source", type=str, default=None,
        help="Camera source (empty=auto from robot, URL, rtsp://, device index or path)",
    )
    return parser.parse_args()


def _pause_for_user() -> None:
    if sys.stdin is not None and sys.stdin.isatty():
        input("Press any key to close the window...")


def _build_formatter(
    output_mode: str, *, color_enabled: bool, verbose: int
) -> UserOutputFormatter | StdoutOutputFormatter:
    if output_mode == "stdout":
        return StdoutOutputFormatter(verbose=verbose)
    return UserOutputFormatter(color_enabled=color_enabled)


def _find_model_file(model_path: Path) -> str:
    try:
        files = sorted(model_path.glob("*.tflite")) + sorted(model_path.glob("*.onnx"))
        if files:
            return files[0].name
        sig = model_path / "signature.json"
        if sig.exists():
            import json  # noqa: PLC0415
            with sig.open(encoding="utf-8-sig") as f:
                return json.load(f).get("filename", "?")
    except (OSError, ValueError, TypeError):
        pass
    return "?"


def _build_context(model_path: Path, settings: Settings) -> str:
    model_name = _find_model_file(model_path)
    src = (settings.camera_source or "").strip()
    if src.startswith(("http://", "https://", "rtsp://")):
        cam = src
    elif not src:
        cam = f"Robot {settings.robot_ip}:{settings.robot_video_port}" if settings.robot_ip else "USB camera"
    else:
        cam = f"USB camera ({src})"
    return f"Model: {model_name}  │  Camera: {cam}  │  Robot: {settings.robot_ip}:{settings.robot_port}"


def main() -> None:
    args = _parse_args()
    log_file = Path(args.log_file) if args.log_file else _LOG_FILE
    _setup_file_logging(log_file)
    logger.info("Starting program (log: %s)", log_file)
    try:
        settings = load_settings()
    except FileNotFoundError:
        logger.exception("settings.ini not found")
        _pause_for_user()
        sys.exit(1)

    if args.output_mode:
        settings.output_mode = args.output_mode
    if args.robot_ip:
        settings.robot_ip = args.robot_ip
    if args.robot_port:
        settings.robot_port = args.robot_port
    if args.robot_video_port:
        settings.robot_video_port = args.robot_video_port
    if args.camera_source:
        settings.camera_source = args.camera_source

    color_enabled = not args.no_color and settings.color_enabled
    formatter = _build_formatter(settings.output_mode, color_enabled=color_enabled, verbose=args.verbose)

    model_path = resolve_model_path(settings)
    logger.info("Model path: %s", model_path)

    if isinstance(formatter, UserOutputFormatter):
        formatter.set_context(_build_context(model_path, settings))

    server = LobeServer(settings, model_path, formatter=formatter)
    try:
        asyncio.run(server.run_forever())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.close()
        logger.info("Press any key to close the window...")
        _pause_for_user()


if __name__ == "__main__":
    main()
