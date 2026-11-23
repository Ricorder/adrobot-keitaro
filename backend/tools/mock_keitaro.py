"""Офлайн-мок Keitaro Admin API для демо и разработки без тестового стенда.

Это не часть приложения, а инструмент: поднимается отдельным процессом и заменяет
`KEITARO_BASE_URL`. Поведение снято с настоящего стенда `tlgk.host` запросами, поэтому мок
воспроизводит и неудобные частности — иначе демо показывало бы то, чего в жизни нет:

 - `GET /campaigns` отдаёт голый массив без `total`, пагинация `limit`/`offset`;
 - `POST /traffic_sources`, `POST /domains`, `POST /offers` отвечают `403 You have no
   permission` — на стенде эти сущности можно только переиспользовать;
 - неверный или отсутствующий ключ даёт `401 {"error": "Invalid API key"}`;
 - `404` приходит как `{"error": "...", "stacktrace": null}`;
 - у потока идентификаторы есть и у фильтров, и у связок поток-оффер, а при `PUT` трекер
   сохраняет id существующей связки и выдаёт новый для добавленного оффера.

Запуск:  uvicorn tools.mock_keitaro:app --port 8099
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

API_KEY = "mock-key"
PREFIX = "/admin_api/v1"

STREAM_SCHEMAS = [
    {"value": "landings", "name": "Landing pages & offers"},
    {"value": "redirect", "name": "Direct URL"},
    {"value": "action", "name": "Action"},
]
STREAM_ACTIONS = [
    {"value": "http", "name": "HTTP Redirect", "type": "redirect", "recommended": True},
    {"value": "js", "name": "JS Redirect", "type": "redirect", "recommended": False},
    {"value": "meta", "name": "Meta Redirect", "type": "redirect", "recommended": False},
]
STREAM_TYPES = [{"value": "regular"}, {"value": "default"}, {"value": "forced"}]
COUNTRY_FILTER = {
    "name": "country",
    "label": "Countries",
    "type": "select",
    "modes": [{"value": "accept"}, {"value": "reject"}],
}


def _seed() -> dict[str, Any]:
    """Начальное состояние: справочники со стенда и кампании, похожие на реальные."""
    return {
        "next_id": 900000,
        "offers": [
            {
                "id": 18813,
                "name": "18813 Flexacil [JOINT-PE]",
                "group_id": 7183,
                "state": "active",
                "payout_type": "CPA",
                "payout_value": 0,
                "payout_currency": "USD",
                "offer_type": "local",
                "action_type": "local_file",
            },
            {
                "id": 18814,
                "name": "18814 Flexacil [JOINT-MX]",
                "group_id": 7183,
                "state": "active",
                "payout_type": "CPA",
                "payout_value": 0,
                "payout_currency": "USD",
                "offer_type": "local",
                "action_type": "local_file",
            },
            {
                "id": 18815,
                "name": "18815 Flexacil [JOINT-CO]",
                "group_id": 7183,
                "state": "active",
                "payout_type": "CPA",
                "payout_value": 0,
                "payout_currency": "USD",
                "offer_type": "local",
                "action_type": "local_file",
            },
            {
                "id": 18816,
                "name": "18816 Flexacil [JOINT-RO]",
                "group_id": 7183,
                "state": "active",
                "payout_type": "CPA",
                "payout_value": 0,
                "payout_currency": "USD",
                "offer_type": "local",
                "action_type": "local_file",
            },
        ],
        "groups": [
            {"id": 10332, "name": "FORTESTS", "type": "campaigns", "position": 1},
            {"id": 7183, "name": "JOINT", "type": "offers", "position": 1},
        ],
        "domains": [{"id": 1813, "name": "kylovoa.com", "state": "active", "is_ssl": True}],
        "traffic_sources": [{"id": 836, "name": "FORTESTS", "state": "active"}],
        "campaigns": {},
        "streams": {},
        "archive": [],
    }


def _seeded_campaign(
    state: dict[str, Any], campaign_id: int, alias: str, name: str, geo: str
) -> None:
    """Кампания в том виде, в каком её возвращает живой трекер: два потока и доли 34/33/33."""
    geo_stream_id = state["next_id"] + 1
    offer_stream_id = state["next_id"] + 2
    state["next_id"] += 2
    state["campaigns"][campaign_id] = {
        "id": campaign_id,
        "alias": alias,
        "name": name,
        "type": "position",
        "state": "active",
        "domain_id": 1813,
        "group_id": 10332,
        "traffic_source_id": 836,
    }
    state["streams"][geo_stream_id] = {
        "id": geo_stream_id,
        "campaign_id": campaign_id,
        "name": f"Гео {geo} → Google",
        "position": 1,
        "type": "regular",
        "schema": "redirect",
        "action_type": "http",
        "action_options": {"url": "https://www.google.com"},
        "state": "active",
        "weight": 0,
        "collect_clicks": True,
        "filter_or": False,
        "filters": [
            {
                "id": state["next_id"] + 10,
                "stream_id": geo_stream_id,
                "name": "country",
                "mode": "accept",
                "payload": [geo],
            }
        ],
        "offers": [],
        "triggers": [],
        "landings": [],
    }
    offers = state["offers"][:3]
    shares = [34, 33, 33]
    state["streams"][offer_stream_id] = {
        "id": offer_stream_id,
        "campaign_id": campaign_id,
        "name": "Офферы",
        "position": 2,
        "type": "regular",
        "schema": "landings",
        "action_type": "http",
        "action_options": None,
        "state": "active",
        "weight": 0,
        "collect_clicks": True,
        "filter_or": False,
        "filters": [],
        "offers": [
            {
                "id": state["next_id"] + 100 + i,
                "stream_id": offer_stream_id,
                "offer_id": offer["id"],
                "share": shares[i],
                "state": "active",
            }
            for i, offer in enumerate(offers)
        ],
        "triggers": [],
        "landings": [],
    }


def create_mock_app(*, api_key: str = API_KEY) -> FastAPI:
    state = _seed()
    _seeded_campaign(state, 216370, "demo-joint-pe", "Демо JOINT PE", "PE")
    _seeded_campaign(state, 216371, "demo-joint-mx", "Демо JOINT MX", "MX")
    state["next_id"] += 200

    app = FastAPI(title="Mock Keitaro Admin API", docs_url=None, redoc_url=None, openapi_url=None)

    def deny(resource: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": f"You have no permission to access this page - {resource}",
                "stacktrace": None,
            },
        )

    def not_found(what: str) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": what, "stacktrace": None})

    def check_key(key: str | None) -> JSONResponse | None:
        if key != api_key:
            return JSONResponse(
                status_code=401, content={"error": "Invalid API key", "stacktrace": None}
            )
        return None

    def new_id() -> int:
        state["next_id"] += 1
        return state["next_id"]

    async def body_of(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return payload if isinstance(payload, dict) else {}

    @app.middleware("http")
    async def require_key(request: Request, call_next):  # type: ignore[no-untyped-def]
        denied = check_key(request.headers.get("Api-Key"))
        if denied is not None:
            return denied
        return await call_next(request)

    # --- справочники -----------------------------------------------------------------

    @app.get(f"{PREFIX}/offers")
    def offers() -> Any:
        return state["offers"]

    @app.get(f"{PREFIX}/offers/{{offer_id}}")
    def offer(offer_id: int) -> Any:
        found = next((o for o in state["offers"] if o["id"] == offer_id), None)
        return found if found is not None else not_found("Offer not found")

    @app.post(f"{PREFIX}/offers")
    def create_offer() -> Any:
        return deny("Offers")

    @app.get(f"{PREFIX}/groups")
    def groups(type: str = Query("campaigns")) -> Any:
        return [g for g in state["groups"] if g["type"] == type]

    @app.post(f"{PREFIX}/groups")
    async def create_group(request: Request) -> Any:
        body = await body_of(request)
        created = {
            "id": new_id(),
            "name": body["name"],
            "type": body.get("type", "campaigns"),
            "position": len(state["groups"]) + 1,
        }
        state["groups"].append(created)
        return created

    @app.get(f"{PREFIX}/domains")
    def domains() -> Any:
        return state["domains"]

    @app.post(f"{PREFIX}/domains")
    def create_domain() -> Any:
        return deny("Domains")

    @app.get(f"{PREFIX}/traffic_sources")
    def traffic_sources() -> Any:
        return state["traffic_sources"]

    @app.post(f"{PREFIX}/traffic_sources")
    def create_traffic_source() -> Any:
        return deny("TrafficSources")

    @app.get(f"{PREFIX}/stream_schemas")
    def stream_schemas() -> Any:
        return STREAM_SCHEMAS

    @app.get(f"{PREFIX}/streams_actions")
    def stream_actions() -> Any:
        return STREAM_ACTIONS

    @app.get(f"{PREFIX}/stream_types")
    def stream_types() -> Any:
        return STREAM_TYPES

    @app.get(f"{PREFIX}/stream_filters")
    def stream_filters() -> Any:
        return [COUNTRY_FILTER]

    # --- кампании --------------------------------------------------------------------

    @app.get(f"{PREFIX}/campaigns")
    def campaigns(limit: int = Query(1000), offset: int = Query(0)) -> Any:
        ordered = sorted(state["campaigns"].values(), key=lambda c: c["id"], reverse=True)
        return ordered[offset : offset + limit]

    @app.get(f"{PREFIX}/campaigns/{{campaign_id}}")
    def campaign(campaign_id: int) -> Any:
        found = state["campaigns"].get(campaign_id)
        return found if found is not None else not_found("Campaign not found")

    @app.post(f"{PREFIX}/campaigns")
    async def create_campaign(request: Request) -> Any:
        body = await body_of(request)
        if not body.get("alias") or not body.get("name"):
            return JSONResponse(
                status_code=400,
                content={"error": "Alias and Name are required", "stacktrace": None},
            )
        if any(c["alias"] == body["alias"] for c in state["campaigns"].values()):
            return JSONResponse(
                status_code=400, content={"error": "Alias already exists", "stacktrace": None}
            )
        campaign_id = new_id()
        state["campaigns"][campaign_id] = {
            "id": campaign_id,
            "alias": body["alias"],
            "name": body["name"],
            "type": body.get("type", "position"),
            "state": body.get("state", "active"),
            "domain_id": body.get("domain_id"),
            "group_id": body.get("group_id"),
            "traffic_source_id": body.get("traffic_source_id"),
        }
        return state["campaigns"][campaign_id]

    @app.delete(f"{PREFIX}/campaigns/{{campaign_id}}")
    def delete_campaign(campaign_id: int) -> Any:
        removed = state["campaigns"].pop(campaign_id, None)
        if removed is None:
            return not_found("Campaign not found")
        state["archive"].append(removed)
        for stream_id in [
            s for s, v in state["streams"].items() if v["campaign_id"] == campaign_id
        ]:
            state["streams"].pop(stream_id, None)
        return [removed]

    @app.get(f"{PREFIX}/campaigns/{{campaign_id}}/streams")
    def campaign_streams(campaign_id: int) -> Any:
        if campaign_id not in state["campaigns"]:
            return not_found("Campaign not found")
        return [s for s in state["streams"].values() if s["campaign_id"] == campaign_id]

    # --- потоки ----------------------------------------------------------------------

    @app.post(f"{PREFIX}/streams")
    async def create_stream(request: Request) -> Any:
        body = await body_of(request)
        if body.get("campaign_id") not in state["campaigns"]:
            return not_found("Campaign not found")
        stream_id = new_id()
        stored = dict(body)
        stored["id"] = stream_id
        stored["filters"] = [
            {**item, "id": new_id(), "stream_id": stream_id} for item in body.get("filters", [])
        ]
        stored["offers"] = [
            {**item, "id": new_id(), "stream_id": stream_id} for item in body.get("offers", [])
        ]
        stored.setdefault("triggers", [])
        stored.setdefault("landings", [])
        state["streams"][stream_id] = stored
        return stored

    @app.put(f"{PREFIX}/streams/{{stream_id}}")
    async def update_stream(stream_id: int, request: Request) -> Any:
        stream = state["streams"].get(stream_id)
        if stream is None:
            return not_found("Stream not found")
        body = await body_of(request)
        keep = {offer["offer_id"]: offer["id"] for offer in stream.get("offers", [])}
        for key, value in body.items():
            if key in ("offers", "filters"):
                continue
            stream[key] = value
        stream["filters"] = [
            {**item, "id": item.get("id") or new_id(), "stream_id": stream_id}
            for item in body.get("filters", stream.get("filters", []))
        ]
        stream["offers"] = [
            {
                "id": keep.get(item["offer_id"], new_id()),
                "stream_id": stream_id,
                "offer_id": item["offer_id"],
                "share": item.get("share", 100),
                "state": item.get("state", "active"),
            }
            for item in body.get("offers", [])
        ]
        return {"id": stream_id}

    @app.delete(f"{PREFIX}/streams/{{stream_id}}")
    def delete_stream(stream_id: int) -> Any:
        if state["streams"].pop(stream_id, None) is None:
            return not_found("Stream not found")
        return {"success": True}

    return app


app = create_mock_app()
