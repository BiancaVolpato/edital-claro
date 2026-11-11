"""HTTP client for the public PNCP APIs.

Two official APIs are used, each with its own OpenAPI document:

- API de Consulta (``/api/consulta``): search of procurements by publication date;
- API PNCP (``/api/pncp``): list and download of the files of a procurement.

The client is polite and resilient: a minimum interval between requests, a
timeout per request, retries with exponential backoff on network errors, 429
and 5xx (honouring ``Retry-After``), and a local cache of JSON responses.
File downloads are not cached here: the ingestion already deduplicates files
by content hash.
"""

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRY_AFTER_SECONDS = 30.0


class PncpError(RuntimeError):
    """The PNCP could not be reached or answered with an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ResponseCache:
    """JSON responses on disk, one file per URL, valid for ``ttl_seconds``."""

    def __init__(self, folder: Path, ttl_seconds: int, clock: Callable[[], float] = time.time):
        self.folder = folder
        self.ttl_seconds = ttl_seconds
        self._clock = clock

    def _path(self, key: str) -> Path:
        return self.folder / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        try:
            if self._clock() - path.stat().st_mtime > self.ttl_seconds:
                return None
            return json.loads(path.read_text(encoding="utf-8"))["body"]
        except (OSError, ValueError, KeyError):
            return None

    def set(self, key: str, body: Any) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            # Written to a temporary file first so a reader never sees half a file.
            path = self._path(key)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"url": key, "body": body}, ensure_ascii=False), "utf-8")
            tmp.replace(path)
        except OSError:
            logger.warning("could not write the PNCP cache", extra={"folder": str(self.folder)})


class PncpClient:
    def __init__(
        self,
        *,
        consulta_url: str,
        api_url: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        min_interval_seconds: float = 1.0,
        cache: ResponseCache | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.consulta_url = consulta_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self.max_retries = max_retries
        self.min_interval_seconds = min_interval_seconds
        self.cache = cache
        self._http = httpx.Client(
            timeout=timeout_seconds, transport=transport, follow_redirects=True
        )
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._last_request: float | None = None
        self.requests_made = 0

    def close(self) -> None:
        self._http.close()

    def _wait_turn(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last_request is not None:
                wait = self.min_interval_seconds - (now - self._last_request)
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()

    def _request(self, url: str, params: Mapping[str, Any] | None = None) -> httpx.Response:
        attempt = 0
        while True:
            self._wait_turn()
            self.requests_made += 1
            try:
                response = self._http.get(url, params=params)
            except httpx.TransportError as exc:  # timeouts and connection errors
                if attempt >= self.max_retries:
                    raise PncpError(f"O PNCP não respondeu ({type(exc).__name__}).") from exc
                delay = 2.0**attempt
            else:
                if response.status_code not in RETRY_STATUS or attempt >= self.max_retries:
                    return response
                delay = _retry_after(response) or 2.0**attempt
            logger.warning(
                "retrying PNCP request", extra={"url": url, "attempt": attempt + 1, "delay": delay}
            )
            self._sleep(delay)
            attempt += 1

    def get_json(self, url: str, params: Mapping[str, Any] | None = None) -> Any | None:
        """GET a JSON resource. ``None`` means "no content" (HTTP 204)."""
        key = str(httpx.URL(url, params=params))
        if self.cache and (cached := self.cache.get(key)) is not None:
            return cached["data"]
        response = self._request(url, params)
        if response.status_code == 204:
            body = None
        elif response.status_code == 200:
            try:
                body = response.json()
            except ValueError as exc:
                raise PncpError("O PNCP respondeu com um conteúdo inválido.", 200) from exc
        else:
            raise PncpError(_error_message(response), response.status_code)
        if self.cache:
            # Wrapped so that a cached "no content" is told apart from a cache miss.
            self.cache.set(key, {"data": body})
        return body

    def download(self, url: str, max_bytes: int) -> bytes:
        """Download a file, refusing anything larger than ``max_bytes``."""
        self._wait_turn()
        self.requests_made += 1
        try:
            with self._http.stream("GET", url) as response:
                if response.status_code != 200:
                    raise PncpError(_error_message(response), response.status_code)
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise PncpError(
                            f"Arquivo maior que o limite de {max_bytes // (1024 * 1024)} MB."
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.TransportError as exc:
            raise PncpError(f"Falha ao baixar o arquivo do PNCP ({type(exc).__name__}).") from exc

    # --- Endpoints (paths from the official OpenAPI documents) ---------------------

    def search_by_publication(self, params: Mapping[str, Any]) -> dict[str, Any] | None:
        """API de Consulta: GET /v1/contratacoes/publicacao."""
        return self.get_json(f"{self.consulta_url}/v1/contratacoes/publicacao", params)

    def get_procurement(self, cnpj: str, year: int, sequential: int) -> dict[str, Any] | None:
        """API de Consulta: GET /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}."""
        url = f"{self.consulta_url}/v1/orgaos/{cnpj}/compras/{year}/{sequential}"
        return self.get_json(url)

    def list_files(self, cnpj: str, year: int, sequential: int) -> list[dict[str, Any]]:
        """API PNCP: GET /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos."""
        url = f"{self.api_url}/v1/orgaos/{cnpj}/compras/{year}/{sequential}/arquivos"
        return self.get_json(url) or []

    def file_url(self, cnpj: str, year: int, sequential: int, document: int) -> str:
        """API PNCP: GET /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos/{n}.

        Built from the documented path instead of trusting the ``url`` field of the
        listing, so a download can only ever go to the PNCP.
        """
        return f"{self.api_url}/v1/orgaos/{cnpj}/compras/{year}/{sequential}/arquivos/{document}"


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return min(max(float(value), 0.0), _MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        return None


def _error_message(response: httpx.Response) -> str:
    """The PNCP's own message when it sends one (e.g. "Período ... maior que 365 dias.")."""
    try:
        body = response.json()
    except ValueError:
        body = None
    message = body.get("message") if isinstance(body, dict) else None
    detail = f": {message}" if message else ""
    return f"O PNCP respondeu com erro {response.status_code}{detail}"
