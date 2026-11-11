"""Law search endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.law.search import SearchMode, search_law

router = APIRouter(prefix="/law", tags=["law"])


class LawHitRead(BaseModel):
    citation: str  # e.g. "Lei 14.133/2021, Art. 67, § 1º"
    identifier: str
    kind: str
    article: int
    heading: str
    text: str
    score: float
    semantic_rank: int | None
    lexical_rank: int | None


@router.get("/search")
def search(
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query(min_length=3, max_length=500, description="Pergunta ou tema")],
    k: Annotated[int, Query(ge=1, le=20)] = 5,
    mode: SearchMode = "hybrid",
) -> list[LawHitRead]:
    """Search the Lei 14.133/2021 and return the best-matching provisions."""
    try:
        hits = search_law(session, q, k, mode=mode)
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "A base da lei não está disponível. Rode as migrações e a indexação da lei.",
        ) from None
    return [
        LawHitRead(
            citation=hit.citation,
            identifier=hit.identifier,
            kind=hit.kind,
            article=hit.article,
            heading=hit.heading,
            text=hit.text,
            score=hit.score,
            semantic_rank=hit.semantic_rank,
            lexical_rank=hit.lexical_rank,
        )
        for hit in hits
    ]
