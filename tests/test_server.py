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


@pytest.fixture(params=["cat"])
def mock_model(request) -> MagicMock:
    model = MagicMock()
    prediction = MagicMock()
    prediction.prediction = request.param
    model.predict.return_value = prediction
    return model


@pytest.fixture
def mock_camera() -> MagicMock:
    cam = MagicMock()
    im = MagicMock()
    cam.capture.return_value = im
    return cam


def _make_server(settings, mock_model, mock_camera):
    with (
        patch("lobe_server.server._load_model", return_value=mock_model),
        patch("lobe_server.server.create_camera", return_value=mock_camera),
    ):
        return LobeServer(settings, MagicMock())


@pytest.mark.asyncio
async def test_send_format(settings, mock_model, mock_camera) -> None:
    sock = AsyncMock()
    sock.send = MagicMock()

    server = _make_server(settings, mock_model, mock_camera)
    await server._send(sock, "hello")
    sock.send.assert_called_once_with(b"5:hello")


@pytest.mark.asyncio
async def test_send_message(settings, mock_model, mock_camera) -> None:
    sock = AsyncMock()
    sock.send = MagicMock()

    server = _make_server(settings, mock_model, mock_camera)
    await server._send_message(sock, "cat")
    sock.send.assert_called_once_with(b"8:data:cat")


def test_predict(settings, mock_model, mock_camera) -> None:
    server = _make_server(settings, mock_model, mock_camera)
    result = server._predict()
    assert result == "cat"
    mock_camera.capture.assert_called_once()
    mock_model.predict.assert_called_once()


def test_predict_none(settings, mock_model, mock_camera) -> None:
    mock_camera.capture.return_value = None

    server = _make_server(settings, mock_model, mock_camera)
    result = server._predict()
    assert result == "-1"
    mock_model.predict.assert_not_called()


@pytest.mark.asyncio
async def test_reader_quit(settings, mock_model, mock_camera) -> None:
    sock = MagicMock()
    loop = asyncio.get_event_loop()
    loop.sock_recv = AsyncMock(return_value=b"9:data:quit")

    server = _make_server(settings, mock_model, mock_camera)
    server._running = True
    await server._reader(sock)
    assert server._running is False


@pytest.mark.asyncio
async def test_reader_ignore_garbage(settings, mock_model, mock_camera) -> None:
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
