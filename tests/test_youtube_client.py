"""Mocked YouTube adapter tests: batching, partial fields, parsing, malformed bodies,
retries, quota buckets, clean stops and resume states. No network is used."""

from __future__ import annotations

import json

import pytest

from gta_lab.youtube import (
    BadKeyError,
    BadRequestError,
    BudgetExhaustedError,
    MalformedResponseError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExhaustedError,
    QuotaLedger,
    TransientError,
    YouTubeClient,
    estimate_hydration,
    estimate_search,
)
from gta_lab.youtube.client import VIDEO_FIELDS
from gta_lab.youtube.quota import METHOD_COST, estimate_uploads
from gta_lab.youtube.transport import API_BASE, HttpResponse, UrllibTransport

from .youtube_fakes import (
    FakeTransport,
    TransportFailure,
    api_error,
    cid,
    make_client,
    ok,
    upl,
    vid,
    video_item,
)

# ---------------------------------------------------------------- videos.list


def test_videos_list_request_shape_and_partial_fields() -> None:
    t = FakeTransport(ok({"items": [video_item(vid(1))]}))
    client, _ = make_client(t)
    client.videos([vid(1), vid(2)])
    assert t.urls[0].startswith(API_BASE + "videos?")
    p = t.params()
    assert p["part"] == ["snippet,contentDetails,statistics,status"]
    assert p["id"] == [f"{vid(1)},{vid(2)}"]
    assert p["fields"] == [VIDEO_FIELDS]
    assert "maxResults" not in p  # not supported together with id
    # Never request descriptions, comments, captions, files or player embeds.
    for forbidden in ("description", "comment", "caption", "fileDetails", "player", "tags"):
        assert forbidden not in p["fields"][0].replace("commentCount", "")
        assert forbidden not in p["part"][0]
    assert t.timeouts == [15.0]


def test_videos_parse_fields_and_missing_metrics_unavailable() -> None:
    hidden = video_item(vid(2), statistics={"viewCount": "5"})  # likes/comments hidden
    no_stats = video_item(vid(3))
    del no_stats["statistics"]
    t = FakeTransport(ok({"items": [video_item(vid(1)), hidden, no_stats]}))
    client, _ = make_client(t)
    page = client.videos([vid(1), vid(2), vid(3)])
    full, part, none = page.records
    assert full.title == f"Synthetic title {vid(1)}"
    assert full.channel_id == cid(1)
    assert full.duration_iso == "PT10M2S"
    assert full.category_id == "20"
    assert full.embeddable is True
    assert full.published_at is not None and full.published_at.tzinfo is not None
    assert full.thumbnail_url.startswith("https://i.ytimg.com/")
    assert full.statistics.view_count == 1000
    assert part.statistics.view_count == 5
    assert part.statistics.like_count is None  # unavailable, never 0
    assert part.statistics.comment_count is None
    assert page.hints[vid(2)].missing_stats == ("likeCount", "commentCount")
    assert none.statistics is None
    assert page.hints[vid(1)].default_audio_language == "en"
    assert full.default_language is None  # only snippet.defaultLanguage fills this
    assert page.field_anomalies == 0


def test_zero_counts_stay_zero() -> None:
    item = video_item(vid(1), statistics={"viewCount": "0", "likeCount": "0", "commentCount": "0"})
    client, _ = make_client(FakeTransport(ok({"items": [item]})))
    stats = client.videos([vid(1)]).records[0].statistics
    assert (stats.view_count, stats.like_count, stats.comment_count) == (0, 0, 0)


def test_no_shorts_flag_is_inferred_from_duration() -> None:
    short = video_item(vid(1), contentDetails={"duration": "PT30S"})
    client, _ = make_client(FakeTransport(ok({"items": [short]})))
    page = client.videos([vid(1)])
    rec = page.records[0]
    assert rec.duration_iso == "PT30S"
    names = set(vars(rec)) | set(vars(page.hints[vid(1)]))
    assert not any("short" in n.lower() for n in names)


def test_hydrate_batches_of_50_dedupes_and_reports_not_returned() -> None:
    ids = [vid(i) for i in range(120)] + [vid(0), vid(1)]  # duplicates dropped

    def responder(resource: str, params: dict) -> HttpResponse:
        assert resource == "videos"
        batch = params["id"][0].split(",")
        # pretend every 10th video is deleted/private (simply not returned)
        return ok({"items": [video_item(v) for v in batch if int(v[3:]) % 10]})

    t = FakeTransport(responder=responder)
    client, _ = make_client(t)
    hyd = client.hydrate(ids)
    sizes = [len(t.params(i)["id"][0].split(",")) for i in range(len(t.urls))]
    assert sizes == [50, 50, 20]
    assert len(hyd.records) == 108
    assert sorted(hyd.not_returned) == sorted(vid(i) for i in range(0, 120, 10))
    assert hyd.stop_kind is None and hyd.remaining_ids == []
    assert client.ledger.used == {"search": 0, "units": 3}
    assert estimate_hydration(120).units == 3


@pytest.mark.parametrize(
    "bad",
    [
        [],
        [vid(1)] * 2,
        [vid(i) for i in range(51)],
        ["not-an-id"],
        ["abc,def,ghi"],
    ],
)
def test_videos_rejects_bad_batches_before_sending(bad: list[str]) -> None:
    t = FakeTransport()
    client, _ = make_client(t)
    with pytest.raises(ValueError):
        client.videos(bad)
    assert t.urls == [] and client.ledger.used["units"] == 0


# ---------------------------------------------------------------- malformed bodies


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"\xff\xfe",
        b"[]",
        b'{"items": {}}',
        b'{"items": [1]}',
        json.dumps({"items": [video_item("bad")]}).encode(),
        json.dumps({"items": [video_item(vid(9))]}).encode(),  # not requested
        json.dumps({"items": [video_item(vid(1)), video_item(vid(1))]}).encode(),  # duplicate
        json.dumps({"items": [video_item(vid(1), statistics={"viewCount": "-1"})]}).encode(),
        json.dumps({"items": [video_item(vid(1), statistics={"viewCount": "lots"})]}).encode(),
        json.dumps({"items": [video_item(vid(1), statistics={"likeCount": True})]}).encode(),
        json.dumps({"items": [video_item(vid(1), statistics=[1])]}).encode(),
        json.dumps({"items": [video_item(vid(1), snippet="x")]}).encode(),
        json.dumps({"items": [video_item(vid(1), status={"embeddable": "yes"})]}).encode(),
    ],
)
def test_malformed_videos_response_raises_and_is_not_retried(body: bytes) -> None:
    t = FakeTransport(HttpResponse(200, body))
    client, sleeps = make_client(t)
    with pytest.raises(MalformedResponseError):
        client.videos([vid(1)])
    assert len(t.urls) == 1 and sleeps == []


def test_malformed_published_at_raises() -> None:
    item = video_item(vid(1))
    item["snippet"]["publishedAt"] = "yesterday"
    client, _ = make_client(FakeTransport(ok({"items": [item]})))
    with pytest.raises(MalformedResponseError):
        client.videos([vid(1)])


def test_odd_optional_fields_drop_to_none_and_are_counted() -> None:
    item = video_item(vid(1), contentDetails={"duration": "ten minutes"})
    item["snippet"]["thumbnails"] = {"high": {"url": "https://evil.example/x.jpg"}}
    item["snippet"]["channelId"] = "notAChannel"
    client, _ = make_client(FakeTransport(ok({"items": [item]})))
    page = client.videos([vid(1)])
    rec = page.records[0]
    assert (rec.duration_iso, rec.thumbnail_url, rec.channel_id) == (None, None, None)
    assert page.field_anomalies == 3


def test_empty_items_means_none_returned() -> None:
    client, _ = make_client(FakeTransport(ok({})))
    hyd = client.hydrate([vid(1), vid(2)])
    assert hyd.records == [] and hyd.not_returned == [vid(1), vid(2)]


def test_malformed_error_body_still_classified_by_status() -> None:
    t = FakeTransport(HttpResponse(403, b"<html>nope</html>"))
    client, _ = make_client(t)
    with pytest.raises(PermissionDeniedError):
        client.videos([vid(1)])


# ---------------------------------------------------------------- retries


@pytest.mark.parametrize(
    "transient",
    [
        TransportFailure("timeout"),
        TransportFailure("network"),
        api_error(500, "backendError"),
        api_error(503),
        api_error(429),
        api_error(403, "rateLimitExceeded"),
        api_error(403, "userRateLimitExceeded"),
        api_error(403, info="RATE_LIMIT_EXCEEDED"),
    ],
)
def test_transient_errors_are_retried_with_jitter(transient) -> None:
    t = FakeTransport(transient, transient, ok({"items": [video_item(vid(1))]}))
    client, sleeps = make_client(t)
    page = client.videos([vid(1)])
    assert len(page.records) == 1
    assert len(t.urls) == 3 and len(sleeps) == 2 and client.retries == 2
    assert 0 <= sleeps[0] <= 0.5 and 0 <= sleeps[1] <= 1.0  # full-jitter caps
    assert client.ledger.used["units"] == 3  # every attempt is charged


def test_retries_are_bounded() -> None:
    t = FakeTransport(*[api_error(503)] * 4)
    client, sleeps = make_client(t, attempts=4)
    with pytest.raises(TransientError) as info:
        client.videos([vid(1)])
    assert info.value.status == 503
    assert len(t.urls) == 4 and len(sleeps) == 3


def test_retry_after_is_honoured_but_capped() -> None:
    t = FakeTransport(
        api_error(429, headers={"Retry-After": "3"}),
        api_error(429, headers={"Retry-After": "999"}),
        ok({"items": []}),
    )
    client, sleeps = make_client(t)
    client.videos([vid(1)])
    assert sleeps[0] >= 3 and sleeps[1] == 8.0


@pytest.mark.parametrize(
    ("resp", "exc", "kind", "resumable"),
    [
        (api_error(400, "badRequest", info="API_KEY_INVALID"), BadKeyError, "bad_key", False),
        (
            api_error(400, "badRequest", message="API key not valid. Please pass a valid API key."),
            BadKeyError,
            "bad_key",
            False,
        ),
        (api_error(400, "keyInvalid"), BadKeyError, "bad_key", False),
        (api_error(401), BadKeyError, "bad_key", False),
        (api_error(403, "quotaExceeded"), QuotaExhaustedError, "quota_exhausted", True),
        (api_error(403, "dailyLimitExceeded"), QuotaExhaustedError, "quota_exhausted", True),
        (api_error(403, "forbidden"), PermissionDeniedError, "permission", False),
        (
            api_error(403, "accessNotConfigured", info="SERVICE_DISABLED"),
            PermissionDeniedError,
            "permission",
            False,
        ),
        (
            api_error(403, info="API_KEY_SERVICE_BLOCKED"),
            PermissionDeniedError,
            "permission",
            False,
        ),
        (api_error(404, "videoNotFound"), NotFoundError, "not_found", False),
        (api_error(400, "invalidPageToken"), BadRequestError, "bad_request", False),
    ],
)
def test_stop_errors_are_never_retried(resp, exc, kind, resumable) -> None:
    t = FakeTransport(resp)
    client, sleeps = make_client(t)
    with pytest.raises(exc) as info:
        client.videos([vid(1)])
    assert info.value.kind == kind and info.value.resumable is resumable
    assert len(t.urls) == 1 and sleeps == [] and client.retries == 0


def test_hydrate_stops_cleanly_on_quota_and_reports_resume_ids() -> None:
    ids = [vid(i) for i in range(100)]
    t = FakeTransport(
        ok({"items": [video_item(v) for v in ids[:50]]}), api_error(403, "quotaExceeded")
    )
    client, _ = make_client(t)
    hyd = client.hydrate(ids)
    assert len(hyd.records) == 50
    assert hyd.stop_kind == "quota_exhausted"
    assert hyd.remaining_ids == ids[50:]
    # resume: a new run with the remaining IDs only
    t2 = FakeTransport(ok({"items": [video_item(v) for v in ids[50:]]}))
    client2, _ = make_client(t2)
    assert len(client2.hydrate(hyd.remaining_ids).records) == 50


# ---------------------------------------------------------------- quota buckets


def test_method_costs_match_verified_docs() -> None:
    # Verified 2026-11-17 on the official quota page: search.list has its own bucket
    # (1 per call); the other three cost 1 unit each. The old 100-unit search price is gone.
    assert METHOD_COST == {
        "search.list": ("search", 1),
        "videos.list": ("units", 1),
        "channels.list": ("units", 1),
        "playlistItems.list": ("units", 1),
    }
    assert estimate_search(3).as_dict() == {
        "search_bucket": 3,
        "units_bucket": 0,
        "requests": {"search.list": 3},
    }
    est = estimate_uploads(channel_count=60, pages_per_channel=2)
    assert est.units == 2 + 120 and est.search == 0


def test_local_budget_stops_before_sending() -> None:
    t = FakeTransport(ok({"items": []}))
    client, _ = make_client(t, units=1)
    client.videos([vid(1)])
    with pytest.raises(BudgetExhaustedError) as info:
        client.videos([vid(2)])
    assert info.value.resumable and len(t.urls) == 1
    assert client.ledger.snapshot()["used"] == {"search": 0, "units": 1}


def test_search_bucket_is_separate_from_units() -> None:
    t = FakeTransport(ok({"items": [{"id": {"videoId": vid(1)}}]}), ok({"items": []}))
    client, _ = make_client(t, search=1, units=5)
    res = client.search_video_ids("gta story", per_page=5)
    assert res.complete and res.video_ids == [vid(1)]
    client.videos([vid(1)])
    assert client.ledger.used == {"search": 1, "units": 1}
    res2 = client.search_video_ids("gta story")
    assert res2.stop_kind == "budget_exhausted" and len(t.urls) == 2


def test_budget_can_stop_retries_cleanly() -> None:
    t = FakeTransport(api_error(503), ok({"items": []}))
    client, _ = make_client(t, units=1)
    with pytest.raises(BudgetExhaustedError):
        client.videos([vid(1)])
    assert len(t.urls) == 1


def test_ledger_rejects_negative_budget() -> None:
    with pytest.raises(ValueError):
        QuotaLedger(-1, 0)


# ---------------------------------------------------------------- search / pagination


def test_search_request_is_ids_only_videos_only() -> None:
    t = FakeTransport(ok({"items": []}))
    client, _ = make_client(t)
    client.search_video_ids(
        " gta myths ",
        order="date",
        per_page=7,
        published_after="2025-01-01T00:00:00Z",
        region_code="IN",
    )
    p = t.params()
    assert t.urls[0].startswith(API_BASE + "search?")
    assert p["part"] == ["id"] and p["type"] == ["video"] and p["q"] == ["gta myths"]
    assert p["fields"] == ["nextPageToken,items(id(videoId))"]
    assert p["maxResults"] == ["7"] and p["order"] == ["date"]
    assert p["publishedAfter"] == ["2025-01-01T00:00:00Z"] and p["regionCode"] == ["IN"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": "x" * 201},
        {"query": "ok", "order": "random"},
        {"query": "ok", "max_pages": 0},
        {"query": "ok", "max_pages": 21},
        {"query": "ok", "per_page": 51},
        {"query": "ok", "region_code": ""},
    ],
)
def test_search_validates_inputs(kwargs) -> None:
    t = FakeTransport()
    client, _ = make_client(t)
    query = kwargs.pop("query")
    with pytest.raises(ValueError):
        client.search_video_ids(query, **kwargs)
    assert t.urls == []


def test_search_paginates_dedupes_and_resumes_from_token() -> None:
    pages = [
        ok(
            {
                "items": [{"id": {"videoId": vid(1)}}, {"id": {"videoId": vid(2)}}],
                "nextPageToken": "T2",
            }
        ),
        ok(
            {
                "items": [{"id": {"videoId": vid(2)}}, {"id": {"videoId": vid(3)}}],
                "nextPageToken": "T3",
            }
        ),
    ]
    t = FakeTransport(*pages)
    client, _ = make_client(t)
    res = client.search_video_ids("gta", max_pages=2, per_page=2)
    assert res.video_ids == [vid(1), vid(2), vid(3)]
    assert res.pages == 2 and not res.complete and res.resume_token == "T3"
    assert "pageToken" not in t.params(0) and t.params(1)["pageToken"] == ["T2"]

    t2 = FakeTransport(ok({"items": [{"id": {"videoId": vid(4)}}]}))
    client2, _ = make_client(t2)
    res2 = client2.search_video_ids("gta", page_token=res.resume_token)
    assert t2.params()["pageToken"] == ["T3"] and res2.complete


def test_pagination_stops_with_resume_token_on_quota() -> None:
    t = FakeTransport(
        ok({"items": [{"id": {"videoId": vid(1)}}], "nextPageToken": "T2"}),
        api_error(403, "quotaExceeded"),
    )
    client, _ = make_client(t)
    res = client.search_video_ids("gta", max_pages=3)
    assert res.video_ids == [vid(1)]
    assert res.stop_kind == "quota_exhausted" and res.resume_token == "T2"


def test_repeating_page_token_does_not_loop() -> None:
    t = FakeTransport(
        ok({"items": [], "nextPageToken": "SAME"}), ok({"items": [], "nextPageToken": "SAME"})
    )
    client, _ = make_client(t)
    res = client.search_video_ids("gta", max_pages=5)
    assert res.stop_kind == "malformed" and len(t.urls) == 2


def test_malformed_search_item_is_rejected() -> None:
    t = FakeTransport(ok({"items": [{"id": {"channelId": cid(1)}}]}))
    client, _ = make_client(t)
    assert client.search_video_ids("gta").stop_kind == "malformed"


# ---------------------------------------------------------------- channels / uploads


def _channel(n: int, uploads: str | None = "auto") -> dict:
    related = {} if uploads is None else {"uploads": upl(n) if uploads == "auto" else uploads}
    return {
        "id": cid(n),
        "snippet": {"title": f"Synthetic {n}"},
        "contentDetails": {"relatedPlaylists": related},
    }


def test_uploads_discovery_uses_channels_then_playlist_items() -> None:
    def responder(resource: str, params: dict) -> HttpResponse:
        if resource == "channels":
            assert params["fields"] == [
                "items(id,snippet(title),contentDetails(relatedPlaylists(uploads)))"
            ]
            return ok({"items": [_channel(1), _channel(2, uploads=None)]})
        assert resource == "playlistItems"
        assert params["part"] == ["contentDetails"]
        assert params["playlistId"] == [upl(1)]
        return ok({"items": [{"contentDetails": {"videoId": vid(7)}}]})

    t = FakeTransport(responder=responder)
    client, _ = make_client(t)
    results, stop = client.uploads_video_ids([cid(1), cid(2), cid(1)])
    assert stop is None
    assert results[cid(1)].video_ids == [vid(7)] and cid(2) not in results
    assert client.ledger.used == {"search": 0, "units": 2}  # 1 channels + 1 playlist page
    assert client.ledger.requests == {"channels.list": 1, "playlistItems.list": 1}


def test_channels_reject_unrequested_and_bad_uploads() -> None:
    client, _ = make_client(FakeTransport(ok({"items": [_channel(9)]})))
    with pytest.raises(MalformedResponseError):
        client.channels([cid(1)])
    client, _ = make_client(FakeTransport(ok({"items": [_channel(1, uploads="nope")]})))
    with pytest.raises(MalformedResponseError):
        client.channels([cid(1)])


def test_channel_for_handle() -> None:
    t = FakeTransport(ok({"items": [_channel(1)]}), ok({}))
    client, _ = make_client(t)
    assert client.channel_for_handle("synthetic.handle").uploads_playlist_id == upl(1)
    assert t.params(0)["forHandle"] == ["@synthetic.handle"]
    assert client.channel_for_handle("nobody_here") is None
    with pytest.raises(ValueError):
        client.channel_for_handle("bad handle")


# ---------------------------------------------------------------- transport pinning


def test_urllib_transport_refuses_other_hosts() -> None:
    with pytest.raises(ValueError):
        UrllibTransport().send("https://example.com/youtube/v3/videos", 5)
    with pytest.raises(ValueError):
        UrllibTransport().send("http://www.googleapis.com/youtube/v3/videos", 5)


def test_client_requires_key_and_sane_timeout() -> None:
    with pytest.raises(BadKeyError):
        YouTubeClient("  ", QuotaLedger(1, 1), transport=FakeTransport())
    with pytest.raises(ValueError):
        YouTubeClient("k", QuotaLedger(1, 1), transport=FakeTransport(), timeout=0.1)
