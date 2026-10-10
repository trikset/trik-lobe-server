#!/usr/bin/env python3
"""
gate.py — canonical local quality gate for trik-lobe-server.

Runs all checks in the required order (ruff -> basedpyright -> pylint ->
bandit -> vulture -> pytest). Exits on first failure.

Usage:  cd /project/root && uv run python scripts/gate.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS: list[tuple[str, list[str]]] = [
    ("ruff", ["uv", "run", "ruff", "check", "."]),
    ("basedpyright", ["uv", "run", "basedpyright", "."]),
    ("pylint", ["uv", "run", "pylint", "lobe_server", "TRIKLobeServer.py", "tests"]),
    ("bandit", ["uv", "run", "bandit", "--recursive", "lobe_server/", "TRIKLobeServer.py"]),
    ("vulture", ["uv", "run", "vulture", "lobe_server/", "tests/", "TRIKLobeServer.py"]),
    ("pytest", ["uv", "run", "pytest", "-q", "--cov", "--cov-fail-under=100"]),
]


def main() -> int:
    for name, cmd in STEPS:
        print(f"=== {name} ===")
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            print(f"FAIL: {name} exited with code {result.returncode}")
            return 1
    print("All gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())