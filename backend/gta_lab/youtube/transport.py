"""HTTPS transport pinned to the official YouTube Data API v3 base URL.

The default transport uses the standard library only (no new dependency). It refuses any
URL outside ``API_BASE``, refuses redirects, caps the response size and maps socket and
timeout failures to ``TransportFailure``. Tests inject a fake transport instead.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

API_BASE = "https://www.googleapis.com/youtube/v3/"
MAX_BODY_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


class TransportFailure(Exception):
    """Network-level failure. ``kind`` is ``timeout`` or ``network``; no URL is kept."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class Transport(Protocol):
    def send(self, url: str, timeout: float) -> HttpResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None  # a redirect surfaces as an HTTP 3xx error, which is not retried


class UrllibTransport:
    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_NoRedirect())

    def send(self, url: str, timeout: float) -> HttpResponse:
        if not url.startswith(API_BASE):
            raise ValueError("refusing a non-YouTube-API destination")
        request = urllib.request.Request(  # noqa: S310 - scheme and host pinned above
            url, headers={"Accept": "application/json", "Accept-Encoding": "identity"}
        )
        try:
            with self._opener.open(request, timeout=timeout) as resp:
                return HttpResponse(resp.status, _read_capped(resp), dict(resp.headers))
        except urllib.error.HTTPError as exc:
            # HTTPError keeps the URL (with the key) on .filename/.url: drop the exception
            # and keep only status, headers and the capped body.
            status, headers = exc.code, dict(exc.headers or {})
            try:
                body = _read_capped(exc)
            except Exception:
                body = b""
            finally:
                exc.close()
            return HttpResponse(status, body, headers)
        except TimeoutError:
            raise TransportFailure("timeout") from None
        except urllib.error.URLError as exc:
            kind = "timeout" if isinstance(exc.reason, TimeoutError) else "network"
            raise TransportFailure(kind) from None
        except OSError:
            raise TransportFailure("network") from None


def _read_capped(resp) -> bytes:  # noqa: ANN001
    body = resp.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        return b""  # treated as malformed by the parser
    return body
