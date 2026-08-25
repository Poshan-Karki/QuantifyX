
from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Request
from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter

LOGGER = logging.getLogger("quantifyx.ratelimit")

_storage = storage_from_string(os.getenv("RATE_LIMIT_REDIS_URL", "memory://"))
_limiter = MovingWindowRateLimiter(_storage)

#: Disabled under pytest, and by setting RATE_LIMIT_ENABLED=0.
_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1").lower() not in {"0", "false", "no"}


def client_key(request: Request) -> str:
    """Identify the caller.

    X-Forwarded-For is trusted only when TRUST_PROXY_HEADERS is set, because a
    client can otherwise spoof it and mint itself a fresh allowance per request.
    Set it when running behind a proxy that overwrites the header.
    """
    if os.getenv("TRUST_PROXY_HEADERS", "").lower() in {"1", "true", "yes"}:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimit:
    """Dependency enforcing one limit, e.g. `RateLimit("30/minute")`.

    Usage:  @app.post("/thing", dependencies=[Depends(RateLimit("30/minute"))])
    """

    def __init__(self, limit: str, scope: str | None = None):
        self.limit = parse(limit)
        self.scope = scope or limit

    async def __call__(self, request: Request) -> None:
        if not _ENABLED:
            return

        key = client_key(request)
        if not _limiter.hit(self.limit, self.scope, key):
            reset_at, _ = _limiter.get_window_stats(self.limit, self.scope, key)
            LOGGER.warning("Rate limit %s exceeded by %s on %s", self.limit, key, request.url.path)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit reached ({self.limit}). "
                    "Wait a moment before trying again."
                ),
                headers={"Retry-After": str(max(1, int(reset_at)))},
            )
