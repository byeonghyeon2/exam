import hashlib
import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

SESSION_COOKIE = "certexam_session"

PROTECTED_DATA_PREFIXES = (
    "/api/v1/study/",
    "/api/v1/mock-exams/",
    "/api/v1/questions/",
    "/api/v1/wrong-notes",
)
AUTHENTICATION_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/passkeys/",
    "/api/v1/auth/admin/recovery",
)


class FixedWindowRateLimiter:
    """Small single-process limiter; Nginx remains the distributed perimeter limiter."""

    def __init__(self, limit: int, window_seconds: int, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def consume(self, key: str, now: float | None = None) -> tuple[bool, int]:
        current = time.monotonic() if now is None else now
        boundary = current - self.window_seconds
        with self._lock:
            for stale_key, stale_events in list(self._events.items()):
                while stale_events and stale_events[0] <= boundary:
                    stale_events.popleft()
                if not stale_events:
                    self._events.pop(stale_key, None)
            if key not in self._events and len(self._events) >= self.max_keys:
                oldest_key = min(self._events, key=lambda item: self._events[item][0])
                self._events.pop(oldest_key, None)
            events = self._events[key]
            if len(events) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (current - events[0]) + 0.999))
                return False, retry_after
            events.append(current)
            return True, 0


def is_problem_data_request(request: Request) -> bool:
    return request.url.path.startswith(PROTECTED_DATA_PREFIXES)


def is_authentication_request(request: Request) -> bool:
    return request.url.path.startswith(AUTHENTICATION_PREFIXES)


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
