"""Ошибки клиента Keitaro.

Разделение важно для политики повторов: сеть и 5xx повторяем, 4xx — нет.
"""

from __future__ import annotations

from typing import Any


class KeitaroError(Exception):
    """Базовая ошибка клиента."""


class KeitaroConfigError(KeitaroError):
    """Не хватает настроек (например, API-ключ пустой)."""


class KeitaroTransportError(KeitaroError):
    """Сеть: коннект, таймаут, обрыв. Повторять можно."""


class KeitaroAPIError(KeitaroError):
    """Трекер ответил JSON с полем error или невалидным статусом."""

    def __init__(self, status: int, payload: Any, path: str) -> None:
        self.status = status
        self.path = path
        detail = payload
        if isinstance(payload, dict):
            detail = payload.get("error") or payload
        super().__init__(f"Keitaro {status} на {path}: {detail}")


class KeitaroAuthError(KeitaroAPIError):
    """401/403: ключ не подошёл — повторять бессмысленно."""
