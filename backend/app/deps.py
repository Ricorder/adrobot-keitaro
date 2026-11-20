from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.keitaro.client import KeitaroClient


def get_db(request: Request) -> Iterator[Session]:
    """Сессия на время запроса; коммит и откат — ответственность сервисного слоя."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_keitaro_client(request: Request) -> Iterator[KeitaroClient]:
    """Клиент на приложение: пул соединений переиспользуется, закрывается на остановке.

    Создаётся лениво — иначе отсутствие KEITARO_API_KEY ломало бы /healthz и тесты,
    которым трекер не нужен.
    """
    client: KeitaroClient | None = getattr(request.app.state, "keitaro_client", None)
    if client is None:
        client = KeitaroClient(request.app.state.settings)
        request.app.state.keitaro_client = client
    yield client


# Аннотированные псевдонимы для роутов: Depends в значениях по умолчанию FastAPI считает
# антипаттерном (ruff B008), поэтому тип с зависимостью объявлен здесь один раз.
SessionDep = Annotated[Session, Depends(get_db)]
KeitaroDep = Annotated[KeitaroClient, Depends(get_keitaro_client)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
