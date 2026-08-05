# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

import asyncio
import socket
from collections.abc import Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lobe_server.config import Settings
from lobe_server.server import LobeServer

_SockPair = tuple[socket.socket, socket.socket]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        server_ip="127.0.0.1",
        my_hull_number=3,
        server_port=8889,
    )


@pytest.fixture
def mock_model() -> MagicMock:
    model = MagicMock()
    prediction = MagicMock()
    prediction.prediction = "cat"
    model.predict.return_value = prediction
    return model


@pytest.fixture
def mock_camera() -> MagicMock:
    cam = MagicMock()
    im = MagicMock()
    cam.capture.return_value = im
    return cam


@pytest.fixture
def real_sock_pair() -> _SockPair:
    a, b = socket.socketpair()
    a.setblocking(False)  # noqa: FBT003
    b.setblocking(False)  # noqa: FBT003
    return a, b


def _make_server(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> LobeServer:
    with (
        patch("lobe_server.server.load_model", return_value=mock_model),
        patch("lobe_server.server.create_camera", return_value=mock_camera),
    ):
        return LobeServer(settings, MagicMock())


@pytest.fixture
def server(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> LobeServer:
    return _make_server(settings, mock_model, mock_camera)


@pytest.fixture
def running_server(server: LobeServer) -> LobeServer:
    server._running = True
    return server


def _reader_sock(data: Any) -> MagicMock:
    """Mock socket whose reads come from a stubbed loop.sock_recv (bytes → value, else side_effect)."""
    sock = MagicMock()
    loop = asyncio.get_running_loop()
    if isinstance(data, bytes):
        loop.sock_recv = AsyncMock(return_value=data)
    else:
        loop.sock_recv = AsyncMock(side_effect=data)
    return sock


async def _run_with_timeout(server: LobeServer, coro: Coroutine[Any, Any, object], seconds: float = 0.5) -> None:
    """Run coro until it finishes or `seconds` elapse (then stop the server)."""

    async def stop_after() -> None:
        await asyncio.sleep(seconds)
        server._running = False

    await asyncio.wait(
        [asyncio.create_task(coro), asyncio.create_task(stop_after())],
        return_when=asyncio.FIRST_COMPLETED,
    )


@pytest.mark.asyncio
async def test_send_format(server: LobeServer, real_sock_pair: _SockPair) -> None:
    sock, reader = real_sock_pair
    await server._send(sock, "hello")
    data = await asyncio.get_running_loop().sock_recv(reader, 255)
    assert data == b"5:hello"


@pytest.mark.asyncio
async def test_send_message(server: LobeServer, real_sock_pair: _SockPair) -> None:
    sock, reader = real_sock_pair
    await server._send_message(sock, "cat")
    data = await asyncio.get_running_loop().sock_recv(reader, 255)
    assert data == b"8:data:cat"


@pytest.mark.asyncio
async def test_send_oserror(server: LobeServer, real_sock_pair: _SockPair) -> None:
    sock, reader = real_sock_pair
    reader.close()
    await server._send(sock, "hello")


def test_predict(server: LobeServer, mock_camera: MagicMock, mock_model: MagicMock) -> None:
    result = server._predict()
    assert result == "cat"
    mock_camera.capture.assert_called_once()
    mock_model.predict.assert_called_once()


def test_predict_none(server: LobeServer, mock_camera: MagicMock, mock_model: MagicMock) -> None:
    mock_camera.capture.return_value = None
    result = server._predict()
    assert result == "-1"
    mock_model.predict.assert_not_called()


def test_shutdown(server: LobeServer) -> None:
    assert server._running is False
    server._running = True
    server.shutdown()
    assert server._running is False


def test_close(server: LobeServer, mock_camera: MagicMock) -> None:
    server.close()
    mock_camera.release.assert_called_once()


@pytest.mark.parametrize(
    ("recv", "race", "final_running"),
    [
        pytest.param(b"9:data:quit", False, False, id="quit"),
        pytest.param(b"", False, True, id="empty-recv"),
        pytest.param(TimeoutError, False, True, id="timeout"),
        pytest.param(ConnectionResetError, False, True, id="connection-reset"),
        pytest.param(b"9:keepalive", True, False, id="keepalive"),
        pytest.param(b"some garbage", True, False, id="garbage"),
        pytest.param(b"8:data:cat", True, False, id="parsed-message"),
        pytest.param(b"8:data:cat9:data:quit", False, False, id="multi-then-quit"),
        pytest.param([b"9:data:q", b"uit"], False, False, id="partial-then-complete"),
    ],
)
@pytest.mark.asyncio
async def test_reader_behavior(
    running_server: LobeServer,
    recv: Any,
    race: bool,  # noqa: FBT001
    final_running: bool,  # noqa: FBT001
) -> None:
    sock = _reader_sock(recv)
    if race:
        await _run_with_timeout(running_server, running_server._reader(sock))
    else:
        await running_server._reader(sock)
    assert running_server._running is final_running


@pytest.mark.asyncio
async def test_reader_oserror_transient_recovers(running_server: LobeServer) -> None:
    calls = {"n": 0}

    def _recv(*_: Any) -> bytes:
        calls["n"] += 1
        if calls["n"] == 1:
            err = "transient"
            raise OSError(err)
        return b"9:keepalive"

    task = asyncio.create_task(running_server._reader(_reader_sock(_recv)))
    await asyncio.sleep(0.2)
    assert not task.done()
    running_server._running = False
    await task


@pytest.mark.asyncio
async def test_reader_oserror_exhausts_retries(running_server: LobeServer) -> None:
    def _recv(*_: Any) -> bytes:
        err = "fatal"
        raise OSError(err)

    await running_server._reader(_reader_sock(_recv))
    assert running_server._running is True


@pytest.mark.asyncio
async def test_keepalive_loop(running_server: LobeServer, real_sock_pair: _SockPair) -> None:
    sock, reader = real_sock_pair
    await _run_with_timeout(running_server, running_server._keepalive_loop(sock), seconds=0.1)
    data = await asyncio.get_running_loop().sock_recv(reader, 255)
    assert data == b"9:keepalive"


@pytest.mark.asyncio
async def test_prediction_loop(running_server: LobeServer, real_sock_pair: _SockPair) -> None:
    sock, reader = real_sock_pair
    await _run_with_timeout(running_server, running_server._prediction_loop(sock), seconds=0.1)
    data = await asyncio.get_running_loop().sock_recv(reader, 255)
    assert data == b"8:data:cat"


@pytest.mark.asyncio
async def test_handle_connection(running_server: LobeServer, real_sock_pair: _SockPair) -> None:
    sock, reader = real_sock_pair

    async def send_quit() -> None:
        await asyncio.sleep(0.1)
        await asyncio.get_running_loop().sock_sendall(reader, b"9:data:quit")

    await asyncio.wait(
        [asyncio.create_task(running_server._handle_connection(sock)), asyncio.create_task(send_quit())],
        return_when=asyncio.FIRST_COMPLETED,
    )
    running_server._running = False


def test_load_model(settings: Settings) -> None:
    mock_img_model = MagicMock()

    with patch("lobe_server.server.load_model", return_value=mock_img_model):
        server = _make_server(settings, mock_img_model, MagicMock())
    assert server._model is mock_img_model


@pytest.mark.asyncio
async def test_connect_once(server: LobeServer) -> None:
    mock_sock = MagicMock()
    mock_loop = MagicMock()
    mock_loop.sock_connect = AsyncMock()

    with (
        patch("lobe_server.server.socket.socket", return_value=mock_sock),
        patch("lobe_server.server.asyncio.get_running_loop", return_value=mock_loop),
    ):
        result = await server._connect_once()

    assert result is mock_sock
    mock_sock.setblocking.assert_called_once_with(False)  # noqa: FBT003
    mock_loop.sock_connect.assert_called_once_with(
        mock_sock,
        (server._settings.server_ip, server._settings.server_port),
    )


@pytest.mark.asyncio
async def test_run_forever_connect_failure(server: LobeServer) -> None:
    with patch(
        "lobe_server.server.LobeServer._connect_once",
        side_effect=ConnectionRefusedError,
    ):

        async def stop_on_reconnect(*_: Any) -> None:
            server.shutdown()

        with patch("asyncio.sleep", stop_on_reconnect):
            await server.run_forever()
    assert server._running is False


@pytest.mark.asyncio
async def test_run_forever_success(server: LobeServer) -> None:
    mock_sock = MagicMock()

    async def handle_and_stop(_sock: socket.socket) -> None:
        server._running = False

    with (
        patch.object(server, "_connect_once", return_value=mock_sock),
        patch.object(server, "_handle_connection", side_effect=handle_and_stop),
    ):
        await server.run_forever()

    mock_sock.close.assert_called()


@pytest.mark.asyncio
async def test_run_forever_reconnects_after_reader_break(server: LobeServer) -> None:
    calls = {"n": 0}

    def handle_and_stop(_sock: socket.socket) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            server.shutdown()

    with (
        patch.object(server, "_connect_once", return_value=MagicMock()),
        patch.object(server, "_handle_connection", side_effect=handle_and_stop),
        patch("lobe_server.server.asyncio.sleep", AsyncMock()),
    ):
        await server.run_forever()

    assert calls["n"] == 2
    assert server._running is False


@pytest.mark.asyncio
async def test_run_forever_does_not_swallow_keyboardinterrupt(server: LobeServer) -> None:
    with (
        patch.object(server, "_connect_once", return_value=MagicMock()),
        patch.object(server, "_handle_connection", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        await server.run_forever()


@pytest.mark.asyncio
async def test_handle_connection_cancels_pending(
    settings: Settings,
    mock_model: MagicMock,
    real_sock_pair: _SockPair,
) -> None:
    import threading  # noqa: PLC0415

    sock, reader = real_sock_pair

    block = threading.Event()
    mock_camera = MagicMock()
    mock_camera.capture.side_effect = lambda: (block.wait(10), None)[1]

    server = _make_server(settings, mock_model, mock_camera)
    server._running = True

    async def send_quit() -> None:
        await asyncio.sleep(0.1)
        await asyncio.get_running_loop().sock_sendall(reader, b"9:data:quit")

    asyncio.create_task(send_quit())  # noqa: RUF006
    before = set(asyncio.all_tasks())
    with patch.object(socket.socket, "getsockname", return_value=("127.0.0.1", 8889)):
        await server._handle_connection(sock)
    leftover = set(asyncio.all_tasks()) - before
    assert not leftover  # child tasks are cancelled AND awaited before returning

    server._running = False
    block.set()
