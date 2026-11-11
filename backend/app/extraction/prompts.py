"""Loads a versioned prompt set from ``backend/prompts/``.

A prompt set is a folder (e.g. ``extraction/v1``) holding the system prompt and
the definition of the field groups. Its version and a hash of its files are
stored with every analysis, so any result can be traced to the exact prompt
that produced it. To change a prompt, add a new version folder instead of
editing an existing one.
"""

import hashlib
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.extraction.schemas import EditalExtraction

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@dataclass(frozen=True)
class FieldGroup:
    name: str
    fields: tuple[str, ...]
    queries: tuple[str, ...]
    keywords: tuple[re.Pattern[str], ...]
    lead_chunks: int
    top_k: int
    # Also include the first chunk of every annex (where its title is).
    annex_openings: bool
    task: str


@dataclass(frozen=True)
class PromptSet:
    version: str
    content_hash: str  # sha256 of the prompt files, first 12 hex chars
    system: str
    groups: tuple[FieldGroup, ...]


def fold(text: str) -> str:
    """Lowercase and strip accents, for accent-insensitive keyword matching."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn").casefold()


@lru_cache
def load_prompt_set(version: str) -> PromptSet:
    folder = PROMPTS_DIR / version
    system_bytes = (folder / "system.md").read_bytes()
    groups_bytes = (folder / "groups.toml").read_bytes()

    groups = tuple(
        FieldGroup(
            name=name,
            fields=tuple(spec["fields"]),
            queries=tuple(spec["queries"]),
            keywords=tuple(re.compile(pattern, re.MULTILINE) for pattern in spec["keywords"]),
            lead_chunks=spec["lead_chunks"],
            top_k=spec["top_k"],
            annex_openings=spec.get("annex_openings", False),
            task=spec["task"].strip(),
        )
        for name, spec in tomllib.loads(groups_bytes.decode("utf-8"))["groups"].items()
    )
    _check_field_coverage(groups)

    # Line endings are normalized so the hash is the same on Windows and Linux checkouts.
    digest = hashlib.sha256()
    for content in (system_bytes, groups_bytes):
        digest.update(content.replace(b"\r\n", b"\n"))
    return PromptSet(
        version=version,
        content_hash=digest.hexdigest()[:12],
        system=system_bytes.decode("utf-8").strip(),
        groups=groups,
    )


def _check_field_coverage(groups: tuple[FieldGroup, ...]) -> None:
    """Every schema field must belong to exactly one group."""
    assigned = [field for group in groups for field in group.fields]
    expected = set(EditalExtraction.model_fields)
    if len(assigned) != len(set(assigned)) or set(assigned) != expected:
        missing = sorted(expected - set(assigned))
        unknown = sorted(set(assigned) - expected)
        duplicated = sorted({field for field in assigned if assigned.count(field) > 1})
        raise ValueError(
            f"prompt groups do not match the schema: missing={missing} "
            f"unknown={unknown} duplicated={duplicated}"
        )
