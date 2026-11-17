"""CLI: ``python -m gta_lab serve`` and ``python -m gta_lab config``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from . import __version__
from .config import Settings, default_env_file, load_settings, looks_cloud_synced


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gta_lab", description="Engineer Tests GTA (local)")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the local app on 127.0.0.1")
    serve.add_argument("--mode", choices=["demo", "live"], help="overrides GTA_LAB_MODE")
    serve.add_argument("--port", type=int, help="overrides GTA_LAB_PORT")
    serve.add_argument("--data-dir", type=Path, help="overrides GTA_LAB_DATA_DIR")
    serve.add_argument("--reload", action="store_true", help="dev auto-reload (backend only)")

    sub.add_parser("config", help="print effective non-secret settings as JSON")

    db = sub.add_parser("db", help="local database maintenance (migrate, status, purge)")
    db.add_argument("action", choices=["migrate", "status", "purge"])
    db.add_argument("--mode", choices=["demo", "live"], help="overrides GTA_LAB_MODE")
    db.add_argument("--data-dir", type=Path, help="overrides GTA_LAB_DATA_DIR")
    return parser


def _db_command(action: str, settings: Settings) -> int:
    from .db import open_for_settings, purge_expired
    from .db.health import read_health

    path = settings.active_db_path
    if action == "status":
        print(json.dumps({"db_path": str(path), "health": read_health(path)}, indent=2))
        return 0
    try:
        db = open_for_settings(settings)
    except Exception as exc:  # report and exit nonzero; never a traceback with data
        print(f"db error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    with db:
        if action == "migrate":
            print(
                json.dumps(
                    {
                        "db_path": str(path),
                        "dataset": db.dataset,
                        "applied": list(db.migration.applied),
                        "schema_version": db.schema_version(),
                    },
                    indent=2,
                )
            )
        else:  # purge
            report = purge_expired(db).as_dict()
            print(json.dumps({"db_path": str(path), "purged": report}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    overrides: dict[str, object] = {}
    if getattr(args, "mode", None):
        overrides["mode"] = args.mode
    if getattr(args, "port", None):
        overrides["port"] = args.port
    if getattr(args, "data_dir", None):
        overrides["data_dir"] = args.data_dir

    try:
        settings = load_settings(**overrides)
    except ValidationError as exc:
        # Pydantic hides SecretStr values, but print only field names and messages anyway.
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"])
            print(f"config error: {field}: {err['msg']}", file=sys.stderr)
        return 2

    if args.command == "db":
        return _db_command(args.action, settings)

    if args.command == "config":
        print(
            json.dumps(
                {
                    "mode": settings.mode,
                    "host": settings.host,
                    "port": settings.port,
                    "data_dir": str(settings.data_dir),
                    "data_dir_cloud_synced": looks_cloud_synced(settings.data_dir),
                    "active_db_path": str(settings.active_db_path),
                    "private_env_file": str(default_env_file()),
                    "private_env_file_exists": default_env_file().is_file(),
                    "youtube_api_key": "configured"
                    if settings.youtube_key_configured
                    else "not configured",
                    "frontend_dist": str(settings.resolved_frontend_dist()),
                },
                indent=2,
            )
        )
        return 0

    import os

    import uvicorn

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if looks_cloud_synced(settings.data_dir):
        print(
            "warning: data dir is inside a OneDrive-synced folder; set GTA_LAB_DATA_DIR "
            "to a local path",
            file=sys.stderr,
        )
    print(
        f"Engineer Tests GTA {__version__} [{settings.mode}] -> http://{settings.host}:{settings.port}/"
    )

    if args.reload:
        # The reloader re-imports the app in a child process, so pass CLI overrides via env.
        for key, value in overrides.items():
            os.environ[f"GTA_LAB_{key.upper()}"] = str(value)
        uvicorn.run(
            "gta_lab.app:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
            reload=True,
            reload_dirs=[str(Path(__file__).resolve().parent)],
            server_header=False,
            proxy_headers=False,
        )
    else:
        from .app import create_app

        uvicorn.run(
            create_app(settings),
            host=settings.host,
            port=settings.port,
            server_header=False,
            proxy_headers=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
