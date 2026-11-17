"""Secret redaction: the key never reaches logs, exceptions, reprs, results or CLI output."""

from __future__ import annotations

import json
import logging
import traceback

import pytest

from gta_lab.__main__ import main
from gta_lab.youtube import YouTubeError, redact
from gta_lab.youtube import smoke as smoke_mod
from gta_lab.youtube.smoke import run_smoke

from .youtube_fakes import (
    SENTINEL_KEY,
    FakeTransport,
    TransportFailure,
    api_error,
    make_client,
    ok,
    vid,
    video_item,
)


def test_redact_helper() -> None:
    text = f"GET https://x/videos?id=1&key={SENTINEL_KEY}&fields=a and AIza{'B' * 35}"
    out = redact(text, SENTINEL_KEY)
    assert SENTINEL_KEY not in out and "AIza" not in out
    assert "key=[REDACTED]" in out
    assert redact("key=abc123&x=1") == "key=[REDACTED]&x=1"


def test_key_is_sent_only_in_the_request_url() -> None:
    t = FakeTransport(ok({"items": []}))
    client, _ = make_client(t)
    client.videos([vid(1)])
    assert t.params()["key"] == [SENTINEL_KEY]
    assert SENTINEL_KEY not in repr(client) and SENTINEL_KEY not in str(vars(client))


ERROR_CASES = [
    api_error(
        400, "badRequest", info="API_KEY_INVALID", message=f"API key not valid: {SENTINEL_KEY}"
    ),
    api_error(403, "quotaExceeded", message=f"quota for key={SENTINEL_KEY}"),
    api_error(403, "forbidden", message=SENTINEL_KEY),
    api_error(404, "videoNotFound", message=SENTINEL_KEY),
    api_error(400, "invalidPageToken", message=SENTINEL_KEY),
    api_error(500, message=SENTINEL_KEY),
    api_error(200 + 302, message=SENTINEL_KEY),
    TransportFailure("timeout"),
]


@pytest.mark.parametrize("failure", ERROR_CASES)
def test_no_key_in_logs_or_exceptions(failure, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    t = FakeTransport(failure, failure, failure, failure)
    client, _ = make_client(t)
    with pytest.raises(YouTubeError) as info:
        client.videos([vid(1)])
    exc = info.value
    rendered = "".join(traceback.format_exception(exc)) + str(exc) + repr(exc)
    rendered += str(vars(exc)) + str(exc.args)
    assert SENTINEL_KEY not in rendered
    assert "googleapis.com" not in str(exc)  # no URL in the message
    assert SENTINEL_KEY not in caplog.text
    assert "googleapis.com" not in caplog.text
    assert caplog.records, "each attempt is logged (method/status/attempt only)"


def test_paged_and_smoke_results_carry_no_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    t = FakeTransport(
        ok({"items": [{"id": {"videoId": vid(i)}} for i in range(1, 6)]}),
        ok({"items": [video_item(vid(i)) for i in range(1, 5)]}),
    )
    client, _ = make_client(t)
    report = run_smoke(client, 5, "gta story")
    dumped = json.dumps(report)
    assert SENTINEL_KEY not in dumped and SENTINEL_KEY not in caplog.text
    # Counts only: no IDs or titles in the report.
    assert vid(1) not in dumped and "Synthetic title" not in dumped
    assert report["search"]["ids_returned"] == 5
    assert report["videos"]["returned"] == 4 and report["videos"]["not_returned"] == 1
    assert report["quota"]["used"] == {"search": 1, "units": 1}


def test_cli_smoke_without_key_is_blocked(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setenv("GTA_LAB_ENV_FILE", str(tmp_path / "none.env"))
    assert main(["youtube", "smoke", "--max-videos", "5"]) == 3
    out = json.loads(capsys.readouterr().out)
    assert out["blocked"] == "YOUTUBE_API_KEY not configured"


def test_cli_dry_run_sends_nothing(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL_KEY)
    monkeypatch.setenv("GTA_LAB_ENV_FILE", str(tmp_path / "none.env"))

    def boom(*_a, **_k):
        raise AssertionError("dry run must not build a client")

    monkeypatch.setattr(smoke_mod, "run_smoke_safely", boom)
    assert main(["youtube", "smoke", "--dry-run", "--max-videos", "15"]) == 0
    out = capsys.readouterr().out
    assert SENTINEL_KEY not in out
    assert json.loads(out)["estimate"] == {
        "search_bucket": 1,
        "units_bucket": 1,
        "requests": {"search.list": 1, "videos.list": 1},
    }


@pytest.mark.parametrize("size", ["4", "16"])
def test_cli_smoke_size_bounds(size, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GTA_LAB_ENV_FILE", str(tmp_path / "none.env"))
    assert main(["youtube", "smoke", "--dry-run", "--max-videos", size]) == 2


def test_cli_smoke_bad_key_stops_cleanly_without_leaking(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", SENTINEL_KEY)
    monkeypatch.setenv("GTA_LAB_ENV_FILE", str(tmp_path / "none.env"))
    t = FakeTransport(api_error(400, "badRequest", info="API_KEY_INVALID", message=SENTINEL_KEY))
    real_client = smoke_mod.YouTubeClient
    monkeypatch.setattr(
        smoke_mod, "YouTubeClient", lambda key, ledger: real_client(key, ledger, transport=t)
    )
    assert main(["youtube", "smoke", "--max-videos", "5"]) == 4
    captured = capsys.readouterr()
    assert SENTINEL_KEY not in captured.out + captured.err
    out = json.loads(captured.out)
    assert out["search"]["stop_kind"] == "bad_key"
