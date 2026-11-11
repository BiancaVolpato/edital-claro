"""PNCP endpoints: search procurements and import an edital for analysis."""

import datetime as dt
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.documents import DocumentRead
from app.core.config import get_settings
from app.db.models import DocumentStatus
from app.db.session import get_session
from app.ingestion.service import process_document
from app.pncp.client import PncpClient, PncpError, ResponseCache
from app.pncp.schemas import DEFAULT_MODALITIES, PncpFile, Procurement
from app.pncp.service import (
    PncpInputError,
    PncpNotFoundError,
    SearchFilters,
    import_procurement,
    search,
)

router = APIRouter(prefix="/pncp", tags=["pncp"])

SessionDep = Annotated[Session, Depends(get_session)]


@lru_cache
def get_pncp_client() -> PncpClient:
    settings = get_settings()
    return PncpClient(
        consulta_url=settings.pncp_consulta_url,
        api_url=settings.pncp_api_url,
        timeout_seconds=settings.pncp_timeout_seconds,
        max_retries=settings.pncp_max_retries,
        min_interval_seconds=settings.pncp_min_interval_seconds,
        cache=ResponseCache(settings.pncp_cache_dir, settings.pncp_cache_ttl_seconds),
    )


ClientDep = Annotated[PncpClient, Depends(get_pncp_client)]


def _bad_gateway(exc: PncpError) -> HTTPException:
    # 4xx from the PNCP means the request was refused (its message explains why).
    if exc.status_code is not None and 400 <= exc.status_code < 500:
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"PNCP indisponível. {exc}")


class SearchResponse(BaseModel):
    results: list[Procurement]
    total_matches: int
    scanned: int
    truncated: bool
    warnings: list[str]


@router.get("/search")
def search_pncp(
    client: ClientDep,
    data_inicial: Annotated[dt.date, Query(description="Início do período de publicação")],
    data_final: Annotated[dt.date, Query(description="Fim do período (até 365 dias)")],
    uf: Annotated[str | None, Query(description="Sigla da UF, ex.: SC")] = None,
    municipio: Annotated[str | None, Query(description="Nome do município")] = None,
    codigo_ibge: Annotated[str | None, Query(description="Código IBGE do município")] = None,
    modalidade: Annotated[
        list[int] | None,
        Query(description="Códigos de modalidade do PNCP (padrão: 4 e 5, concorrências)"),
    ] = None,
    q: Annotated[
        str | None, Query(description="Palavras que devem aparecer no objeto, ex.: pavimentação")
    ] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SearchResponse:
    """Search procurements published in the PNCP. Responses are cached locally."""
    filters = SearchFilters(
        date_from=data_inicial,
        date_to=data_final,
        modalities=tuple(modalidade or DEFAULT_MODALITIES),
        uf=uf or None,
        ibge_code=codigo_ibge or None,
        municipality=municipio or None,
        keywords=q or None,
    )
    try:
        outcome = search(client, filters, limite)
    except PncpInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except PncpError as exc:
        raise _bad_gateway(exc) from None
    return SearchResponse(
        results=outcome.results,
        total_matches=outcome.total_matches,
        scanned=outcome.scanned,
        truncated=outcome.truncated,
        warnings=outcome.warnings,
    )


class ImportRequest(BaseModel):
    numero_controle: str = Field(
        description="Número de controle PNCP, ex.: 82939422000191-1-000153/2026"
    )
    sequencial_documento: int | None = Field(
        default=None,
        ge=1,
        description="Arquivo a importar; sem ele, importa os arquivos do tipo Edital.",
    )


class ImportedDocument(BaseModel):
    document: DocumentRead
    file: PncpFile
    duplicate: bool


class ImportResponse(BaseModel):
    procurement: Procurement
    documents: list[ImportedDocument]
    skipped: list[str]


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
def import_from_pncp(
    body: ImportRequest, background_tasks: BackgroundTasks, session: SessionDep, client: ClientDep
) -> ImportResponse:
    """Download the edital of a procurement and ingest it, as an upload would.

    Poll GET /documents/{id} and, once ready, start POST /documents/{id}/analyze.
    """
    try:
        outcome = import_procurement(
            session, client, body.numero_controle, body.sequencial_documento
        )
    except PncpInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except PncpNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except PncpError as exc:
        raise _bad_gateway(exc) from None
    if not outcome.imported:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Nenhum arquivo pôde ser importado. " + " ".join(outcome.skipped),
        )
    for item in outcome.imported:
        if item.created or item.document.status == DocumentStatus.FAILED.value:
            background_tasks.add_task(process_document, item.document.id)
    return ImportResponse(
        procurement=outcome.procurement,
        documents=[
            ImportedDocument(
                document=DocumentRead.model_validate(item.document),
                file=item.file,
                duplicate=not item.created,
            )
            for item in outcome.imported
        ],
        skipped=outcome.skipped,
    )
