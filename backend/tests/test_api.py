import httpx
import pytest
from fastapi.testclient import TestClient
from test_creator import FakeKeitaro

from app.config import Settings
from app.deps import get_keitaro_client
from app.keitaro.client import KeitaroClient
from app.keitaro.errors import KeitaroConfigError
from app.main import create_app

SETTINGS = Settings(
    keitaro_base_url="https://track.example",
    keitaro_api_key="test-key",
    keitaro_prefix="kolesnikov-",
    keitaro_max_retries=0,
    google_redirect_url="https://www.google.com",
)


@pytest.fixture
def tracker() -> FakeKeitaro:
    fake = FakeKeitaro()
    # второй оффер нужен редактором: добавлять в поток тот же самый — ошибка, а не тест
    fake.offers.append({"id": 18814, "name": "18814 Flexacil второй", "state": "active"})
    return fake


@pytest.fixture
def app(tmp_path, tracker: FakeKeitaro):
    application = create_app(f"sqlite:///{tmp_path / 'api.db'}", settings=SETTINGS)
    from app.db.models import Base

    Base.metadata.create_all(application.state.engine)
    client = KeitaroClient(
        SETTINGS, transport=httpx.MockTransport(tracker.handle), sleep=lambda _: None
    )
    application.dependency_overrides[get_keitaro_client] = lambda: client
    return application


@pytest.fixture
def api(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def payload(name: str = "Кампания PR", geo: str = "PE", offer_id: int = 18813) -> dict:
    return {"name": name, "geo": geo, "offer_id": offer_id}


def test_create_campaign_returns_two_flows(api: TestClient, tracker: FakeKeitaro) -> None:
    response = api.post("/api/campaigns", json=payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["alias"].startswith("kolesnikov-")
    assert body["created_by_us"] is True
    assert [s["schema"] for s in body["streams"]] == ["redirect", "landings"]
    geo_flow, offer_flow = body["streams"]
    assert geo_flow["filters"] == [{"name": "country", "mode": "accept", "payload": ["PE"]}]
    assert [o["share"] for o in offer_flow["offers"]] == [100]
    assert offer_flow["yellow"] is False


def test_create_validates_geo_and_offer(api: TestClient) -> None:
    bad_geo = api.post("/api/campaigns", json=payload(geo="XX"))
    assert bad_geo.status_code == 400
    assert "ISO 3166" in bad_geo.json()["detail"]

    bad_offer = api.post("/api/campaigns", json=payload(offer_id=999999))
    assert bad_offer.status_code == 400
    assert "не найден" in bad_offer.json()["detail"]


def test_missing_key_is_service_error(api: TestClient, app) -> None:
    def broken() -> KeitaroClient:
        raise KeitaroConfigError("KEITARO_API_KEY пустой")

    app.dependency_overrides[get_keitaro_client] = broken
    response = api.post("/api/campaigns", json=payload(name="Без ключа"))
    assert response.status_code == 503
    assert "KEITARO_API_KEY" in response.json()["detail"]


def test_idempotency_header_prevents_duplicate(api: TestClient, tracker: FakeKeitaro) -> None:
    headers = {"Idempotency-Key": "req-42"}
    first = api.post("/api/campaigns", json=payload(name="Одна и та же"), headers=headers)
    second = api.post("/api/campaigns", json=payload(name="Одна и та же"), headers=headers)
    assert first.json()["id"] == second.json()["id"]
    assert len(tracker.campaigns) == 1


def test_list_campaigns_filters_by_text_and_ownership(api: TestClient) -> None:
    api.post("/api/campaigns", json=payload(name="Нужная PR"))
    api.post("/api/sync")
    churists = api.get("/api/campaigns", params={"q": "Чужая"})
    assert churists.status_code == 200

    ours = api.get("/api/campaigns", params={"only_ours": True}).json()
    assert any(c["name"] == "Нужная PR" for c in ours)


def test_open_campaign_pulls_streams(api: TestClient, tracker: FakeKeitaro) -> None:
    created = api.post("/api/campaigns", json=payload()).json()
    detail = api.get(f"/api/campaigns/{created['id']}")
    assert detail.status_code == 200
    offer_flow = next(s for s in detail.json()["streams"] if s["schema"] == "landings")
    assert offer_flow["offers"][0]["offer_id"] == 18813
    assert offer_flow["offers"][0]["sync_status"] == "synced"


def test_editor_cycle_add_pin_remove_push(api: TestClient, tracker: FakeKeitaro) -> None:
    created = api.post("/api/campaigns", json=payload()).json()
    flow = next(s for s in created["streams"] if s["schema"] == "landings")
    stream_id = flow["id"]

    duplicate = api.post(f"/api/streams/{stream_id}/offers", json={"offer_id": 18813})
    assert duplicate.status_code == 400 and "уже стоит" in duplicate.json()["detail"]

    added = api.post(f"/api/streams/{stream_id}/offers", json={"offer_id": 18814})
    assert added.status_code == 200, added.text
    assert sorted(o["share"] for o in added.json()) == [50, 50]
    assert any(o["yellow"] for o in added.json())

    view = api.get(f"/api/campaigns/{created['id']}").json()
    current = next(s for s in view["streams"] if s["id"] == stream_id)
    second = next(o for o in current["offers"] if o["offer_id"] == 18814)

    pinned = api.put(f"/api/streams/offers/{second['id']}/pin", json={"share": 30})
    assert pinned.status_code == 204
    current = _flow(api, created["id"], stream_id)
    assert {o["offer_id"]: o["share"] for o in current["offers"]} == {18813: 70, 18814: 30}
    assert current["unassigned_percent"] == 0

    first = next(o for o in current["offers"] if o["offer_id"] == 18813)
    assert api.delete(f"/api/streams/offers/{first['id']}").status_code == 204
    current = _flow(api, created["id"], stream_id)
    # закреплённые 30 % остаются, доливать их до ста мы не вправе — дырка видна отдельно
    assert current["unassigned_percent"] == 70

    pushed = api.post(f"/api/streams/{stream_id}/push")
    assert pushed.status_code == 200, pushed.text
    assert pushed.json()["yellow"] is False
    sent = tracker.put_payloads[-1]["offers"]
    assert [o["offer_id"] for o in sent] == [18814]
    after = _flow(api, created["id"], stream_id)
    assert [o["offer_id"] for o in after["offers"]] == [18814]
    assert after["offers"][0]["link_id"] is not None


def _flow(api: TestClient, campaign_id: int, stream_id: int) -> dict:
    view = api.get(f"/api/campaigns/{campaign_id}").json()
    return next(s for s in view["streams"] if s["id"] == stream_id)


def test_push_empty_flow_is_refused(api: TestClient, tracker: FakeKeitaro) -> None:
    created = api.post("/api/campaigns", json=payload()).json()
    flow = next(s for s in created["streams"] if s["schema"] == "landings")
    for offer in flow["offers"]:
        api.delete(f"/api/streams/offers/{offer['id']}")
    response = api.post(f"/api/streams/{flow['id']}/push")
    assert response.status_code == 400
    assert "не осталось ни одного оффера" in response.json()["detail"]


def test_offers_search_from_mirror(api: TestClient) -> None:
    api.post("/api/sync")
    found = api.get("/api/offers", params={"q": "18813"}).json()
    assert [o["id"] for o in found] == [18813]

    missing = api.get("/api/offers", params={"q": "999999"}).json()
    assert missing == []


def test_health_and_meta_still_work(api: TestClient) -> None:
    assert api.get("/healthz").json()["tables"] >= 10
    meta = api.get("/api/meta").json()
    assert meta["keitaro_prefix"] == "kolesnikov-"


def test_unexpected_transport_failure_is_gateway_error(app, tracker: FakeKeitaro) -> None:
    def broken_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нет связи", request=request)

    client = KeitaroClient(
        SETTINGS, transport=httpx.MockTransport(broken_handler), sleep=lambda _: None
    )
    app.dependency_overrides[get_keitaro_client] = lambda: client
    with TestClient(app) as api:
        response = api.post("/api/campaigns", json=payload())
        assert response.status_code == 504
        assert "нет связи" in response.json()["detail"]
