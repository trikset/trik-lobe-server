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
    """Add a file handler so double-click users can always find logs."""
    target = log_path or _LOG_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(target), encoding="utf-8", mode="a")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
    except OSError:
        pass  # best-effort; console logging still works


def _get_version() -> str:
    try:
        from importlib.metadata import version as _version  # noqa: PLC0415

        return _version("trik-lobe-server")
    except Exception:  # noqa: BLE001  # importlib.metadata can fail unpredictably in PyInstaller
        return "0.0.0"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TRIK Lobe ML inference server")
    parser.add_argument(
        "-o",
        "--output-mode",
        choices=["user", "stdout"],
        help="Output mode (overrides settings.ini)",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity (stackable: -v -v)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (default: lobe_server.log next to executable)",
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


def _build_context(model_path: Path, settings: Settings) -> str:
    """Build a context header shown at the top of user-mode output."""
    model_name = model_path.name or "."
    if settings.photo_url:
        cam = f"URL {settings.photo_url}"
    elif settings.get_images_from_robot:
        cam = f"Robot {settings.server_ip}:8080"
    else:
        cam = f"Webcam #{settings.camera_number}"
    return f"Model: {model_name}  │  Camera: {cam}  │  Server: {settings.server_ip}:{settings.server_port}"


def main() -> None:
    args = _parse_args()
    log_file = Path(args.log_file) if args.log_file else _LOG_FILE
    _setup_file_logging(log_file)
    logger.info("Starting program (log: %s)", log_file)
    try:
        settings = load_settings()
    except FileNotFoundError as _:
        logger.exception("settings.ini not found")
        _pause_for_user()
        sys.exit(1)

    output_mode = args.output_mode or settings.output_mode
    color_enabled = not args.no_color and settings.color_enabled
    formatter = _build_formatter(output_mode, color_enabled=color_enabled, verbose=args.verbose)

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
