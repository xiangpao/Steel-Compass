from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from . import __version__
from .auth import hash_password
from .config import get_settings
from .core.errors import CalculationInputError
from .database import Base, SessionLocal, engine
from .models import User
from .routers import auth_routes, calculation_routes, project_routes, scene_routes


class BootstrapConfigError(RuntimeError):
    """Startup configuration that would leave a fresh install without an admin."""


def bootstrap_database() -> None:
    Base.metadata.create_all(bind=engine)
    settings = get_settings()
    if not settings.bootstrap_admin_username or not settings.bootstrap_admin_password:
        return
    with SessionLocal() as db:
        existing = db.scalar(
            select(User).where(User.username == settings.bootstrap_admin_username)
        )
        if existing is not None:
            return
        # Fail fast with a readable cause: skipping would start a server that
        # nobody can log in to, and the health check would still pass.
        try:
            password_hash = hash_password(settings.bootstrap_admin_password)
        except ValueError as exc:
            raise BootstrapConfigError(
                "STEEL_COMPASS_BOOTSTRAP_ADMIN_PASSWORD is too short to create the "
                f"bootstrap admin {settings.bootstrap_admin_username!r}: {exc}"
            ) from exc
        db.add(
            User(
                username=settings.bootstrap_admin_username,
                display_name="系统管理员",
                password_hash=password_hash,
                is_admin=True,
                must_change_password=True,
            )
        )
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_database()
    yield


settings = get_settings()
request_logger = logging.getLogger("steel_compass.requests")
# uvicorn configures only its own loggers; without a handler the INFO-level
# structured request log is dropped by the root WARNING threshold.
if not request_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    request_logger.addHandler(_handler)
    request_logger.setLevel(logging.INFO)
    request_logger.propagate = False
app = FastAPI(
    title="Steel-Compass V2 API",
    version=__version__,
    lifespan=lifespan,
)


@app.middleware("http")
async def structured_request_log(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        request_logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
                ensure_ascii=False,
            )
        )
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(CalculationInputError)
async def calculation_input_error_handler(
    _: Request, exc: CalculationInputError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": exc.as_dict()},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


app.include_router(auth_routes.router, prefix="/api/v1")
app.include_router(calculation_routes.router, prefix="/api/v1")
app.include_router(project_routes.router, prefix="/api/v1")
app.include_router(auth_routes.router, prefix="/api/v2")
app.include_router(calculation_routes.router, prefix="/api/v2")
app.include_router(project_routes.router, prefix="/api/v2")
app.include_router(scene_routes.router, prefix="/api/v2")
