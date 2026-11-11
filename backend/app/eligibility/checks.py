"""Checks decided by code: dates, amounts, registrations and company size.

Each check compares a typed field of the profile with what the requirement
asks. When the profile lacks the data, or the requirement's number cannot be
read, the answer is "nao_verificavel" with the reason: the check never guesses.
"""

import datetime as dt
from dataclasses import dataclass, field

from app.eligibility.profile import CERTIFICATE_LABELS, CompanyProfileData, format_cnae
from app.eligibility.requirements import (
    Requirement,
    certificate_kinds,
    councils,
    is_conditional_on_indices,
    mentions_capital,
    mentions_net_worth,
    parse_money,
    parse_percent,
)
from app.eligibility.schemas import STATUS_ORDER, RequirementStatus

# CNAE divisions of construction (section F of the CNAE 2.3 classification).
CONSTRUCTION_DIVISIONS = ("41", "42", "43")


@dataclass(frozen=True)
class CheckContext:
    profile: CompanyProfileData
    reference_date: dt.date
    estimated_value: float | None  # only when backed by a confirmed quote


@dataclass(frozen=True)
class Outcome:
    status: RequirementStatus
    reason: str
    evidence: list[str] = field(default_factory=list)


def brl(value: float) -> str:
    """1234567.8 -> 'R$ 1.234.567,80'."""
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


def br_date(value: dt.date) -> str:
    return value.strftime("%d/%m/%Y")


def worst(outcomes: list[Outcome]) -> Outcome:
    """Combine the outcomes of the parts of one requirement."""
    status = min((o.status for o in outcomes), key=STATUS_ORDER.__getitem__)
    return Outcome(
        status=status,
        reason=" ".join(o.reason for o in outcomes),
        evidence=[item for o in outcomes for item in o.evidence],
    )


def check_certificates(requirement: Requirement, context: CheckContext) -> Outcome:
    outcomes: list[Outcome] = []
    for kind in certificate_kinds(requirement.text):
        label = CERTIFICATE_LABELS[kind]
        held = [c for c in context.profile.certificates if c.kind == kind]
        if not held:
            outcomes.append(
                Outcome(
                    "nao_verificavel",
                    f"{label}: não cadastrada no perfil; emita antes da abertura.",
                )
            )
            continue
        latest = max(held, key=lambda c: c.valid_until)
        evidence = [f"{label}, válida até {br_date(latest.valid_until)}"]
        if latest.valid_until < context.reference_date:
            outcomes.append(
                Outcome(
                    "nao_atende",
                    f"{label}: vence em {br_date(latest.valid_until)}, antes de "
                    f"{br_date(context.reference_date)}; renove antes da abertura.",
                    evidence,
                )
            )
        else:
            outcomes.append(
                Outcome("atende", f"{label}: válida até {br_date(latest.valid_until)}.", evidence)
            )
    return worst(outcomes)


def check_registration(requirement: Requirement, context: CheckContext) -> Outcome:
    registration = context.profile.registration
    if registration is None:
        return Outcome("nao_atende", "O perfil não tem registro da empresa no CREA nem no CAU.")
    evidence = [f"Registro no {registration.council} nº {registration.number}"]
    accepted = councils(requirement.text)
    if accepted and registration.council not in accepted:
        return Outcome(
            "nao_atende",
            f"O edital pede registro no {' ou '.join(sorted(accepted))}; o perfil tem registro "
            f"no {registration.council}.",
            evidence,
        )
    if registration.valid_until and registration.valid_until < context.reference_date:
        return Outcome(
            "nao_atende",
            f"A certidão de registro no {registration.council} vence em "
            f"{br_date(registration.valid_until)}, antes de {br_date(context.reference_date)}.",
            evidence,
        )
    return Outcome("atende", f"Empresa registrada no {registration.council}.", evidence)


def _required_amount(requirement: Requirement, context: CheckContext) -> tuple[float, str] | str:
    """The minimum amount and how it was obtained, or why it cannot be determined."""
    amounts = parse_money(requirement.text)
    if amounts:
        return amounts[0], brl(amounts[0])
    percents = parse_percent(requirement.text)
    if not percents:
        return "O valor mínimo exigido não foi identificado no texto da exigência."
    if context.estimated_value is None:
        return (
            f"A exigência é de {percents[0]:g}% do valor estimado, mas o valor estimado não foi "
            "extraído com citação confirmada."
        )
    # Rounded to cents, as the amount would be written in the edital.
    amount = round(context.estimated_value * percents[0] / 100, 2)
    return amount, f"{brl(amount)} ({percents[0]:g}% de {brl(context.estimated_value)})"


def check_capital_or_net_worth(requirement: Requirement, context: CheckContext) -> Outcome:
    required = _required_amount(requirement, context)
    if isinstance(required, str):
        return Outcome("nao_verificavel", required)
    amount, described = required

    # "capital social ou patrimônio líquido": meeting either one is enough.
    options = [
        (label, value)
        for label, value, mentioned in (
            ("capital social", context.profile.share_capital, mentions_capital(requirement.text)),
            ("patrimônio líquido", context.profile.net_worth, mentions_net_worth(requirement.text)),
        )
        if mentioned
    ]
    evidence = [f"{label}: {brl(value)}" for label, value in options if value is not None]
    met = [label for label, value in options if value is not None and value >= amount]
    if met:
        return Outcome("atende", f"{met[0].capitalize()} igual ou acima de {described}.", evidence)
    if any(value is None for _, value in options):
        missing = " e ".join(label for label, value in options if value is None)
        return Outcome(
            "nao_verificavel", f"O perfil não informa {missing}; mínimo: {described}.", evidence
        )
    shortfall = "; ".join(
        f"{label} de {brl(value)}" for label, value in options if value is not None
    )
    if is_conditional_on_indices(requirement.text):
        return Outcome(
            "nao_verificavel",
            f"{shortfall.capitalize()}, abaixo de {described}. A exigência só vale se os índices "
            "contábeis ficarem abaixo do limite, e o perfil não tem os índices.",
            evidence,
        )
    return Outcome(
        "nao_atende", f"{shortfall.capitalize()}, abaixo do mínimo de {described}.", evidence
    )


def check_company_size(context: CheckContext) -> Outcome:
    size = context.profile.size
    if size in ("ME", "EPP"):
        return Outcome("atende", f"A empresa é {size}.", [f"Porte: {size}"])
    return Outcome(
        "nao_atende",
        "A licitação é exclusiva para ME e EPP, e o perfil não é de ME nem de EPP.",
        [f"Porte: {size}"],
    )


def check_cnpj(context: CheckContext) -> Outcome:
    if context.profile.cnpj:
        return Outcome("atende", "CNPJ informado no perfil.", [f"CNPJ {context.profile.cnpj}"])
    return Outcome("nao_verificavel", "O perfil não informa o CNPJ.")


def check_company_purpose(context: CheckContext) -> Outcome:
    cnaes = context.profile.cnaes
    if not cnaes:
        return Outcome("nao_verificavel", "O perfil não informa CNAEs.")
    construction = [format_cnae(c) for c in cnaes if c[:2] in CONSTRUCTION_DIVISIONS]
    if construction:
        return Outcome(
            "atende",
            "O perfil tem CNAE de construção (divisões 41 a 43); confira se o objeto social "
            "registrado cobre o objeto da licitação.",
            [f"CNAE {c}" for c in construction],
        )
    return Outcome(
        "nao_verificavel",
        "Nenhum CNAE do perfil é de construção (divisões 41 a 43); confira se o objeto social "
        "cobre o objeto da licitação.",
        [f"CNAE {format_cnae(c)}" for c in cnaes],
    )


# Requirements the profile has no data for: say what to do instead of guessing.
MANUAL_REASONS = {
    "indices_contabeis": "O perfil não tem os índices contábeis (liquidez, solvência); "
    "calcule-os com o último balanço.",
    "balanco": "Documento contábil que o perfil não guarda; confira com o contador.",
    "declaracao": "Declaração emitida pela própria empresa, conforme o modelo do edital.",
    "visita_tecnica": "Visita técnica: confira se é obrigatória e o prazo para agendar.",
    "outro": "O perfil não tem dados para conferir esta exigência; confira manualmente.",
}
