"""Синхронный клиент Keitaro Admin API.

Формат ответов подсмотрен живыми запросами к стенду (см. README, раздел «Как проверялось»):
 - GET /campaigns отдаёт голый массив без total, поэтому страницы листаем до короткого ответа;
 - ошибки приходят как {"error": "...", "stacktrace": null} с HTTP 4xx;
 - обязательные поля кампании по API — alias и name.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from app.config import Settings
from app.keitaro.errors import (
    KeitaroAPIError,
    KeitaroAuthError,
    KeitaroConfigError,
    KeitaroError,
    KeitaroTransportError,
)

RETRY_STATUS = {500, 502, 503, 504}
AUTH_STATUS = {401, 403}


class KeitaroClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ) -> None:
        if not settings.keitaro_api_key:
            raise KeitaroConfigError(
                "KEITARO_API_KEY пустой: возьмите ключ в админке, Профиль -> API ключи"
            )
        self._settings = settings
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=settings.api_base,
            headers={"Api-Key": settings.keitaro_api_key},
            timeout=settings.keitaro_timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> KeitaroClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        attempt = 0
        retries = self._settings.keitaro_max_retries
        while True:
            attempt += 1
            try:
                response = self._http.request(method, path, json=json_body, params=params)
            except httpx.TransportError as exc:
                if attempt > retries:
                    raise KeitaroTransportError(f"{method} {path}: {exc}") from exc
                self._sleep(self._backoff(attempt))
                continue

            if response.status_code in AUTH_STATUS:
                # неверный ключ: повтор ничего не исправит, только замедлит ответ
                raise KeitaroAuthError(response.status_code, self._payload(response), path)
            if response.status_code in RETRY_STATUS and attempt <= retries:
                self._sleep(self._backoff(attempt))
                continue
            if response.status_code >= 400:
                raise KeitaroAPIError(response.status_code, self._payload(response), path)

            if not response.content:
                return None
            return response.json()

    @staticmethod
    def _payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text[:300]

    @staticmethod
    def _backoff(attempt: int) -> float:
        return 0.5 * (2 ** (attempt - 1))

    # --- справочники и списки -------------------------------------------------------------

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params or None)

    def iter_campaigns(self, page_size: int = 100) -> Iterator[dict[str, Any]]:
        offset = 0
        while True:
            page = self._request("GET", "/campaigns", params={"limit": page_size, "offset": offset})
            if not isinstance(page, list):
                raise KeitaroError(f"/campaigns вернул не массив: {page!r}")
            yield from page
            if len(page) < page_size:
                return
            offset += page_size

    def campaign(self, campaign_id: int) -> dict[str, Any]:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def streams(self, campaign_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams")

    def offers(self) -> list[dict[str, Any]]:
        return self._request("GET", "/offers")

    def offer(self, offer_id: int) -> dict[str, Any]:
        return self._request("GET", f"/offers/{offer_id}")

    def groups(self, group_type: str = "campaigns") -> list[dict[str, Any]]:
        return self._request("GET", "/groups", params={"type": group_type})

    def domains(self) -> list[dict[str, Any]]:
        return self._request("GET", "/domains")

    def traffic_sources(self) -> list[dict[str, Any]]:
        return self._request("GET", "/traffic_sources")

    def stream_schemas(self) -> list[dict[str, Any]]:
        return self._request("GET", "/stream_schemas")

    def stream_actions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/streams_actions")

    def stream_filters(self) -> list[dict[str, Any]]:
        return self._request("GET", "/stream_filters")

    # --- запись ---------------------------------------------------------------------------

    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/campaigns", json_body=payload)

    def update_campaign(self, campaign_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/campaigns/{campaign_id}", json_body=payload)

    def delete_campaign(self, campaign_id: int) -> Any:
        return self._request("DELETE", f"/campaigns/{campaign_id}")

    def create_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/streams", json_body=payload)

    def create_group(self, *, name: str, group_type: str) -> dict[str, Any]:
        return self._request("POST", "/groups", json_body={"name": name, "type": group_type})

    def create_traffic_source(self, *, name: str) -> dict[str, Any]:
        return self._request("POST", "/traffic_sources", json_body={"name": name})

    def update_stream(self, stream_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/streams/{stream_id}", json_body=payload)

    def delete_stream(self, stream_id: int) -> Any:
        return self._request("DELETE", f"/streams/{stream_id}")
