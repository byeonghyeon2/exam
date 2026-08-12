import hashlib
import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.api.v1.auth import SESSION_COOKIE

PROTECTED_DATA_PREFIXES = (
    "/api/v1/study/",
    "/api/v1/mock-exams/",
    "/api/v1/questions/",
    "/api/v1/wrong-notes",
)


class FixedWindowRateLimiter:
    """Small single-process limiter; Nginx remains the distributed perimeter limiter."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def consume(self, key: str, now: float | None = None) -> tuple[bool, int]:
        current = time.monotonic() if now is None else now
        boundary = current - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= boundary:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (current - events[0]) + 0.999))
                return False, retry_after
            events.append(current)
            return True, 0


def is_problem_data_request(request: Request) -> bool:
    return request.url.path.startswith(PROTECTED_DATA_PREFIXES)


def _is_trusted_proxy(host: str, trusted_proxies: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    for value in trusted_proxies.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            if address in ipaddress.ip_network(value, strict=False):
                return True
        except ValueError:
            continue
    return False


def rate_limit_keys(request: Request, trusted_proxies: str = "") -> list[str]:
    host = request.client.host if request.client else "unknown"
    forwarded_host = request.headers.get("x-real-ip", "").strip()
    if forwarded_host and _is_trusted_proxy(host, trusted_proxies):
        try:
            host = str(ipaddress.ip_address(forwarded_host))
        except ValueError:
            pass
    keys = [f"ip:{host}"]
    session = request.cookies.get(SESSION_COOKIE)
    if session:
        digest = hashlib.sha256(session.encode("utf-8")).hexdigest()
        keys.append(f"session:{digest}")
    return keys
