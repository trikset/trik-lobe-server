# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.


def format_message(msg: str) -> bytes:
    data = msg.encode()
    return bytes(f"{len(data)}:", encoding="UTF-8") + data


def make_command(cmd: str, *args: str | int) -> str:
    return f"{cmd}:" + ":".join(str(a) for a in args)


def try_parse_message(buf: bytes) -> tuple[bool, str, bytes]:
    if b":" not in buf:
        return False, "", buf
    prefix, _, rest = buf.partition(b":")
    if not prefix.isdigit():
        return False, "", buf
    length = int(prefix)
    if len(rest) < length:
        return False, "", buf
    return True, rest[:length].decode("utf-8", errors="replace"), rest[length:]


def is_quit_command(msg: str) -> bool:
    return msg == "data:quit"
