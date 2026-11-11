"""What the application reads from the PNCP, mapped to stable names.

Only the fields the application uses are read; the PNCP field each one comes
from is noted beside it (see ``RecuperarCompraPublicacaoDTO`` and
``RecuperarDadosDocumentoCompraDTO`` in the official OpenAPI documents).
"""

import datetime as dt
from typing import Any

from pydantic import BaseModel

# Codes of the PNCP domain table of modalities (GET /api/pncp/v1/modalidades,
# read on 11/11/2026). Kept here so a search does not depend on one more request.
MODALITIES: dict[int, str] = {
    1: "Leilão - Eletrônico",
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
    8: "Dispensa",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
    13: "Leilão - Presencial",
    14: "Inaplicabilidade da Licitação",
    15: "Chamada pública",
    16: "Concorrência – Eletrônica Internacional",
    17: "Concorrência – Presencial Internacional",
    18: "Pregão – Eletrônico Internacional",
    19: "Pregão – Presencial Internacional",
}
# Works (obras) are procured by concorrência (Lei 14.133, art. 29, parágrafo único).
DEFAULT_MODALITIES = (4, 5)
# "Edital" in the PNCP domain table of document types (GET /api/pncp/v1/tipos-documentos).
EDITAL_DOCUMENT_TYPE = 2


def _datetime(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None


class Procurement(BaseModel):
    control_number: str  # numeroControlePNCP, e.g. "82939422000191-1-000153/2026"
    cnpj: str  # orgaoEntidade.cnpj
    year: int  # anoCompra
    sequential: int  # sequencialCompra
    number: str | None  # numeroCompra, as numbered by the agency
    process: str | None  # processo
    object: str  # objetoCompra
    modality_id: int | None  # modalidadeId
    modality_name: str | None  # modalidadeNome
    agency: str | None  # orgaoEntidade.razaoSocial
    unit: str | None  # unidadeOrgao.nomeUnidade
    municipality: str | None  # unidadeOrgao.municipioNome
    uf: str | None  # unidadeOrgao.ufSigla
    ibge_code: str | None  # unidadeOrgao.codigoIbge
    estimated_value: float | None  # valorTotalEstimado
    status: str | None  # situacaoCompraNome
    published_at: dt.datetime | None  # dataPublicacaoPncp
    # Period for sending proposals, as registered in the PNCP. The session date in
    # the edital itself may differ; the analysis reads it from the document.
    proposals_from: dt.datetime | None  # dataAberturaProposta
    proposals_until: dt.datetime | None  # dataEncerramentoProposta

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Procurement":
        agency = data.get("orgaoEntidade") or {}
        unit = data.get("unidadeOrgao") or {}
        return cls(
            control_number=data["numeroControlePNCP"],
            cnpj=agency.get("cnpj") or "",
            year=data["anoCompra"],
            sequential=data["sequencialCompra"],
            number=data.get("numeroCompra"),
            process=data.get("processo"),
            object=(data.get("objetoCompra") or "").strip(),
            modality_id=data.get("modalidadeId"),
            modality_name=data.get("modalidadeNome"),
            agency=agency.get("razaoSocial"),
            unit=unit.get("nomeUnidade"),
            municipality=unit.get("municipioNome"),
            uf=unit.get("ufSigla"),
            ibge_code=unit.get("codigoIbge"),
            estimated_value=data.get("valorTotalEstimado"),
            status=data.get("situacaoCompraNome"),
            published_at=_datetime(data.get("dataPublicacaoPncp")),
            proposals_from=_datetime(data.get("dataAberturaProposta")),
            proposals_until=_datetime(data.get("dataEncerramentoProposta")),
        )


class PncpFile(BaseModel):
    sequential: int  # sequencialDocumento
    title: str  # titulo
    type_id: int | None  # tipoDocumentoId
    type_name: str | None  # tipoDocumentoNome
    active: bool  # statusAtivo

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "PncpFile":
        return cls(
            sequential=data["sequencialDocumento"],
            title=(data.get("titulo") or "").strip(),
            type_id=data.get("tipoDocumentoId"),
            type_name=data.get("tipoDocumentoNome"),
            active=bool(data.get("statusAtivo", True)),
        )
