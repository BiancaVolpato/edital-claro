"""Loads the versioned prompt of the attestation comparison."""

import hashlib
from dataclasses import dataclass
from functools import lru_cache

from app.extraction.prompts import PROMPTS_DIR


@dataclass(frozen=True)
class EligibilityPrompt:
    version: str
    content_hash: str
    system: str
    task: str


@lru_cache
def load_eligibility_prompt(version: str) -> EligibilityPrompt:
    folder = PROMPTS_DIR / version
    system_bytes = (folder / "system.md").read_bytes()
    task_bytes = (folder / "task.md").read_bytes()
    digest = hashlib.sha256()
    for content in (system_bytes, task_bytes):
        digest.update(content.replace(b"\r\n", b"\n"))
    return EligibilityPrompt(
        version=version,
        content_hash=digest.hexdigest()[:12],
        system=system_bytes.decode("utf-8").strip(),
        task=task_bytes.decode("utf-8").strip(),
    )
