"""Настройки приложения.

Значения по умолчанию — тестовый стенд из ТЗ. Боевой адрес и API-ключ в коде отсутствуют:
они берутся только из окружения или .env, который не попадает в git.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite:///./adrobot.db",
        description="SQLite для локального запуска, Postgres через DATABASE_URL",
    )
    keitaro_base_url: str = Field(
        default="https://tlgk.host",
        description="Адрес трекера без завершающего слэша",
    )
    keitaro_api_key: str = Field(default="", description="Ключ из админки: Профиль -> API ключи")
    keitaro_prefix: str = Field(
        default="kolesnikov-",
        description="Префикс кампаний, групп и офферов: стенд общий с другими кандидатами",
    )
    keitaro_timeout_seconds: float = Field(default=15.0)
    keitaro_max_retries: int = Field(default=3, description="Повторы только сетевых ошибок и 5xx")
    google_redirect_url: str = Field(default="https://www.google.com")

    @property
    def api_base(self) -> str:
        return f"{self.keitaro_base_url.rstrip('/')}/admin_api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
