"""Demo mode: the public demonstration only shows analyses that are already done.

Uploads, PNCP imports and new analyses cost money (LLM calls) and need the
embedding model, which the demo image leaves out to fit a free 512 MB instance.
The law search needs the model too. Those routes answer 403 with an explanation;
everything else (reading analyses, profiles, eligibility checks without the LLM,
PNCP search) works as usual. See ADR-039.
"""

import re
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

DEMO_BLOCKED_ROUTES: list[tuple[str, re.Pattern[str]]] = [
    ("POST", re.compile(r"^/documents/?$")),
    ("POST", re.compile(r"^/documents/[^/]+/analyze$")),
    ("POST", re.compile(r"^/pncp/import$")),
    ("GET", re.compile(r"^/law/search$")),
]

DEMO_MESSAGE = (
    "Esta ação está desativada na demonstração pública, para não gerar custo com a IA. "
    "Veja os editais já analisados ou rode o projeto localmente (instruções no README)."
)


def is_blocked_in_demo(method: str, path: str) -> bool:
    return any(method == m and pattern.match(path) for m, pattern in DEMO_BLOCKED_ROUTES)


async def demo_guard(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if is_blocked_in_demo(request.method, request.url.path):
        return JSONResponse({"detail": DEMO_MESSAGE}, status_code=403)
    return await call_next(request)
