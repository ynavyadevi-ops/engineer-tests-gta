"""Test isolation: no real env, no private env file, no network."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from gta_lab.config import is_loopback_host

# Synthetic sentinel, not a real key. Tests assert it never leaks.
SENTINEL_KEY = "SENTINEL-not-a-real-key-7f3a9c"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in list(os.environ):
        if name.startswith("GTA_LAB_") or name == "YOUTUBE_API_KEY":
            monkeypatch.delenv(name, raising=False)
    home = tmp_path / "app home with spaces"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local app data"))
    monkeypatch.setenv("GTA_LAB_ENV_FILE", str(home / "private.env"))
    monkeypatch.setenv("GTA_LAB_DATA_DIR", str(home / "data dir"))
    monkeypatch.setenv("GTA_LAB_FRONTEND_DIST", str(tmp_path / "no dist here"))
    return home


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any non-loopback connection fails the test (no YouTube or cloud calls).

    Loopback stays allowed: asyncio on Windows builds its self-pipe from a local socket pair.
    """
    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: object) -> None:
        host = address[0] if isinstance(address, tuple) else address
        if not (isinstance(host, str) and is_loopback_host(host)):
            raise AssertionError(f"network access attempted during tests: {host!r}")
        real_connect(self, address)  # type: ignore[arg-type]

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access attempted during tests")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
