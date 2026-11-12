"""Rate limit per client IP, kept in memory.

Two windows per client: every request counts against a per-minute limit, and the
endpoints that cost money or load the PNCP also count against a per-hour limit.
The counters live in the process, which is enough for a single instance; several
instances would need a shared store (e.g. Redis), see ADR-037.

The client IP is the connection's address, unless the connection comes from a
trusted proxy (the frontend's server, which forwards browser calls): then the
X-Forwarded-For header is read from the right, skipping trusted addresses, so a
client cannot pick its own identity by sending the header.
"""

import ipaddress
import math
import re
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.responses import JSONResponse

# (method, path pattern) of the costly endpoints.
COSTLY_ROUTES: list[tuple[str, re.Pattern[str]]] = [
    ("POST", re.compile(r"^/documents/?$")),
    ("POST", re.compile(r"^/documents/[^/]+/analyze$")),
    ("POST", re.compile(r"^/analyses/[^/]+/eligibility$")),
    ("POST", re.compile(r"^/pncp/import$")),
    ("GET", re.compile(r"^/pncp/search$")),
]
EXEMPT_PATHS = {"/health"}


@dataclass(frozen=True)
class Window:
    name: str
    limit: int
    seconds: float


class RateLimiter:
    def __init__(
        self,
        per_minute: int,
        costly_per_hour: int,
        trusted_proxies: list[str],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.general = Window("geral", per_minute, 60.0)
        self.costly = Window("custosa", costly_per_hour, 3600.0)
        # Addresses or networks (CIDR), e.g. "127.0.0.1" or "172.16.0.0/12".
        self.trusted = [ipaddress.ip_network(entry, strict=False) for entry in trusted_proxies]
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def is_trusted(self, address: str | None) -> bool:
        try:
            ip = ipaddress.ip_address(address or "")
        except ValueError:
            return False
        return any(ip in network for network in self.trusted)

    def client_ip(self, peer: str | None, forwarded_for: str | None) -> str:
        if self.is_trusted(peer) and forwarded_for:
            hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
            for hop in reversed(hops):
                if not self.is_trusted(hop):
                    return hop
        return peer or "desconhecido"

    @staticmethod
    def is_costly(method: str, path: str) -> bool:
        return any(method == m and pattern.match(path) for m, pattern in COSTLY_ROUTES)

    def check(self, client: str, method: str, path: str) -> float | None:
        """Record the request; seconds to wait if it is over a limit, else None."""
        windows = [self.general]
        if self.is_costly(method, path):
            windows.append(self.costly)
        now = self._clock()
        with self._lock:
            for window in windows:
                if window.limit <= 0:
                    continue
                hits = self._hits.setdefault((client, window.name), deque())
                while hits and now - hits[0] >= window.seconds:
                    hits.popleft()
                if len(hits) >= window.limit:
                    return max(1.0, window.seconds - (now - hits[0]))
            for window in windows:
                if window.limit > 0:
                    self._hits[(client, window.name)].append(now)
        return None


def rate_limit_middleware(
    limiter: RateLimiter,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path in EXEMPT_PATHS:
            return await call_next(request)
        client = limiter.client_ip(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
        )
        wait = limiter.check(client, request.method, path)
        if wait is not None:
            return JSONResponse(
                {
                    "detail": "Muitas requisições em pouco tempo. Tente de novo em "
                    f"{math.ceil(wait)} segundos."
                },
                status_code=429,
                headers={"Retry-After": str(math.ceil(wait))},
            )
        return await call_next(request)

    return middleware
