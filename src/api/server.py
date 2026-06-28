from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes.documentos import router as documentos_router
from src.api.routes.fotos import router as fotos_router
from src.api.routes.health import router as health_router
from src.api.routes.medicoes import router as medicoes_router
from src.api.routes.obras import router as obras_router
from src.api.routes.openclaw import router as openclaw_router
from src.api.routes.orcamento import router as orcamento_router
from src.api.routes.tasks import router as tasks_router
from src.api.routes.triagem import router as triagem_router
from src.config.env import get_settings
from src.core.errors import NotFoundError, ObrabotError, UnauthorizedError


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Obrabot API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin] if settings.cors_origin != "*" else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(tasks_router)
    app.include_router(openclaw_router)
    app.include_router(triagem_router)
    app.include_router(obras_router)
    app.include_router(documentos_router)
    app.include_router(fotos_router)
    app.include_router(orcamento_router)
    app.include_router(medicoes_router)

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(_request: Request, exc: UnauthorizedError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(ObrabotError)
    async def obrabot_error_handler(_request: Request, exc: ObrabotError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app


app = create_app()
