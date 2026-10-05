"""
Rate limiting for sensitive endpoints — Phase 11 (spec section 32's
"harden the auth surface" concerns, made concrete).

Login and registration are the two endpoints an attacker can hammer
without ever holding a valid token: brute-forcing a password, or
spraying the registration endpoint to enumerate/occupy email
addresses. Every other route in the project already sits behind
`@token_required`, which makes unauthenticated abuse far less
attractive there.

This is a small in-memory, fixed-window limiter — no Redis, no new
dependency — in the same spirit as Phase 8 choosing a plain Haversine
formula over a spatial database extension. It is keyed on the
caller's IP address plus the route name, so a slow login attacker on
one IP doesn't block every other user of the API.

Known limitation (documented rather than hidden): counters live in
this process's memory, so they reset on restart and are NOT shared
across multiple worker processes/machines. That's an acceptable
tradeoff for an academic-scope project running as a single process;
a production deployment behind multiple workers would want a shared
store (e.g. Redis) instead.
"""

import threading
import time
from functools import wraps

from flask import jsonify, request

# {(bucket_key, client_key): [timestamps within the current window]}
_hits: dict[tuple[str, str], list[float]] = {}
_lock = threading.Lock()


def _client_key() -> str:
    """
    Best-effort caller identity for rate limiting purposes only — NOT
    used for authentication or authorization. Honors
    X-Forwarded-For (set by a reverse proxy) before falling back to
    the direct connection address, then finally a constant so the
    limiter still works (shared across all callers) in a test client
    with no address at all.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limit(*, max_requests: int, window_seconds: int, bucket: str):
    """
    Decorator factory: allow at most `max_requests` calls per
    `client_key()` within a rolling `window_seconds` window for this
    `bucket` (a short label so /login and /register keep independent
    counters even from the same caller).

    On the window being exceeded, returns 429 in the project's
    standard error envelope rather than calling the view.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            key = (bucket, _client_key())
            now = time.monotonic()
            cutoff = now - window_seconds

            with _lock:
                timestamps = [t for t in _hits.get(key, []) if t > cutoff]
                if len(timestamps) >= max_requests:
                    retry_after = int(window_seconds - (now - timestamps[0])) + 1
                    _hits[key] = timestamps
                    return (
                        jsonify(
                            success=False,
                            message=(
                                "Too many requests. Please wait before "
                                "trying again."
                            ),
                            error="RATE_LIMITED",
                        ),
                        429,
                        {"Retry-After": str(retry_after)},
                    )
                timestamps.append(now)
                _hits[key] = timestamps

            return view_func(*args, **kwargs)

        return wrapper

    return decorator
