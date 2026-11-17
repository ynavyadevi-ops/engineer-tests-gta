"""Typed adapter errors and secret redaction.

Every error carries only an HTTP status, an API reason code and a short, fixed message
written here. API error *messages* and request URLs are never copied into exceptions,
because a URL carries the key and a message can echo request content.
"""

from __future__ import annotations

import re
from typing import Literal

StopKind = Literal[
    "bad_key", "permission", "quota_exhausted", "budget_exhausted", "not_found", "bad_request"
]

# Google API key shape (AIza + 35 chars) and any key=... query parameter.
_KEY_SHAPE_RE = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
_KEY_PARAM_RE = re.compile(r"(?i)((?:^|[?&\s])key=)[^&#\s]+")
REDACTED = "[REDACTED]"


def redact(text: str, *secrets: str | None) -> str:
    """Remove known secret values, key-shaped strings and ``key=`` parameters."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _KEY_PARAM_RE.sub(lambda m: m.group(1) + REDACTED, text)
    return _KEY_SHAPE_RE.sub(REDACTED, text)


class YouTubeError(Exception):
    """Base class. ``str()`` never contains a key, URL or API-provided text."""

    retryable = False

    def __init__(self, message: str, *, status: int | None = None, reason: str | None = None):
        super().__init__(message)
        self.status = status
        self.reason = reason

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status={self.status!r}, reason={self.reason!r})"


class StopError(YouTubeError):
    """A clean, non-retryable stop. ``kind`` tells the caller whether it can resume."""

    kind: StopKind = "permission"

    @property
    def resumable(self) -> bool:
        # Quota stops resume after the reset or with a new budget; key/permission stops
        # need the user to fix configuration first.
        return self.kind in ("quota_exhausted", "budget_exhausted")


class BadKeyError(StopError):
    kind: StopKind = "bad_key"


class PermissionDeniedError(StopError):
    kind: StopKind = "permission"


class QuotaExhaustedError(StopError):
    """YouTube reported the project's daily quota as used up (resets midnight PT)."""

    kind: StopKind = "quota_exhausted"


class BudgetExhaustedError(StopError):
    """The local per-bucket budget would be exceeded; nothing was sent."""

    kind: StopKind = "budget_exhausted"


class NotFoundError(StopError):
    kind: StopKind = "not_found"


class BadRequestError(StopError):
    """HTTP 400 other than an invalid key (bad parameter, invalid page token...)."""

    kind: StopKind = "bad_request"


class TransientError(YouTubeError):
    """Timeout, network failure, 5xx or rate limiting that outlived the retry budget."""

    retryable = True
    retry_after: str | None = None


class MalformedResponseError(YouTubeError):
    """The response did not match the expected shape. Never retried, never stored."""


class InvalidSeedError(ValueError):
    """A seed link or ID failed normalization. The input itself is not echoed back."""
