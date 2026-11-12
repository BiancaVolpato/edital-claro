"""FastAPI application factory."""

from fastapi import FastAPI

from app import __version__
from app.api import analyses, documents, eligibility, health, law, pncp, profiles
from app.core.config import get_settings
from app.core.demo import demo_guard
from app.core.logging import configure_logging
from app.core.middleware import log_requests
from app.core.rate_limit import RateLimiter, rate_limit_middleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version=__version__)
    # Registered first, so it runs inside the logging middleware: refused requests
    # are logged too, with their 429 status.
    limiter = RateLimiter(
        settings.rate_limit_per_minute,
        settings.rate_limit_costly_per_hour,
        settings.trusted_proxies,
        settings.proxy_token.get_secret_value() if settings.proxy_token else None,
    )
    app.state.rate_limiter = limiter
    if settings.demo_mode:
        # Innermost: refused demo actions still count against the rate limit.
        app.middleware("http")(demo_guard)
    app.middleware("http")(rate_limit_middleware(limiter))
    app.middleware("http")(log_requests)
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(analyses.router)
    app.include_router(law.router)
    app.include_router(profiles.router)
    app.include_router(eligibility.router)
    app.include_router(pncp.router)
    return app


app = create_app()
