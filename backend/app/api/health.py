from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db.models import Base
from app.deps import SettingsDep

router = APIRouter()


@router.get("/healthz")
def healthz(request: Request) -> dict:
    """Жив ли процесс и открывается ли база; Keitaro здесь не трогаем."""
    with request.app.state.engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok", "database": "reachable", "tables": len(Base.metadata.tables)}


@router.get("/api/meta")
def meta(settings: SettingsDep) -> dict:
    """Что фронт должен знать о конфигурации: префикс и адрес трекера, но не ключ."""
    return {
        "keitaro_base_url": settings.keitaro_base_url,
        "keitaro_prefix": settings.keitaro_prefix,
        "keitaro_key_configured": bool(settings.keitaro_api_key),
        "google_redirect_url": settings.google_redirect_url,
    }
