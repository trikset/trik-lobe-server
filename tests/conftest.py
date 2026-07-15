import socket
from unittest.mock import MagicMock

import pytest

from lobe_server.config import Settings

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
    a.setblocking(False)
    b.setblocking(False)
    return a, b
