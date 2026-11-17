"""Seed link / ID normalization. Pure string parsing: a seed URL is never fetched.

Accepted seeds:

* video: bare 11-char ID, ``youtube.com/watch?v=``, ``/shorts/``, ``/embed/``, ``/live/``,
  ``youtu.be/<id>``
* channel: ``UC`` + 22-char ID, ``youtube.com/channel/<id>``, ``@handle``,
  ``youtube.com/@handle``
* playlist: ``youtube.com/playlist?list=<id>`` or a bare ``PL``/``UU``/``OL``… ID

Only ``https``/``http`` links on the YouTube hosts below are accepted. Anything else
(other hosts, credentials in the URL, ports, unknown paths) is rejected. A ``/shorts/``
link only says how the seed was written; it is not recorded as a Shorts flag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from .errors import InvalidSeedError

SeedKind = Literal["video", "channel", "handle", "playlist"]

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
PLAYLIST_ID_RE = re.compile(r"^(PL|UU|LL|FL|OL|RD|UL|PU)[A-Za-z0-9_-]{8,62}$")
# YouTube handles: 3-30 chars of letters, digits, '_', '-', '.'.
HANDLE_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,30}$")

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_HOSTS = {"youtu.be"}
_MAX_SEED_LEN = 300
_VIDEO_PATH_PREFIXES = ("shorts", "embed", "live", "v")


@dataclass(frozen=True)
class Seed:
    kind: SeedKind
    value: str  # canonical ID (or handle without '@')


def _reject(why: str) -> InvalidSeedError:
    return InvalidSeedError(f"invalid seed: {why}")


def _video(value: str) -> Seed:
    if not VIDEO_ID_RE.match(value):
        raise _reject("not a video ID")
    return Seed("video", value)


def normalize_seed(raw: str) -> Seed:
    """Return a validated ``Seed`` or raise ``InvalidSeedError``."""
    if not isinstance(raw, str):
        raise _reject("not text")
    text = raw.strip()
    if not text or len(text) > _MAX_SEED_LEN or any(c.isspace() for c in text):
        raise _reject("empty, too long or contains whitespace")

    if text.startswith("@"):
        return _handle(text[1:])
    if "/" not in text and "." not in text and "?" not in text:
        return _bare_id(text)
    return _from_url(text)


def _handle(value: str) -> Seed:
    if not HANDLE_RE.match(value):
        raise _reject("not a handle")
    return Seed("handle", value)


def _bare_id(text: str) -> Seed:
    if CHANNEL_ID_RE.match(text):
        return Seed("channel", text)
    if VIDEO_ID_RE.match(text):
        return Seed("video", text)
    if PLAYLIST_ID_RE.match(text):
        return Seed("playlist", text)
    raise _reject("not a video, channel or playlist ID")


def _from_url(text: str) -> Seed:
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise _reject("unparseable URL") from None
    if parts.scheme not in ("https", "http"):
        raise _reject("scheme must be http(s)")
    if parts.username or parts.password or port is not None:
        raise _reject("credentials or ports are not allowed")
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    query = parse_qs(parts.query, keep_blank_values=False)

    if host in _SHORT_HOSTS:
        if len(segments) != 1:
            raise _reject("unexpected youtu.be path")
        return _video(segments[0])
    if host not in _YOUTUBE_HOSTS:
        raise _reject("not a YouTube host")

    if segments == ["watch"]:
        values = query.get("v", [])
        if len(values) != 1:
            raise _reject("watch link needs exactly one v=")
        return _video(values[0])
    if segments == ["playlist"]:
        values = query.get("list", [])
        if len(values) != 1 or not PLAYLIST_ID_RE.match(values[0]):
            raise _reject("playlist link needs one valid list=")
        return Seed("playlist", values[0])
    if len(segments) == 2 and segments[0] in _VIDEO_PATH_PREFIXES:
        return _video(segments[1])
    if len(segments) >= 1 and segments[0] == "channel":
        if len(segments) > 2 or len(segments) == 1 or not CHANNEL_ID_RE.match(segments[1]):
            raise _reject("not a channel link")
        return Seed("channel", segments[1])
    if len(segments) >= 1 and segments[0].startswith("@"):
        # /@handle, /@handle/videos, /@handle/shorts ... all name the same channel
        return _handle(segments[0][1:])
    raise _reject("unsupported YouTube link")


def normalize_seeds(raws: list[str]) -> tuple[list[Seed], int]:
    """Normalize many seeds. Returns (unique valid seeds in input order, rejected count)."""
    seen: set[Seed] = set()
    out: list[Seed] = []
    rejected = 0
    for raw in raws:
        try:
            seed = normalize_seed(raw)
        except InvalidSeedError:
            rejected += 1
            continue
        if seed not in seen:
            seen.add(seed)
            out.append(seed)
    return out, rejected
