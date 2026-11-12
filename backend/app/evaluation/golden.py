"""The golden set: hand-annotated correct answers, one JSON file per edital.

The format is described in eval/ANOTACAO.md. Values are validated against the
same types the extraction uses, so a typo in the golden set (a date in the
wrong format, an unknown enum value) is caught before any comparison runs.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.extraction.schemas import EditalExtraction, is_list_field

SCALAR_FIELDS = [name for name in EditalExtraction.model_fields if not is_list_field(name)]
LIST_FIELDS = [name for name in EditalExtraction.model_fields if is_list_field(name)]
TEMPLATE_NAME = "_template.json"


class GoldenDocument(BaseModel):
    file: str  # relative to the repository root
    sha256: str
    pncp: str | None = None
    pages: int


class GoldenAnnotation(BaseModel):
    annotator: str
    date: str
    reviewed: bool = False
    notes: str = ""


class GoldenField(BaseModel):
    value: Any = None  # None: the edital does not state it
    pages: list[int] = Field(default_factory=list)


class Golden(BaseModel):
    document: GoldenDocument
    annotation: GoldenAnnotation
    fields: dict[str, GoldenField]
    requirements: dict[str, list[str]]


@dataclass(frozen=True)
class GoldenCase:
    name: str  # file name without extension
    path: Path
    golden: Golden
    pdf: Path


class GoldenError(ValueError):
    pass


def _value_adapter(name: str) -> TypeAdapter[Any]:
    annotation = EditalExtraction.model_fields[name].annotation
    value_type = annotation.__pydantic_generic_metadata__["args"][0]  # type: ignore[union-attr]
    return TypeAdapter(value_type | None)


def validate_golden(golden: Golden) -> list[str]:
    """Problems found in an annotation (empty when it is valid)."""
    problems: list[str] = []
    missing = [name for name in SCALAR_FIELDS if name not in golden.fields]
    unknown = [name for name in golden.fields if name not in SCALAR_FIELDS]
    if missing:
        problems.append(f"campos faltando: {', '.join(missing)}")
    if unknown:
        problems.append(f"campos desconhecidos: {', '.join(unknown)}")
    for name, field in golden.fields.items():
        if name not in SCALAR_FIELDS:
            continue
        try:
            _value_adapter(name).validate_python(field.value)
        except ValidationError as exc:
            problems.append(f"{name}: valor inválido ({exc.errors()[0]['msg']})")
        if field.value is not None and not field.pages:
            problems.append(f"{name}: informe as páginas onde o valor aparece")
        if any(page < 1 or page > golden.document.pages for page in field.pages):
            problems.append(f"{name}: página fora do documento")
    missing_lists = [name for name in LIST_FIELDS if name not in golden.requirements]
    unknown_lists = [name for name in golden.requirements if name not in LIST_FIELDS]
    if missing_lists:
        problems.append(f"listas faltando: {', '.join(missing_lists)}")
    if unknown_lists:
        problems.append(f"listas desconhecidas: {', '.join(unknown_lists)}")
    return problems


def typed_value(name: str, value: Any) -> Any:
    """The golden value parsed with the extraction's own type (e.g. a str date -> date)."""
    return _value_adapter(name).validate_python(value)


def load_golden(folder: Path, repo_root: Path) -> list[GoldenCase]:
    """Every annotated edital in ``folder``, validated, sorted by name."""
    cases: list[GoldenCase] = []
    errors: list[str] = []
    for path in sorted(folder.glob("*.json")):
        if path.name == TEMPLATE_NAME:
            continue
        try:
            golden = Golden.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, ValidationError) as exc:
            errors.append(f"{path.name}: não é um gabarito válido ({exc})")
            continue
        problems = validate_golden(golden)
        pdf = repo_root / golden.document.file
        if not pdf.is_file():
            problems.append(f"PDF não encontrado: {golden.document.file}")
        elif hashlib.sha256(pdf.read_bytes()).hexdigest() != golden.document.sha256:
            problems.append("o SHA-256 do PDF não confere com o gabarito")
        if problems:
            errors.extend(f"{path.name}: {problem}" for problem in problems)
            continue
        cases.append(GoldenCase(name=path.stem, path=path, golden=golden, pdf=pdf))
    if errors:
        raise GoldenError("\n".join(errors))
    return cases
