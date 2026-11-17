"""/api/status health counts and the ``db`` CLI (no rows or IDs ever exposed)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gta_lab.__main__ import main
from gta_lab.app import create_app
from gta_lab.clock import SystemClock
from gta_lab.config import load_settings
from gta_lab.db import SourceRepository, open_for_settings

from .db_support import fx, rec

BASE = "http://127.0.0.1:8765"


def test_status_reports_no_health_before_the_db_exists() -> None:
    body = TestClient(create_app(load_settings()), base_url=BASE).get("/api/status").json()
    assert body["database"] == "not yet created"
    assert body["data_health"] is None


def test_status_reports_counts_only_and_does_not_create_files() -> None:
    settings = load_settings()
    with open_for_settings(settings, SystemClock()) as db:
        SourceRepository(db).apply_videos_list([fx(1)], [rec(1)], "fixture")
    r = TestClient(create_app(settings), base_url=BASE).get("/api/status")
    body = r.json()
    assert body["database"] == "present"
    health = body["data_health"]
    assert health["state"] == "ready" and health["dataset"] == "synthetic"
    assert health["schema_version"] == 4
    assert health["videos_fresh"] == 1 and health["capabilities_on"] == 0
    assert "fixture:vid" not in r.text and "Synthetic test video" not in r.text
    # Live DB was never touched by a demo-mode status call.
    assert not load_settings(mode="live").active_db_path.exists()


def test_cli_db_migrate_status_purge(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["db", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["health"] is None

    assert main(["db", "migrate"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] == [1, 2, 3, 4] and out["dataset"] == "synthetic"

    assert main(["db", "migrate"]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] == []

    assert main(["db", "purge"]) == 0
    assert json.loads(capsys.readouterr().out)["purged"]["videos_purged"] == 0

    assert main(["db", "status", "--mode", "live"]) == 0
    assert json.loads(capsys.readouterr().out)["health"] is None


def test_cli_reports_dataset_mismatch_with_nonzero_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = load_settings(mode="live")
    settings.live_db_path.parent.mkdir(parents=True)
    # Put a synthetic DB where the live one belongs: the CLI must refuse it.
    from gta_lab.db import open_database

    open_database(settings.live_db_path, "synthetic").close()
    assert main(["db", "migrate", "--mode", "live"]) == 1
    assert "DatasetMismatchError" in capsys.readouterr().err
