"""Typed runtime settings.

Sources, highest priority first:
1. Process environment variables.
2. The private env file (default ``%LOCALAPPDATA%\\EngineerTestsGTA\\private.env``,
   override with ``GTA_LAB_ENV_FILE``). It lives outside the repo and outside OneDrive.
3. Defaults below.

The repo-level ``.env`` is deliberately NOT read: the repo sits in a OneDrive-synced
folder, and a key there would be uploaded to the cloud.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR_NAME = "EngineerTestsGTA"
ENV_FILE_VAR = "GTA_LAB_ENV_FILE"
LOOPBACK_NAMES = {"localhost"}

Mode = Literal["demo", "live"]


def default_app_home() -> Path:
    """Per-user, non-synced app folder (``%LOCALAPPDATA%\\EngineerTestsGTA`` on Windows)."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / ".engineer-tests-gta"


def default_env_file() -> Path:
    override = os.environ.get(ENV_FILE_VAR)
    if override:
        return Path(override).expanduser()
    return default_app_home() / "private.env"


def is_loopback_host(host: str) -> bool:
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def looks_cloud_synced(path: Path) -> bool:
    """True when the path sits under OneDrive (sync can corrupt SQLite WAL files)."""
    resolved = path.expanduser().resolve(strict=False)
    roots = [
        os.environ.get(name) for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
    ]
    for root in filter(None, roots):
        try:
            resolved.relative_to(Path(root).resolve(strict=False))
            return True
        except ValueError:
            continue
    return any(part.lower().startswith("onedrive") for part in resolved.parts)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GTA_LAB_",
        extra="ignore",
        frozen=True,
        env_file_encoding="utf-8",
    )

    mode: Mode = Field(
        default="demo",
        description="demo = fixture data only, never touches the network. live = real API data.",
    )
    data_dir: Path = Field(default_factory=lambda: default_app_home() / "data")
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    frontend_dist: Path | None = Field(
        default=None, description="Built UI folder; defaults to <repo>/frontend/dist."
    )
    youtube_api_key: SecretStr | None = Field(
        default=None, validation_alias="YOUTUBE_API_KEY", repr=False
    )

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if not is_loopback_host(value):
            raise ValueError("the local app binds to loopback only (127.0.0.1, ::1 or localhost)")
        return value

    @field_validator("data_dir", "frontend_dist")
    @classmethod
    def _expand(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None

    @field_validator("youtube_api_key")
    @classmethod
    def _blank_is_missing(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            return None
        return value

    # ---- derived paths (fixture and live data never share a database) ----
    @property
    def demo_db_path(self) -> Path:
        return self.data_dir / "demo" / "gta_lab_demo.sqlite3"

    @property
    def live_db_path(self) -> Path:
        return self.data_dir / "live" / "gta_lab_live.sqlite3"

    @property
    def active_db_path(self) -> Path:
        return self.live_db_path if self.mode == "live" else self.demo_db_path

    @property
    def youtube_key_configured(self) -> bool:
        return self.youtube_api_key is not None

    def resolved_frontend_dist(self) -> Path:
        if self.frontend_dist is not None:
            return self.frontend_dist
        return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def load_settings(**overrides: object) -> Settings:
    """Build settings from env + the private env file (if it exists) + overrides."""
    env_file = default_env_file()
    kwargs: dict[str, object] = dict(overrides)
    if env_file.is_file():
        kwargs["_env_file"] = env_file
    return Settings(**kwargs)  # type: ignore[arg-type]
