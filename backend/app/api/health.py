"""Health endpoint."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.db.session import check_database

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    database: Literal["ok", "unavailable"]


@router.get("/health")
def health(database_ok: Annotated[bool, Depends(check_database)]) -> HealthResponse:
    """Liveness probe.

    Always answers 200 while the process is up; the ``database`` field reports
    whether PostgreSQL is reachable, so a database outage is visible without
    making the orchestrator restart a healthy API process.
    """
    return HealthResponse(
        status="ok",
        version=__version__,
        database="ok" if database_ok else "unavailable",
    )
