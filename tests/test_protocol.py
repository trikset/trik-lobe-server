# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

import pytest

from lobe_server.protocol import format_message, is_quit_command, make_command, try_parse_message

_KOSHKA = "кошка".encode()


def test_format_message() -> None:
    assert format_message("hello") == b"5:hello"
    assert format_message("") == b"0:"
    assert format_message("data:cat") == b"8:data:cat"


@pytest.mark.parametrize("raw", ["кошка", "café"])
def test_format_message_multibyte(raw: str) -> None:
    data = format_message(raw)
    prefix = f"{len(raw.encode())}:".encode()
    assert data[: len(prefix)] == prefix
    assert data[len(prefix) :].decode("utf-8") == raw


def test_make_command() -> None:
    assert make_command("register", 12345, 2) == "register:12345:2"
    assert make_command("self", 2) == "self:2"
    assert make_command("data", "cat") == "data:cat"


def test_make_and_format() -> None:
    assert format_message(make_command("self", 3)) == b"6:self:3"


def test_is_quit_command() -> None:
    assert is_quit_command("data:quit") is True
    assert is_quit_command("data:keepalive") is False
    assert is_quit_command("") is False
    assert is_quit_command("hello") is False
    assert is_quit_command("9:data:quit") is False


@pytest.mark.parametrize(
    ("data", "msg", "rest"),
    [
        (b"5:hello", "hello", b""),
        (b"5:hello3:cat", "hello", b"3:cat"),
        (b"0:", "", b""),
        (b"5:hello5:world", "hello", b"5:world"),
        (b"10:" + _KOSHKA + b"3:cat", "кошка", b"3:cat"),
    ],
)
def test_try_parse_message_success(data: bytes, msg: str, rest: bytes) -> None:
    ok, parsed, remaining = try_parse_message(data)
    assert ok is True
    assert parsed == msg
    assert remaining == rest


@pytest.mark.parametrize(
    "data",
    [
        b"5:hel",
        b"hello",
        b"abc:hello",
        b"",
        b"10:" + _KOSHKA[:3],
    ],
)
def test_try_parse_message_incomplete(data: bytes) -> None:
    ok, parsed, remaining = try_parse_message(data)
    assert ok is False
    assert parsed == ""
    assert remaining == data


def test_try_parse_message_remaining_chain() -> None:
    data = b"5:hello5:world"
    ok, msg, rest = try_parse_message(data)
    ok, msg, rest = try_parse_message(rest)
    assert (ok, msg, rest) == (True, "world", b"")


def test_try_parse_message_cyrillic_chain() -> None:
    ok, msg, rest = try_parse_message(b"10:" + _KOSHKA + b"3:cat")
    ok, msg, rest = try_parse_message(rest)
    assert (ok, msg, rest) == (True, "cat", b"")
