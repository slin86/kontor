"""FastAPI application factory."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kontor.api import (
    actuals,
    auth,
    cashflow,
    catalog,
    depot,
    financings,
    household,
    outlook,
    people,
    properties,
    tax,
    wealth,
)
from kontor.api import (
    ai as ai_api,
)
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
        # the image build sets KONTOR_VERSION to the release tag, e.g. sha-1a2b3c4
        return {"status": "ok", "version": os.environ.get("KONTOR_VERSION", "dev")}

    app.include_router(auth.router)
    app.include_router(cashflow.router)
    app.include_router(financings.router)
    app.include_router(outlook.router)
    app.include_router(depot.router)
    app.include_router(catalog.router)
    app.include_router(actuals.router)
    app.include_router(tax.router)
    app.include_router(people.router)
    app.include_router(properties.router)
    app.include_router(wealth.router)
    app.include_router(household.router)
    app.include_router(ai_api.router)
    return app


app = create_app()
