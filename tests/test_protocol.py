from lobe_server.protocol import format_message, is_quit_command, make_command


def test_format_message() -> None:
    assert format_message("hello") == b"5:hello"
    assert format_message("") == b"0:"
    assert format_message("data:cat") == b"8:data:cat"


def test_make_command() -> None:
    assert make_command("register", 12345, 2) == "register:12345:2"
    assert make_command("self", 2) == "self:2"
    assert make_command("data", "cat") == "data:cat"


def test_make_and_format() -> None:
    cmd = make_command("self", 3)
    assert format_message(cmd) == b"6:self:3"


def test_is_quit_command() -> None:
    assert is_quit_command("9:data:quit") is True
    assert is_quit_command("9:data:quit\n") is True
    assert is_quit_command("something 9:data:quit else") is True


def test_is_not_quit() -> None:
    assert is_quit_command("9:data:keepalive") is False
    assert is_quit_command("") is False
    assert is_quit_command("hello") is False
