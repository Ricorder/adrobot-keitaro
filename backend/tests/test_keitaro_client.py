import json
from collections.abc import Callable

import httpx
import pytest

from app.config import Settings
from app.keitaro.client import KeitaroClient
from app.keitaro.errors import (
    KeitaroAPIError,
    KeitaroAuthError,
    KeitaroConfigError,
    KeitaroTransportError,
)


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "keitaro_base_url": "https://track.example",
        "keitaro_api_key": "test-key",
        "keitaro_timeout_seconds": 1.0,
        "keitaro_max_retries": 2,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], **overrides: object
) -> KeitaroClient:
    settings = make_settings(**overrides)
    return KeitaroClient(settings, transport=httpx.MockTransport(handler), sleep=lambda _: None)


def test_empty_key_raises_before_any_request() -> None:
    with pytest.raises(KeitaroConfigError, match="KEITARO_API_KEY"):
        KeitaroClient(make_settings(keitaro_api_key=""))


def test_sends_api_key_header_and_json_body() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["header"] = request.headers.get("Api-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 1})

    client = make_client(handler)
    assert client.create_campaign({"alias": "a", "name": "n"}) == {"id": 1}
    assert seen["header"] == "test-key"
    assert seen["body"] == {"alias": "a", "name": "n"}


def test_auth_error_is_not_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error": "Invalid API key"})

    client = make_client(handler)
    with pytest.raises(KeitaroAuthError, match="Invalid API key"):
        client.offers()
    assert len(calls) == 1


def test_server_error_is_retried_then_succeeds() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=[])

    client = make_client(handler)
    assert client.offers() == []
    assert len(calls) == 3


def test_retries_are_bounded() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={"error": "boom"})

    client = make_client(handler, keitaro_max_retries=2)
    with pytest.raises(KeitaroAPIError, match="500"):
        client.offers()
    assert len(calls) == 3


def test_transport_error_becomes_keitaro_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    client = make_client(handler, keitaro_max_retries=1)
    with pytest.raises(KeitaroTransportError):
        client.domains()


def test_campaign_pages_are_followed_until_short_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        total = 103
        ids = list(range(offset, min(offset + limit, total)))
        return httpx.Response(200, json=[{"id": i} for i in ids])

    client = make_client(handler)
    ids = [c["id"] for c in client.iter_campaigns(page_size=100)]
    assert len(ids) == 103
    assert ids[:2] == [0, 1]
    assert ids[-1] == 102
