"""Local FastAPI app: private localhost API plus the packaged (same-origin) UI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import APP_NAME, __version__
from .config import Settings, load_settings, looks_cloud_synced

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


class StatusResponse(BaseModel):
    """Everything here is safe to show in the browser. Never add secret values."""

    app: str
    version: str
    mode: Literal["demo", "live"]
    api: Literal["ok"]
    youtube_api_key: Literal["configured", "not configured"]
    youtube_requests: Literal["disabled"]
    database: Literal["not yet created", "present"]
    data_dir: str
    data_dir_cloud_synced: bool
    ui_build: Literal["present", "not built"]
    advanced_analytics: Literal["off"]
    ai: Literal["off"]
    server_time_utc: str


def _allowed_hosts(settings: Settings) -> list[str]:
    return ["127.0.0.1", "localhost", "[::1]", "::1", settings.host]


def _allowed_origins(settings: Settings) -> set[str]:
    hosts = ["127.0.0.1", "localhost", "[::1]"]
    ports = [str(settings.port), "5173"]
    return {f"http://{h}:{p}" for h in hosts for p in ports}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title="Engineer Tests GTA (local)",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    allowed_origins = _allowed_origins(settings)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Reject cross-origin state-changing requests (CSRF / DNS-rebinding defence).
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in allowed_origins:
                return JSONResponse({"detail": "cross-origin request rejected"}, status_code=403)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = CSP
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Added last so it runs first: unknown Host headers never reach a handler.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts(settings))

    @app.get("/api/status", response_model=StatusResponse)
    def status() -> StatusResponse:
        dist = settings.resolved_frontend_dist()
        return StatusResponse(
            app=APP_NAME,
            version=__version__,
            mode=settings.mode,
            api="ok",
            youtube_api_key="configured" if settings.youtube_key_configured else "not configured",
            youtube_requests="disabled",
            database="present" if settings.active_db_path.is_file() else "not yet created",
            data_dir=str(settings.data_dir),
            data_dir_cloud_synced=looks_cloud_synced(settings.data_dir),
            ui_build="present" if (dist / "index.html").is_file() else "not built",
            advanced_analytics="off",
            ai="off",
            server_time_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_not_found(rest: str) -> JSONResponse:
        return JSONResponse({"detail": "not found"}, status_code=404)

    _mount_ui(app, settings.resolved_frontend_dist())
    return app


def _mount_ui(app: FastAPI, dist: Path) -> None:
    """Serve the built UI from the same origin as the API (packaged local run)."""
    index = dist / "index.html"
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False, response_model=None)
    def root() -> Response:
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return PlainTextResponse(
            "UI not built. Run scripts\\run.ps1 -Build (packaged) or scripts\\dev.ps1 (dev). "
            "API status: /api/status",
            status_code=200,
        )
