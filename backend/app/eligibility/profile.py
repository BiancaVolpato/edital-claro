"""The company profile: what a bidder declares about itself.

Everything the eligibility check compares in code is a typed field here
(money, dates, quantities with a unit), so no number has to be read from free
text on the company side. Free text is kept only where the comparison is about
meaning: the description of the services in a technical attestation.
"""

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CompanySize = Literal["ME", "EPP", "demais"]
Council = Literal["CREA", "CAU"]
CertificateKind = Literal["federal", "estadual", "municipal", "fgts", "trabalhista", "falencia"]
# Units of attested quantities. Requirements in other units are converted when
# possible (km -> m, kg -> t); see ``requirements.parse_quantities``.
QuantityUnit = Literal["m2", "m3", "m", "t", "un"]

CERTIFICATE_LABELS: dict[CertificateKind, str] = {
    "federal": "Certidão de regularidade com a Fazenda Federal (tributos federais e dívida ativa)",
    "estadual": "Certidão de regularidade com a Fazenda Estadual",
    "municipal": "Certidão de regularidade com a Fazenda Municipal",
    "fgts": "Certificado de regularidade do FGTS (CRF)",
    "trabalhista": "Certidão Negativa de Débitos Trabalhistas (CNDT)",
    "falencia": "Certidão negativa de falência e recuperação judicial",
}
UNIT_LABELS: dict[QuantityUnit, str] = {"m2": "m²", "m3": "m³", "m": "m", "t": "t", "un": "un"}


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


class AttestedQuantity(BaseModel):
    service: str = Field(min_length=3, description="Serviço, como descrito no atestado.")
    quantity: float = Field(gt=0, description="Quantidade executada.")
    unit: QuantityUnit


class TechnicalAttestation(BaseModel):
    description: str = Field(min_length=3, description="Obra ou serviço do atestado.")
    issuer: str | None = Field(default=None, description="Quem emitiu (contratante).")
    quantities: list[AttestedQuantity] = Field(default_factory=list)


class Certificate(BaseModel):
    kind: CertificateKind
    valid_until: dt.date = Field(description="Data de validade da certidão.")


class ProfessionalRegistration(BaseModel):
    council: Council
    number: str = Field(min_length=1, max_length=50)
    state: str | None = Field(default=None, min_length=2, max_length=2, description="UF")
    valid_until: dt.date | None = Field(
        default=None, description="Validade da certidão de registro e quitação, se houver."
    )

    @field_validator("state")
    @classmethod
    def _upper_state(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CompanyProfileData(BaseModel):
    """Body of POST/PUT /profiles."""

    name: str = Field(min_length=2, max_length=200, description="Razão social.")
    cnpj: str | None = Field(default=None, description="CNPJ, com ou sem pontuação.")
    size: CompanySize = Field(description="Porte: ME, EPP ou demais.")
    cnaes: list[str] = Field(
        default_factory=list, description="CNAEs, ex.: '4211-1/01' (guardados só com dígitos)."
    )
    share_capital: float | None = Field(default=None, ge=0, description="Capital social, em R$.")
    net_worth: float | None = Field(
        default=None, description="Patrimônio líquido do último balanço, em R$."
    )
    attestations: list[TechnicalAttestation] = Field(default_factory=list)
    certificates: list[Certificate] = Field(default_factory=list)
    registration: ProfessionalRegistration | None = Field(
        default=None, description="Registro da empresa no CREA ou no CAU."
    )

    @field_validator("cnpj")
    @classmethod
    def _valid_cnpj(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        digits = _digits(value)
        if len(digits) != 14:
            raise ValueError("O CNPJ deve ter 14 dígitos.")
        return digits

    @field_validator("cnaes")
    @classmethod
    def _valid_cnaes(cls, values: list[str]) -> list[str]:
        cnaes = []
        for value in values:
            digits = _digits(value)
            if len(digits) != 7:
                raise ValueError(f"CNAE inválido: '{value}'. Use 7 dígitos, ex.: 4211-1/01.")
            if digits not in cnaes:
                cnaes.append(digits)
        return cnaes


def format_cnae(digits: str) -> str:
    return f"{digits[:4]}-{digits[4]}/{digits[5:]}"
