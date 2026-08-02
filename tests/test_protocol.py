# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

from lobe_server.protocol import format_message, is_quit_command, make_command, try_parse_message


def test_format_message() -> None:
    assert format_message("hello") == b"5:hello"
    assert format_message("") == b"0:"
    assert format_message("data:cat") == b"8:data:cat"


def test_format_message_cyrillic() -> None:
    msg = format_message("кошка")
    assert msg[:3] == b"10:"  # "кошка" = 10 bytes UTF-8, 5 chars
    assert msg[3:].decode("utf-8") == "кошка"


def test_format_message_diverse() -> None:
    msg = format_message("café")
    assert msg[:2] == b"5:"  # "café" = 5 bytes UTF-8, 4 chars
    assert msg[2:].decode("utf-8") == "café"


def test_make_command() -> None:
    assert make_command("register", 12345, 2) == "register:12345:2"
    assert make_command("self", 2) == "self:2"
    assert make_command("data", "cat") == "data:cat"


def test_make_and_format() -> None:
    cmd = make_command("self", 3)
    assert format_message(cmd) == b"6:self:3"


def test_is_quit_command() -> None:
    assert is_quit_command("data:quit") is True
    assert is_quit_command("data:keepalive") is False
    assert is_quit_command("") is False
    assert is_quit_command("hello") is False
    assert is_quit_command("9:data:quit") is False


def test_try_parse_message_single() -> None:
    ok, msg, rest = try_parse_message(b"5:hello")
    assert ok is True
    assert msg == "hello"
    assert rest == b""


def test_try_parse_message_multiple() -> None:
    ok, msg, rest = try_parse_message(b"5:hello3:cat")
    assert ok is True
    assert msg == "hello"
    assert rest == b"3:cat"


def test_try_parse_message_partial() -> None:
    ok, msg, rest = try_parse_message(b"5:hel")
    assert ok is False
    assert msg == ""
    assert rest == b"5:hel"


def test_try_parse_message_no_colon() -> None:
    ok, msg, rest = try_parse_message(b"hello")
    assert ok is False
    assert msg == ""
    assert rest == b"hello"


def test_try_parse_message_non_digit_prefix() -> None:
    ok, msg, rest = try_parse_message(b"abc:hello")
    assert ok is False
    assert msg == ""
    assert rest == b"abc:hello"


def test_try_parse_message_empty() -> None:
    ok, msg, rest = try_parse_message(b"")
    assert ok is False
    assert msg == ""
    assert rest == b""


def test_try_parse_message_zero_length() -> None:
    ok, msg, rest = try_parse_message(b"0:")
    assert ok is True
    assert msg == ""
    assert rest == b""


def test_try_parse_message_remaining() -> None:
    ok, msg, rest = try_parse_message(b"5:hello5:world")
    assert ok is True
    assert msg == "hello"
    assert rest == b"5:world"
    ok, msg, rest = try_parse_message(rest)
    assert ok is True
    assert msg == "world"
    assert rest == b""


def test_try_parse_message_cyrillic() -> None:
    data = "кошка".encode()
    msg_bytes = b"10:" + data + b"3:cat"
    ok, msg, rest = try_parse_message(msg_bytes)
    assert ok is True
    assert msg == "кошка"
    assert rest == b"3:cat"
    ok, msg, rest = try_parse_message(rest)
    assert ok is True
    assert msg == "cat"
    assert rest == b""


def test_try_parse_message_cyrillic_partial() -> None:
    data = "кошка".encode()
    msg_bytes = b"10:" + data[:3]
    ok, msg, rest = try_parse_message(msg_bytes)
    assert ok is False
    assert msg == ""
    assert rest == msg_bytes
