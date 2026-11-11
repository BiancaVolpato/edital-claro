"""Search procurements in the PNCP and import their edital into the ingestion."""

import datetime as dt
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentSource
from app.extraction.prompts import fold
from app.ingestion.service import NotAPdfError, register_document
from app.pncp.client import PncpClient, PncpError
from app.pncp.schemas import EDITAL_DOCUMENT_TYPE, MODALITIES, PncpFile, Procurement

logger = logging.getLogger(__name__)

# Limits stated by the PNCP API de Consulta (OpenAPI and its error messages).
MAX_PERIOD_DAYS = 365
PAGE_SIZE = 50
_CONTROL_NUMBER = re.compile(r"^(\d{14})-\d+-(\d{1,6})/(\d{4})$")


class PncpInputError(ValueError):
    """The request cannot be sent to the PNCP as it is (message in Portuguese)."""


class PncpNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class SearchFilters:
    date_from: dt.date
    date_to: dt.date
    modalities: tuple[int, ...]
    uf: str | None = None
    ibge_code: str | None = None
    municipality: str | None = None  # name, matched locally
    keywords: str | None = None  # every word must appear in the object, matched locally

    def validate(self) -> None:
        if self.date_to < self.date_from:
            raise PncpInputError("A data final é anterior à data inicial.")
        if (self.date_to - self.date_from).days > MAX_PERIOD_DAYS:
            raise PncpInputError(f"O PNCP aceita períodos de até {MAX_PERIOD_DAYS} dias.")
        unknown = [m for m in self.modalities if m not in MODALITIES]
        if unknown:
            raise PncpInputError(f"Modalidade desconhecida: {unknown}.")
        if not self.modalities:
            raise PncpInputError("Informe ao menos uma modalidade.")
        if self.uf is not None and not re.fullmatch(r"[A-Za-z]{2}", self.uf):
            raise PncpInputError("A UF deve ter duas letras, ex.: SC.")
        if self.ibge_code is not None and not re.fullmatch(r"\d{7}", self.ibge_code):
            raise PncpInputError("O código IBGE do município tem 7 dígitos.")


@dataclass
class SearchOutcome:
    results: list[Procurement]
    total_matches: int
    scanned: int  # procurements read from the PNCP before filtering
    truncated: bool  # some pages were not read (page limit)
    warnings: list[str] = field(default_factory=list)


def _matches(procurement: Procurement, filters: SearchFilters, raw_extra: str) -> bool:
    if filters.municipality and fold(filters.municipality.strip()) != fold(
        procurement.municipality or ""
    ):
        return False
    if filters.keywords:
        haystack = fold(f"{procurement.object} {raw_extra}")
        return all(word in haystack for word in fold(filters.keywords).split())
    return True


def search(client: PncpClient, filters: SearchFilters, limit: int) -> SearchOutcome:
    """Search by publication date in the PNCP, filtering by keyword and municipality here.

    The API filters by period, modality, UF and IBGE code, but has no text search,
    so every page of the period is read (up to a page limit) and filtered locally.
    """
    filters.validate()
    max_pages = get_settings().pncp_search_max_pages
    found: dict[str, Procurement] = {}
    scanned = 0
    truncated = False
    for modality in filters.modalities:
        page = 1
        while True:
            params: dict[str, str | int] = {
                "dataInicial": filters.date_from.strftime("%Y%m%d"),
                "dataFinal": filters.date_to.strftime("%Y%m%d"),
                "codigoModalidadeContratacao": modality,
                "pagina": page,
                "tamanhoPagina": PAGE_SIZE,
            }
            if filters.uf:
                params["uf"] = filters.uf.upper()
            if filters.ibge_code:
                params["codigoMunicipioIbge"] = filters.ibge_code
            body = client.search_by_publication(params)
            if not body:  # 204: nothing published in the period
                break
            for item in body.get("data") or []:
                scanned += 1
                procurement = Procurement.from_api(item)
                if _matches(procurement, filters, item.get("informacaoComplementar") or ""):
                    found.setdefault(procurement.control_number, procurement)
            total_pages = int(body.get("totalPaginas") or 0)
            if page >= total_pages:
                break
            if page >= max_pages:
                truncated = True
                break
            page += 1

    results = sorted(found.values(), key=lambda p: p.published_at or dt.datetime.min, reverse=True)
    warnings = []
    if truncated:
        warnings.append(
            f"A busca leu só as primeiras {max_pages} páginas de cada modalidade; reduza o "
            "período ou filtre por UF ou município para ver todos os resultados."
        )
    return SearchOutcome(
        results=results[:limit],
        total_matches=len(results),
        scanned=scanned,
        truncated=truncated,
        warnings=warnings,
    )


def parse_control_number(value: str) -> tuple[str, int, int]:
    """'82939422000191-1-000153/2026' -> ('82939422000191', 2026, 153)."""
    match = _CONTROL_NUMBER.match(value.strip())
    if not match:
        raise PncpInputError(
            "Número de controle PNCP inválido. Formato esperado: CNPJ-1-SEQUENCIAL/ANO, "
            "ex.: 82939422000191-1-000153/2026."
        )
    cnpj, sequential, year = match.groups()
    return cnpj, int(year), int(sequential)


@dataclass
class ImportedFile:
    document: Document
    created: bool  # False when this file had already been imported or uploaded
    file: PncpFile


@dataclass
class ImportOutcome:
    procurement: Procurement
    imported: list[ImportedFile]
    skipped: list[str]  # files that could not be imported, with the reason


def source_ref(procurement: Procurement, file: PncpFile) -> str:
    return f"{procurement.control_number}#arquivo-{file.sequential}"


def _select_files(files: list[PncpFile], document: int | None) -> list[PncpFile]:
    if document is not None:
        chosen = [f for f in files if f.sequential == document]
        if not chosen:
            raise PncpNotFoundError(f"A contratação não tem o arquivo {document}.")
        return chosen
    editais = [f for f in files if f.active and f.type_id == EDITAL_DOCUMENT_TYPE]
    if not editais:
        available = ", ".join(f"{f.sequential} ({f.type_name or 'sem tipo'})" for f in files)
        raise PncpNotFoundError(
            "A contratação não tem arquivo do tipo Edital"
            + (f". Arquivos disponíveis: {available}." if available else ".")
        )
    return editais


def import_procurement(
    session: Session, client: PncpClient, control_number: str, document: int | None = None
) -> ImportOutcome:
    """Download the edital (or the chosen file) and register it for ingestion.

    The caller starts the ingestion of the documents with ``created`` true (or that
    had failed before), exactly as for an upload.
    """
    cnpj, year, sequential = parse_control_number(control_number)
    raw = client.get_procurement(cnpj, year, sequential)
    if not raw:
        raise PncpNotFoundError("Contratação não encontrada no PNCP.")
    procurement = Procurement.from_api(raw)
    files = [PncpFile.from_api(item) for item in client.list_files(cnpj, year, sequential)]

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    imported: list[ImportedFile] = []
    skipped: list[str] = []
    for file in _select_files(files, document):
        ref = source_ref(procurement, file)
        existing = session.scalar(select(Document).where(Document.source_ref == ref))
        if existing is not None:  # already imported: no new download
            imported.append(ImportedFile(existing, created=False, file=file))
            continue
        try:
            content = client.download(
                client.file_url(cnpj, year, sequential, file.sequential), max_bytes
            )
        except PncpError as exc:
            skipped.append(f"Arquivo {file.sequential} ({file.title}): {exc}")
            continue
        try:
            registered = register_document(
                session,
                content,
                filename=f"{file.title or 'edital'}.pdf",
                source=DocumentSource.PNCP,
                source_ref=ref,
            )
        except NotAPdfError:
            kind = "um arquivo ZIP" if content[:2] == b"PK" else "um arquivo que não é PDF"
            skipped.append(
                f"Arquivo {file.sequential} ({file.title}): é {kind}; baixe-o no PNCP e envie "
                "os PDFs pelo upload."
            )
            continue
        doc = registered.document
        if registered.created:
            doc.meta = {
                **(doc.meta or {}),
                "pncp": {
                    **procurement.model_dump(mode="json"),
                    "file": file.model_dump(mode="json"),
                },
            }
            session.commit()
        imported.append(ImportedFile(doc, created=registered.created, file=file))
    logger.info(
        "pncp import",
        extra={
            "control_number": procurement.control_number,
            "imported": [str(i.document.id) for i in imported],
            "skipped": len(skipped),
        },
    )
    return ImportOutcome(procurement=procurement, imported=imported, skipped=skipped)
