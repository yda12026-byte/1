"""Small standard-library helpers for the project's official HTTPS APIs."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
        if match:
            values[match.group(1)] = match.group(2)
    return {**values, **os.environ}


def open_direct(request: Request, timeout: int = 15):
    """Open an allowlisted HTTPS request without the machine's unavailable proxy."""
    return build_opener(ProxyHandler({})).open(request, timeout=timeout)
