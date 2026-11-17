"""Seed normalization: links and IDs are validated before any endpoint is called."""

from __future__ import annotations

import pytest

from gta_lab.youtube import InvalidSeedError, Seed, normalize_seed, normalize_seeds

from .youtube_fakes import cid, upl, vid

V = vid(1)
C = cid(1)
P = "PL" + "zzTEST" + "0" * 26


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (V, Seed("video", V)),
        (f"  {V}  ", Seed("video", V)),
        (f"https://www.youtube.com/watch?v={V}", Seed("video", V)),
        (f"https://www.youtube.com/watch?v={V}&t=42s&list={P}", Seed("video", V)),
        (f"youtube.com/watch?v={V}", Seed("video", V)),
        (f"https://m.youtube.com/watch?v={V}", Seed("video", V)),
        (f"https://youtu.be/{V}?si=abc", Seed("video", V)),
        (f"https://www.youtube.com/shorts/{V}", Seed("video", V)),
        (f"https://www.youtube.com/embed/{V}", Seed("video", V)),
        (f"https://www.youtube.com/live/{V}", Seed("video", V)),
        (C, Seed("channel", C)),
        (f"https://www.youtube.com/channel/{C}", Seed("channel", C)),
        ("@synthetic.handle", Seed("handle", "synthetic.handle")),
        ("https://www.youtube.com/@synthetic_handle/videos", Seed("handle", "synthetic_handle")),
        (f"https://www.youtube.com/playlist?list={P}", Seed("playlist", P)),
        (upl(1), Seed("playlist", upl(1))),
    ],
)
def test_valid_seeds_normalize(raw: str, expected: Seed) -> None:
    assert normalize_seed(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "short",
        "x" * 400,
        f"{V} {V}",
        f"https://evil.example/watch?v={V}",
        f"https://youtube.com.evil.example/watch?v={V}",
        f"https://user:pw@www.youtube.com/watch?v={V}",
        f"https://www.youtube.com:8443/watch?v={V}",
        f"ftp://www.youtube.com/watch?v={V}",
        f"javascript:alert(1)//www.youtube.com/watch?v={V}",
        "https://www.youtube.com/watch?v=tooShort",
        f"https://www.youtube.com/watch?v={V}&v={vid(2)}",
        "https://www.youtube.com/results?search_query=gta",
        "https://www.youtube.com/channel/notAChannel",
        "https://www.youtube.com/playlist?list=bad",
        "@a",
        "@bad handle",
        f"https://youtu.be/{V}/extra",
        123,
    ],
)
def test_invalid_seeds_are_rejected(raw: object) -> None:
    with pytest.raises(InvalidSeedError):
        normalize_seed(raw)  # type: ignore[arg-type]


def test_shorts_link_is_not_a_shorts_flag() -> None:
    seed = normalize_seed(f"https://www.youtube.com/shorts/{V}")
    assert seed == Seed("video", V)  # kind is "video": no format is inferred from the link


def test_normalize_many_dedupes_and_counts_rejections() -> None:
    seeds, rejected = normalize_seeds(
        [V, f"https://youtu.be/{V}", "https://evil.example/x", C, "nope"]
    )
    assert seeds == [Seed("video", V), Seed("channel", C)]
    assert rejected == 2
