from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from pathlib import Path

from lobe_server.camera import CameraSource, create_camera
from lobe_server.config import Settings
from lobe_server.model import load_model
from lobe_server.protocol import format_message, is_quit_command, make_command

logger = logging.getLogger(__name__)


class LobeServer:
    KEEPALIVE_INTERVAL = 5
    PREDICTION_INTERVAL = 0.2
    RECONNECT_DELAY = 3
    SOCKET_TIMEOUT = 10
    BUFFER_SIZE = 255

    def __init__(self, settings: Settings, model_path: Path):
        self._settings = settings
        self._model = load_model(str(model_path))
        self._camera: CameraSource = create_camera(settings, settings.server_ip)
        self._lock = asyncio.Lock()
        self._running = False

    async def _send(self, sock: socket.socket, msg: str) -> None:
        data = format_message(msg)
        logger.debug("Send: %s", data)
        loop = asyncio.get_running_loop()
        async with self._lock:
            with contextlib.suppress(OSError):  # send fails on disconnect — reader detects it
                await loop.sock_sendall(sock, data)

    async def _send_message(self, sock: socket.socket, message: str) -> None:
        await self._send(sock, f"data:{message}")

    def _predict(self) -> str:
        im = self._camera.capture()
        if im is None:
            return "-1"
        return self._model.predict(im).prediction

    async def _keepalive_loop(self, sock: socket.socket) -> None:
        while self._running:
            await self._send(sock, "keepalive")
            await asyncio.sleep(self.KEEPALIVE_INTERVAL)

    async def _prediction_loop(self, sock: socket.socket) -> None:
        while self._running:
            prediction = await asyncio.to_thread(self._predict)
            await self._send_message(sock, prediction)
            await asyncio.sleep(self.PREDICTION_INTERVAL)

    async def _reader(self, sock: socket.socket) -> None:
        data = ""
        while self._running and not is_quit_command(data):
            try:
                raw = await asyncio.get_running_loop().sock_recv(sock, self.BUFFER_SIZE)
            except (OSError, ConnectionResetError):
                await asyncio.sleep(0.1)
                continue
            if not raw:
                break
            data = raw.decode("utf-8")
            if data:
                logger.debug("Received: %s", data)
            await asyncio.sleep(0)
        self._running = False

    async def _handle_connection(self, sock: socket.socket) -> None:
        _ip, port = sock.getsockname()
        hull = self._settings.my_hull_number
        await self._send(sock, make_command("register", port, hull))
        await self._send(sock, make_command("self", hull))

        tasks = [
            asyncio.create_task(self._keepalive_loop(sock)),
            asyncio.create_task(self._prediction_loop(sock)),
            asyncio.create_task(self._reader(sock)),
        ]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

    async def _connect_once(self) -> socket.socket:
        sock = socket.socket()
        sock.settimeout(self.SOCKET_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.connect((self._settings.server_ip, self._settings.server_port))
        sock.setblocking(False)
        return sock

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            sock: socket.socket | None = None
            try:
                logger.info(
                    "Connecting to %s:%s",
                    self._settings.server_ip,
                    self._settings.server_port,
                )
                sock = await self._connect_once()
                logger.info("Connected")
                await self._handle_connection(sock)
            except Exception:  # intentional: stay alive through any failure
                logger.exception("Connection error")
            finally:
                if sock is not None:
                    sock.close()
            if self._running:
                logger.info("Reconnecting in %s seconds...", self.RECONNECT_DELAY)
                await asyncio.sleep(self.RECONNECT_DELAY)

    def shutdown(self) -> None:
        self._running = False

    def close(self) -> None:
        self._camera.release()
