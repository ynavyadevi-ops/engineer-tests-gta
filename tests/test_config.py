from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gta_lab.config import Settings, is_loopback_host, load_settings, looks_cloud_synced

from .conftest import SENTINEL_KEY


def test_defaults_start_in_demo_without_key() -> None:
    s = load_settings()
    assert s.mode == "demo"
    assert s.host == "127.0.0.1"
    assert s.youtube_key_configured is False
    assert s.active_db_path == s.demo_db_path


def test_demo_and_live_databases_are_separate() -> None:
    s = load_settings()
    assert s.demo_db_path != s.live_db_path
    assert s.demo_db_path.parent != s.live_db_path.parent
    assert load_settings(mode="live").active_db_path == s.live_db_path


def test_data_dir_override_with_spaces(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "My Data" / "GTA lab (local)"
    monkeypatch.setenv("GTA_LAB_DATA_DIR", str(target))
    s = load_settings()
    assert s.data_dir == target
    assert s.demo_db_path == target / "demo" / "gta_lab_demo.sqlite3"


def test_default_data_dir_is_under_localappdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GTA_LAB_DATA_DIR")
    s = load_settings()
    assert s.data_dir.parts[-2:] == ("EngineerTestsGTA", "data")


def test_invalid_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTA_LAB_MODE", "production")
    with pytest.raises(ValidationError):
        load_settings()


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com", "::"])
def test_non_loopback_host_rejected(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    monkeypatch.setenv("GTA_LAB_HOST", host)
    with pytest.raises(ValidationError):
        load_settings()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "[::1]", "localhost"])
def test_loopback_hosts_accepted(host: str) -> None:
    assert is_loopback_host(host)


def test_key_from_process_env_is_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL_KEY)
    s = load_settings()
    assert s.youtube_key_configured
    assert SENTINEL_KEY not in repr(s)
    assert SENTINEL_KEY not in str(s.model_dump())


def test_blank_key_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "   ")
    assert load_settings().youtube_key_configured is False


def test_private_env_file_is_read(isolated_env: Path) -> None:
    isolated_env.mkdir(parents=True)
    (isolated_env / "private.env").write_text(
        f"YOUTUBE_API_KEY={SENTINEL_KEY}\nGTA_LAB_MODE=live\n", encoding="utf-8"
    )
    s = load_settings()
    assert s.youtube_key_configured
    assert s.mode == "live"


def test_repo_dotenv_is_not_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"YOUTUBE_API_KEY={SENTINEL_KEY}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert load_settings().youtube_key_configured is False


def test_onedrive_paths_flagged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "OneDrive"
    monkeypatch.setenv("OneDrive", str(root))
    assert looks_cloud_synced(root / "Desktop" / "x")
    assert not looks_cloud_synced(tmp_path / "plain local")


def test_settings_are_immutable() -> None:
    s = Settings()
    with pytest.raises(ValidationError):
        s.mode = "live"  # type: ignore[misc]
