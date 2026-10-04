"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kontor.api import actuals, auth, cashflow, catalog, depot, financings, outlook, tax
from kontor.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Kontor", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(cashflow.router)
    app.include_router(financings.router)
    app.include_router(outlook.router)
    app.include_router(depot.router)
    app.include_router(catalog.router)
    app.include_router(actuals.router)
    app.include_router(tax.router)
    return app


app = create_app()
