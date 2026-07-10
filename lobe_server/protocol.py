def format_message(msg: str) -> bytes:
    return bytes(f"{len(msg)}:{msg}", encoding="UTF-8")


def make_command(cmd: str, *args) -> str:
    return f"{cmd}:" + ":".join(str(a) for a in args)


def is_quit_command(data: str) -> bool:
    return "9:data:quit" in data
