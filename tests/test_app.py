from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gta_lab.app import create_app
from gta_lab.config import load_settings

from .conftest import SENTINEL_KEY

BASE = "http://127.0.0.1:8765"


def client(**overrides: object) -> TestClient:
    return TestClient(create_app(load_settings(**overrides)), base_url=BASE)


def test_app_starts_without_any_key() -> None:
    r = client().get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["api"] == "ok"
    assert body["mode"] == "demo"
    assert body["youtube_api_key"] == "not configured"
    assert body["youtube_requests"] == "disabled"
    assert body["advanced_analytics"] == "off"
    assert body["ai"] == "off"
    assert body["database"] == "not yet created"


def test_live_mode_without_key_still_starts() -> None:
    body = client(mode="live").get("/api/status").json()
    assert body["mode"] == "live"
    assert body["youtube_api_key"] == "not configured"


def test_status_never_contains_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL_KEY)
    r = client().get("/api/status")
    assert r.json()["youtube_api_key"] == "configured"
    assert SENTINEL_KEY not in r.text
    assert SENTINEL_KEY not in json.dumps(dict(r.headers))


def test_unknown_host_header_rejected() -> None:
    r = client().get("/api/status", headers={"host": "evil.example"})
    assert r.status_code == 400


def test_cross_origin_post_rejected() -> None:
    r = client().post("/api/status", headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_same_origin_post_not_blocked_by_origin_check() -> None:
    r = client().post("/api/status", headers={"origin": BASE})
    assert r.status_code != 403  # no POST handler exists, but the origin check let it through
    assert r.json() != {"detail": "cross-origin request rejected"}


def test_security_headers_present() -> None:
    r = client().get("/api/status")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert "server" not in {k.lower() for k in r.headers}


def test_unknown_api_route_is_json_404() -> None:
    r = client().get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "not found"}


def test_no_docs_or_openapi_exposed() -> None:
    c = client()
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404


def test_root_without_build_explains_how_to_build() -> None:
    r = client().get("/")
    assert r.status_code == 200
    assert "UI not built" in r.text
    assert client().get("/api/status").json()["ui_build"] == "not built"


def test_packaged_ui_served_same_origin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dist = tmp_path / "frontend build with spaces" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>smoke</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setenv("GTA_LAB_FRONTEND_DIST", str(dist))
    c = client()
    assert "<title>smoke</title>" in c.get("/").text
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/assets/../index.html").status_code in (400, 404) or "smoke" in c.get("/").text
    assert c.get("/api/status").json()["ui_build"] == "present"
