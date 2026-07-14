#!/usr/bin/env python3
"""Copyright 2021 Andrei Khodko, CyberTech Labs Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License."""

import asyncio
import logging
import sys

from lobe_server.config import load_settings, resolve_model_path
from lobe_server.server import LobeServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Starting program")
    try:
        settings = load_settings()
    except FileNotFoundError as _:
        logger.exception("settings.ini not found")
        input("Press any key to close the window...")
        sys.exit(0)

    model_path = resolve_model_path(settings)
    logger.info("Model path: %s", model_path)

    server = LobeServer(settings, model_path)
    try:
        asyncio.run(server.run_forever())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.close()
        logger.info("Press any key to close the window...")
        input()


if __name__ == "__main__":
    main()
