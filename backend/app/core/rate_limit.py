"""Rate limit per client IP, kept in memory.

Two windows per client: every request counts against a per-minute limit, and the
endpoints that cost money or load the PNCP also count against a per-hour limit.
The counters live in the process, which is enough for a single instance; several
instances would need a shared store (e.g. Redis), see ADR-037.

The client IP is the connection's address, unless the connection comes from a
trusted proxy (the frontend's server, which forwards browser calls): then the
X-Forwarded-For header is read from the right, skipping trusted addresses, so a
client cannot pick its own identity by sending the header.

A frontend whose address is not fixed (a serverless platform such as Vercel)
cannot be listed as a trusted proxy. It proves itself with a shared secret
instead (PROXY_TOKEN) and names the visitor in X-Edital-Client-IP, taken from
the header its platform sets and overwrites (see ADR-040).
"""

import hmac
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
PROXY_TOKEN_HEADER = "x-edital-proxy-token"
CLIENT_IP_HEADER = "x-edital-client-ip"


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
        proxy_token: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.general = Window("geral", per_minute, 60.0)
        self.costly = Window("custosa", costly_per_hour, 3600.0)
        # Addresses or networks (CIDR), e.g. "127.0.0.1" or "172.16.0.0/12".
        self.trusted = [ipaddress.ip_network(entry, strict=False) for entry in trusted_proxies]
        self.proxy_token = proxy_token or None
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def is_trusted(self, address: str | None) -> bool:
        try:
            ip = ipaddress.ip_address(address or "")
        except ValueError:
            return False
        return any(ip in network for network in self.trusted)

    def has_valid_token(self, token: str | None) -> bool:
        if not self.proxy_token or not token:
            return False
        return hmac.compare_digest(token.encode(), self.proxy_token.encode())

    def client_ip(
        self,
        peer: str | None,
        forwarded_for: str | None,
        token: str | None = None,
        named_client: str | None = None,
    ) -> str:
        if named_client and self.has_valid_token(token):
            try:
                return str(ipaddress.ip_address(named_client.strip()))
            except ValueError:
                pass
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
            request.headers.get(PROXY_TOKEN_HEADER),
            request.headers.get(CLIENT_IP_HEADER),
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
