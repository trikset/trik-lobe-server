def format_message(msg: str) -> bytes:
    return bytes(f"{len(msg)}:{msg}", encoding="UTF-8")


def make_command(cmd: str, *args: str | int) -> str:
    return f"{cmd}:" + ":".join(str(a) for a in args)


def try_parse_message(buf: str) -> tuple[bool, str, str]:
    if ":" not in buf:
        return False, "", buf
    prefix, _, rest = buf.partition(":")
    if not prefix.isdigit():
        return False, "", buf
    length = int(prefix)
    if len(rest) < length:
        return False, "", buf
    return True, rest[:length], rest[length:]


def is_quit_command(msg: str) -> bool:
    return msg == "data:quit"
