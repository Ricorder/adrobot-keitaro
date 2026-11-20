from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import campaigns, health
from app.config import Settings, get_settings
from app.db.session import make_engine, make_session_factory
from app.keitaro.client import KeitaroClient
from app.keitaro.errors import (
    KeitaroAPIError,
    KeitaroAuthError,
    KeitaroConfigError,
    KeitaroNotFoundError,
    KeitaroTransportError,
)
from app.services import creator, editor, mirror, weights

# Ошибка пользователя или нашего правила -> 400, текст идёт прямо в интерфейс.
# ValueError сюда не включён нарочно: сервисы уже оборачивают его в свои классы, а ловить
# чужие ValueError означало прятать настоящие баги за «плохим запросом».
CLIENT_ERRORS = (creator.CreatorError, editor.EditorError, weights.WeightConflict)
# Проблема трекера или канала до него -> 502/504, чтобы фронт не путал их с неверными данными.
# Порядок важен: KeitaroNotFoundError является KeitaroAPIError, поэтому стоит раньше.
UPSTREAM_STATUS: list[tuple[type[Exception], int]] = [
    (KeitaroConfigError, 503),
    (KeitaroAuthError, 502),
    (KeitaroNotFoundError, 404),
    (KeitaroAPIError, 502),
    (mirror.KeitaroShapeError, 502),
    (KeitaroTransportError, 504),
]


def create_app(database_url: str | None = None, settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine = make_engine(database_url or app_settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        yield
        client: KeitaroClient | None = getattr(app.state, "keitaro_client", None)
        if client is not None:
            client.close()

    app = FastAPI(
        title="Adrobot",
        version="0.1.0",
        description="Обёртка над Keitaro Admin API: создаватель кампаний и редактор офферов",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    app.include_router(health.router)
    app.include_router(campaigns.router)

    async def client_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    async def upstream_error_handler(request: Request, exc: Exception) -> JSONResponse:
        code = next((status for cls, status in UPSTREAM_STATUS if isinstance(exc, cls)), 502)
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    for error in CLIENT_ERRORS:
        app.add_exception_handler(error, client_error_handler)
    for error, _ in UPSTREAM_STATUS:
        app.add_exception_handler(error, upstream_error_handler)

    return app


app = create_app()
