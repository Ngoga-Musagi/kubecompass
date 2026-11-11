"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_agent, routes_core, routes_discovery, routes_graph_agenda
from app.config.conferences import load_conferences
from app.config.settings import get_settings
from app.infrastructure.elasticsearch import SearchUnavailableError
from app.infrastructure.logging import configure_logging
from app.services.container import get_container

log = logging.getLogger("kubecompass.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Warm the embedding model and read models so the first user request is fast."""
    try:
        container = get_container()
        for cid in load_conferences():
            container.read_models.get(cid)
        if container.embeddings.available:
            container.embeddings.embed_query("warm up")
    except Exception as exc:  # the API still starts; endpoints report degraded/503 states
        log.warning("Startup warm-up incomplete: %s", exc)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        lifespan=lifespan,
        title="KubeCompass API",
        version="0.1.0",
        description="AI-native conference discovery: search, knowledge graph, recommendations, "
        "agenda and assistant over official conference data.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Guest-Id", "Authorization"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        log.info(
            "request",
            extra={
                "request_id": rid,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": int((time.perf_counter() - start) * 1000),
            },
        )
        return response

    @app.exception_handler(SearchUnavailableError)
    async def search_unavailable(_: Request, exc: SearchUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "search_unavailable",
                    "message": "The search service is temporarily unavailable. "
                    "Please retry shortly.",
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "error", "message": str(exc.detail)}
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request",
                    "fields": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()],
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "internal_error", "message": "Something went wrong on our side."}
            },
        )

    app.include_router(routes_core.router)
    app.include_router(routes_discovery.router)
    app.include_router(routes_graph_agenda.router)
    app.include_router(routes_agent.router)
    return app


app = create_app()
