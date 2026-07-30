from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from pathlib import Path

from lobe_server.camera import CameraSource, create_camera
from lobe_server.config import Settings
from lobe_server.model import load_model
from lobe_server.protocol import format_message, is_quit_command, make_command, try_parse_message

logger = logging.getLogger(__name__)


class LobeServer:
    KEEPALIVE_INTERVAL = 5
    PREDICTION_INTERVAL = 0.2
    RECONNECT_DELAY = 3
    SOCKET_TIMEOUT = 10
    BUFFER_SIZE = 255
    RECV_TIMEOUT = 10  # robot sends keepalive every 3s; 10s = 3 missed + margin
    CONNECTION_RETRY_DELAY = 0.1

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
            with contextlib.suppress(OSError):  # intentional: _reader is the sole health monitor
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
        buf = b""  # accumulates across recv (TCP is a stream, messages split at any byte)
        while self._running:
            try:
                raw = await asyncio.wait_for(
                    asyncio.get_running_loop().sock_recv(sock, self.BUFFER_SIZE),
                    timeout=self.RECV_TIMEOUT,
                )
                if not raw:
                    logger.info("Peer closed connection")
                    break
                buf += raw
            except TimeoutError:
                logger.warning(
                    "No data from peer in %ss, reconnecting...",
                    self.RECV_TIMEOUT,
                )
                break
            except (OSError, ConnectionResetError):
                await asyncio.sleep(self.CONNECTION_RETRY_DELAY)
                continue
            while self._running:
                ok, msg, rest = try_parse_message(buf)
                if not ok:
                    break
                buf = rest
                if is_quit_command(msg):
                    self._running = False
                    return
                if msg:
                    logger.debug("Received: %s", msg)
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
        sock.connect((self._settings.server_ip, self._settings.server_port))
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
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
            except Exception:
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
