"""Loads the versioned prompt set of the interpretive risk analysis."""

import hashlib
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache

from app.extraction.prompts import PROMPTS_DIR, FieldGroup


@dataclass(frozen=True)
class RiskTopic:
    name: str
    # How the edital excerpts are selected (same mechanism as the extraction).
    selection: FieldGroup
    law_queries: tuple[str, ...]
    law_k: int
    task: str


@dataclass(frozen=True)
class RiskPromptSet:
    version: str
    content_hash: str
    system: str
    topics: tuple[RiskTopic, ...]


@lru_cache
def load_risk_prompt_set(version: str) -> RiskPromptSet:
    folder = PROMPTS_DIR / version
    system_bytes = (folder / "system.md").read_bytes()
    topics_bytes = (folder / "topics.toml").read_bytes()

    topics = tuple(
        RiskTopic(
            name=name,
            selection=FieldGroup(
                name=name,
                fields=(),
                queries=tuple(spec["queries"]),
                keywords=tuple(re.compile(pattern, re.MULTILINE) for pattern in spec["keywords"]),
                lead_chunks=0,
                top_k=spec["top_k"],
                annex_openings=False,
                task=spec["task"].strip(),
            ),
            law_queries=tuple(spec["law_queries"]),
            law_k=spec["law_k"],
            task=spec["task"].strip(),
        )
        for name, spec in tomllib.loads(topics_bytes.decode("utf-8"))["topics"].items()
    )

    digest = hashlib.sha256()
    for content in (system_bytes, topics_bytes):
        digest.update(content.replace(b"\r\n", b"\n"))
    return RiskPromptSet(
        version=version,
        content_hash=digest.hexdigest()[:12],
        system=system_bytes.decode("utf-8").strip(),
        topics=topics,
    )
