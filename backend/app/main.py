import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import applications, catalog, health, ingestion, lenders, runs
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Lender Matching Platform",
        description="Evaluates equipment-finance applications against lender credit policies.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, error: RequestValidationError) -> JSONResponse:
        # Same body shape as api.errors.fail, so the UI has one error format to handle.
        errors = [
            {"path": ".".join(str(p) for p in e["loc"][1:]), "label": e["msg"]}
            for e in error.errors()
        ]
        detail = {"message": "Some values are not valid.", "errors": errors}
        return JSONResponse(status_code=422, content={"detail": detail})

    for router in (
        health.router,
        applications.router,
        applications.samples_router,
        runs.router,
        lenders.router,
        catalog.router,
        ingestion.router,
    ):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
