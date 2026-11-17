from __future__ import annotations

import json

import pytest

from gta_lab.__main__ import main

from .conftest import SENTINEL_KEY


def test_config_command_hides_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL_KEY)
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert SENTINEL_KEY not in out
    data = json.loads(out)
    assert data["youtube_api_key"] == "configured"
    assert data["mode"] == "demo"


def test_bad_config_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GTA_LAB_HOST", "0.0.0.0")
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL_KEY)
    assert main(["config"]) == 2
    captured = capsys.readouterr()
    assert "host" in captured.err
    assert SENTINEL_KEY not in captured.err + captured.out
