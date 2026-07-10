import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lobe_server.config import Settings
from lobe_server.server import LobeServer


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


def _make_server(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> LobeServer:
    with (
        patch("lobe_server.server._load_model", return_value=mock_model),
        patch("lobe_server.server.create_camera", return_value=mock_camera),
    ):
        return LobeServer(settings, MagicMock())


@pytest.mark.asyncio
async def test_send_format(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = AsyncMock()
    sock.send = MagicMock()

    server = _make_server(settings, mock_model, mock_camera)
    await server._send(sock, "hello")
    sock.send.assert_called_once_with(b"5:hello")


@pytest.mark.asyncio
async def test_send_message(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = AsyncMock()
    sock.send = MagicMock()

    server = _make_server(settings, mock_model, mock_camera)
    await server._send_message(sock, "cat")
    sock.send.assert_called_once_with(b"8:data:cat")


@pytest.mark.asyncio
async def test_send_oserror(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = AsyncMock()
    sock.send.side_effect = OSError("broken")

    server = _make_server(settings, mock_model, mock_camera)
    await server._send(sock, "hello")


def test_predict(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    server = _make_server(settings, mock_model, mock_camera)
    result = server._predict()
    assert result == "cat"
    mock_camera.capture.assert_called_once()
    mock_model.predict.assert_called_once()


def test_predict_none(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    mock_camera.capture.return_value = None

    server = _make_server(settings, mock_model, mock_camera)
    result = server._predict()
    assert result == "-1"
    mock_model.predict.assert_not_called()


def test_shutdown(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    server = _make_server(settings, mock_model, mock_camera)
    assert server._running is False
    server._running = True
    server.shutdown()
    assert server._running is False


def test_close(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    server = _make_server(settings, mock_model, mock_camera)
    server.close()
    mock_camera.release.assert_called_once()


@pytest.mark.asyncio
async def test_reader_quit(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = MagicMock()
    loop = asyncio.get_event_loop()
    loop.sock_recv = AsyncMock(return_value=b"9:data:quit")

    server = _make_server(settings, mock_model, mock_camera)
    server._running = True
    await server._reader(sock)
    assert server._running is False


@pytest.mark.asyncio
async def test_reader_connection_reset(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = MagicMock()
    loop = asyncio.get_event_loop()
    loop.sock_recv = AsyncMock(side_effect=ConnectionResetError)

    server = _make_server(settings, mock_model, mock_camera)
    server._running = True

    async def stop_after():
        await asyncio.sleep(0.5)
        server._running = False

    await asyncio.wait(
        [
            asyncio.create_task(server._reader(sock)),
            asyncio.create_task(stop_after()),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )


@pytest.mark.asyncio
async def test_reader_ignore_garbage(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = MagicMock()
    loop = asyncio.get_event_loop()
    loop.sock_recv = AsyncMock(return_value=b"some garbage")

    server = _make_server(settings, mock_model, mock_camera)
    server._running = True

    async def stop_after():
        await asyncio.sleep(0.5)
        server._running = False

    await asyncio.wait(
        [
            asyncio.create_task(server._reader(sock)),
            asyncio.create_task(stop_after()),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )


@pytest.mark.asyncio
async def test_keepalive_loop(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = MagicMock()
    sock.send = MagicMock()

    server = _make_server(settings, mock_model, mock_camera)
    server._running = True

    async def stop_after():
        await asyncio.sleep(0.1)
        server._running = False

    await asyncio.wait(
        [
            asyncio.create_task(server._keepalive_loop(sock)),
            asyncio.create_task(stop_after()),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    sock.send.assert_called_once_with(b"9:keepalive")


@pytest.mark.asyncio
async def test_prediction_loop(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = MagicMock()
    sock.send = MagicMock()

    server = _make_server(settings, mock_model, mock_camera)
    server._running = True

    async def stop_after():
        await asyncio.sleep(0.1)
        server._running = False

    await asyncio.wait(
        [
            asyncio.create_task(server._prediction_loop(sock)),
            asyncio.create_task(stop_after()),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    sock.send.assert_called_once_with(b"8:data:cat")


@pytest.mark.asyncio
async def test_handle_connection(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    sock = MagicMock()
    sock.getsockname.return_value = ("127.0.0.1", 54321)
    sock.send = MagicMock()
    loop = asyncio.get_event_loop()
    loop.sock_recv = AsyncMock(return_value=b"9:data:quit")

    server = _make_server(settings, mock_model, mock_camera)
    server._running = True
    await server._handle_connection(sock)

    assert sock.send.call_count >= 2
    calls = sock.send.call_args_list
    assert b"16:register:54321:3" in [c[0][0] for c in calls]
    assert b"6:self:3" in [c[0][0] for c in calls]


def test_load_model() -> None:
    mock_img_model = MagicMock()

    with (
        patch("lobe_server.server.TFLiteImageModel.load", return_value=mock_img_model),
    ):
        from lobe_server.server import _load_model

        result = _load_model(MagicMock())
    assert result is mock_img_model


@pytest.mark.asyncio
async def test_connect_once(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    mock_sock = MagicMock()

    with patch("lobe_server.server.socket.socket", return_value=mock_sock):
        server = _make_server(settings, mock_model, mock_camera)
        result = await server._connect_once()

    assert result is mock_sock
    mock_sock.settimeout.assert_called_once_with(10)
    mock_sock.connect.assert_called_once_with(("127.0.0.1", 8889))


@pytest.mark.asyncio
async def test_run_forever_connect_failure(settings: Settings, mock_model: MagicMock, mock_camera: MagicMock) -> None:
    with patch(
        "lobe_server.server.LobeServer._connect_once",
        side_effect=ConnectionRefusedError,
    ):
        server = _make_server(settings, mock_model, mock_camera)
        await server.run_forever()
    assert server._running is False
