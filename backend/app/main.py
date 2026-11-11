"""FastAPI application factory."""

from fastapi import FastAPI

from app import __version__
from app.api import analyses, documents, eligibility, health, law, profiles
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import log_requests


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version=__version__)
    app.middleware("http")(log_requests)
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(analyses.router)
    app.include_router(law.router)
    app.include_router(profiles.router)
    app.include_router(eligibility.router)
    return app


app = create_app()
