from fastapi import FastAPI

from app.api import health
from app.config import get_settings
from app.db.session import make_engine, make_session_factory


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()
    engine = make_engine(database_url or settings.database_url)

    app = FastAPI(
        title="Adrobot",
        version="0.1.0",
        description="Обёртка над Keitaro Admin API: создаватель кампаний и редактор офферов",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    app.include_router(health.router)
    return app


app = create_app()
