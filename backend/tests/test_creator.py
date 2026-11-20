import json
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Campaign, CreationStatus
from app.keitaro.client import KeitaroClient
from app.services import creator


class FakeKeitaro:
    """Мини-трекер: помнит созданные сущности и умеет отказывать на выбранном шаге."""

    def __init__(self) -> None:
        self.campaigns: dict[int, dict] = {}
        self.streams: dict[int, dict] = {}
        self.stream_requests: list[dict] = []
        self.groups: list[dict] = [{"id": 1, "name": "VZ adrobot test", "type": "campaigns"}]
        self.sources: list[dict] = [{"id": 2, "name": "FORTESTS"}]
        self.domains: list[dict] = [
            {"id": 1813, "name": "kylovoa.com", "state": "active", "is_ssl": True}
        ]
        self.offers: list[dict] = [{"id": 18813, "name": "Flexacil", "state": "active"}]
        self.next_id = 7000
        self.fail_on_stream_position: int | None = None
        self.fail_delete = False
        self.deleted_campaigns: list[int] = []
        self.put_payloads: list[dict] = []

    def _new_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}

        if path.endswith("/offers") and request.method == "GET":
            return httpx.Response(200, json=self.offers)
        if "/offers/" in path and request.method == "GET":
            offer_id = int(path.rsplit("/", 1)[1])
            found = [o for o in self.offers if o["id"] == offer_id]
            if not found:
                return httpx.Response(404, json={"error": "Offer not found", "stacktrace": None})
            return httpx.Response(200, json=found[0])
        if path.endswith("/domains"):
            return httpx.Response(200, json=self.domains)
        if path.endswith("/traffic_sources") and request.method == "GET":
            return httpx.Response(200, json=self.sources)
        if path.endswith("/traffic_sources") and request.method == "POST":
            created = {"id": self._new_id(), "name": body["name"], "state": "active"}
            self.sources.append(created)
            return httpx.Response(200, json=created)
        if path.endswith("/groups") and request.method == "GET":
            group_type = request.url.params["type"]
            return httpx.Response(200, json=[g for g in self.groups if g["type"] == group_type])
        if path.endswith("/groups") and request.method == "POST":
            created = {"id": self._new_id(), "name": body["name"], "type": body["type"]}
            self.groups.append(created)
            return httpx.Response(200, json=created)
        if path.endswith("/streams") and request.method == "POST":
            position = body.get("position")
            if self.fail_on_stream_position == position:
                return httpx.Response(400, json={"error": "Cannot create flow", "stacktrace": None})
            stream_id = self._new_id()
            self.stream_requests.append(body)
            stored = dict(body)
            stored["id"] = stream_id
            # живой Keitaro присваивает id и фильтрам, и связкам поток-оффер
            stored["filters"] = [
                {**item, "id": self._new_id(), "stream_id": stream_id, "oid": stream_id}
                for item in body.get("filters", [])
            ]
            stored["offers"] = [
                {**item, "id": self._new_id(), "stream_id": stream_id}
                for item in body.get("offers", [])
            ]
            self.streams[stream_id] = stored
            return httpx.Response(200, json={"id": stream_id})
        if "/streams" in path and path.endswith("/streams"):
            campaign_id = int(path.rsplit("/", 2)[1])
            return httpx.Response(
                200, json=[s for s in self.streams.values() if s["campaign_id"] == campaign_id]
            )
        if path.endswith("/campaigns") and request.method == "POST":
            if any(c["alias"] == body["alias"] for c in self.campaigns.values()):
                return httpx.Response(400, json={"error": "Alias already exists"})
            campaign_id = self._new_id()
            self.campaigns[campaign_id] = {**body, "id": campaign_id, "state": "active"}
            return httpx.Response(200, json={"id": campaign_id})
        if path.endswith("/campaigns") and request.method == "GET":
            return httpx.Response(200, json=list(self.campaigns.values()))
        if request.method == "PUT" and "/streams/" in path:
            stream_id = int(path.rsplit("/", 1)[1])
            self.put_payloads.append(body)
            stream = self.streams[stream_id]
            keep = {o["offer_id"]: o["id"] for o in stream.get("offers", [])}
            stream["offers"] = [
                {
                    **item,
                    "id": keep.get(item["offer_id"], self._new_id()),
                    "stream_id": stream_id,
                }
                for item in body.get("offers", [])
            ]
            for key in (
                "name",
                "position",
                "type",
                "schema",
                "action_type",
                "action_options",
                "state",
                "weight",
                "collect_clicks",
                "filter_or",
                "filters",
            ):
                if key in body:
                    stream[key] = body[key]
            return httpx.Response(200, json={"id": stream_id})
        if request.method == "DELETE" and "/campaigns/" in path:
            campaign_id = int(path.rsplit("/", 1)[1])
            if self.fail_delete:
                return httpx.Response(400, json={"error": "Cannot delete campaign"})
            self.campaigns.pop(campaign_id, None)
            self.deleted_campaigns.append(campaign_id)
            return httpx.Response(200, json={"success": True})
        raise AssertionError(f"неожиданный запрос {request.method} {path}")


def make_setup(tracker: FakeKeitaro, session: Session) -> tuple[KeitaroClient, Settings]:
    settings = Settings(
        keitaro_base_url="https://track.example",
        keitaro_api_key="test-key",
        keitaro_prefix="kolesnikov-",
        keitaro_max_retries=0,
    )
    client = KeitaroClient(
        settings, transport=httpx.MockTransport(tracker.handle), sleep=lambda _: None
    )
    return client, settings


def create(session: Session, tracker: FakeKeitaro, **overrides: Any) -> creator.CreationResult:
    client, settings = make_setup(tracker, session)
    params: dict[str, Any] = {"name": "Осень PE", "geo": "PE", "offer_id": 18813}
    params.update(overrides)
    return creator.create_campaign(session, client, settings, **params)


def test_happy_path_creates_campaign_and_two_flows(session: Session) -> None:
    tracker = FakeKeitaro()
    result = create(session, tracker)

    campaign = tracker.campaigns[result.campaign_id]
    assert campaign["name"] == "Осень PE"
    assert campaign["alias"].startswith("kolesnikov-")
    assert campaign["domain_id"] == 1813
    assert campaign["group_id"] and campaign["traffic_source_id"]

    geo_flow, offer_flow = tracker.stream_requests
    assert geo_flow["schema"] == "redirect"
    assert geo_flow["action_options"] == {"url": "https://www.google.com"}
    assert geo_flow["filters"] == [{"name": "country", "mode": "accept", "payload": ["PE"]}]
    assert offer_flow["schema"] == "landings"
    assert offer_flow["offers"] == [{"offer_id": 18813, "share": 100, "state": "active"}]
    assert (geo_flow["position"], offer_flow["position"]) == (1, 2)


def test_created_campaign_lands_in_mirror(session: Session) -> None:
    tracker = FakeKeitaro()
    result = create(session, tracker)
    stored = session.get(Campaign, result.campaign_id)
    assert stored is not None
    assert stored.created_by_us is True
    assert {s.schema for s in stored.streams} == {"redirect", "landings"}


def test_group_and_source_are_created_once(session: Session) -> None:
    tracker = FakeKeitaro()
    create(session, tracker)
    assert [g["name"] for g in tracker.groups if g["name"].startswith("kolesnikov-")] == [
        "kolesnikov-group"
    ]
    assert [s["name"] for s in tracker.sources if s["name"].startswith("kolesnikov-")] == [
        "kolesnikov-source"
    ]

    create(session, tracker)
    assert len([g for g in tracker.groups if g["name"] == "kolesnikov-group"]) == 1
    assert len([s for s in tracker.sources if s["name"] == "kolesnikov-source"]) == 1


def test_unknown_geo_code_stops_before_any_write(session: Session) -> None:
    tracker = FakeKeitaro()
    with pytest.raises(creator.CreatorError, match="ISO 3166"):
        create(session, tracker, geo="XX")
    assert tracker.campaigns == {}
    assert tracker.streams == {}


def test_geo_with_wrong_shape_is_rejected(session: Session) -> None:
    tracker = FakeKeitaro()
    with pytest.raises(creator.CreatorError, match="из двух букв"):
        create(session, tracker, geo="RUS")
    assert tracker.campaigns == {}


def test_same_name_without_key_is_not_created_twice(session: Session) -> None:
    """Повтор без ключа идемпотентности тоже не должен плодить копии на общем стенде."""
    tracker = FakeKeitaro()
    first = create(session, tracker)
    second = create(session, tracker)
    assert second.campaign_id == first.campaign_id
    assert second.reused is True
    assert len(tracker.campaigns) == 1


def test_unknown_offer_stops_before_any_write(session: Session) -> None:
    tracker = FakeKeitaro()
    with pytest.raises(creator.CreatorError, match="не найден"):
        create(session, tracker, offer_id=999999)
    assert tracker.campaigns == {}


def test_second_flow_failure_deletes_the_campaign(session: Session) -> None:
    tracker = FakeKeitaro()
    tracker.fail_on_stream_position = 2
    with pytest.raises(creator.CreatorError, match="удалена"):
        create(session, tracker)
    assert len(tracker.deleted_campaigns) == 1
    assert tracker.campaigns == {}

    record = session.query(creator.CreationRequest).one()
    assert record.status == CreationStatus.PARTIAL
    assert record.campaign_id is None


def test_no_active_domain_is_reported_clearly(session: Session) -> None:
    tracker = FakeKeitaro()
    tracker.domains = [{"id": 1, "name": "old.example", "state": "disabled"}]
    with pytest.raises(creator.CreatorError, match="активного домена"):
        create(session, tracker)


def test_same_idempotency_key_does_not_create_second_campaign(session: Session) -> None:
    tracker = FakeKeitaro()
    client, settings = make_setup(tracker, session)
    first = creator.create_campaign(
        session,
        client,
        settings,
        name="Осень PE",
        geo="PE",
        offer_id=18813,
        idempotency_key="req-1",
    )
    second = creator.create_campaign(
        session,
        client,
        settings,
        name="Осень PE",
        geo="PE",
        offer_id=18813,
        idempotency_key="req-1",
    )
    assert second.campaign_id == first.campaign_id
    assert second.reused is True
    assert len(tracker.campaigns) == 1


def test_compensation_failure_is_recorded_truthfully(session: Session) -> None:
    """Если удалить кампанию не удалось, запись не должна врать, что она удалена."""
    tracker = FakeKeitaro()
    tracker.fail_on_stream_position = 2
    tracker.fail_delete = True

    with pytest.raises(creator.CreatorError, match="осталась на стенде"):
        create(session, tracker)

    record = session.query(creator.CreationRequest).one()
    assert record.campaign_id is not None
    assert record.status == CreationStatus.PARTIAL
    assert len(tracker.campaigns) == 1


def test_retry_finishes_the_campaign_instead_of_duplicating(session: Session) -> None:
    """Осиротевшая кампания сразу попадает в зеркало, поэтому повтор её доделывает."""
    tracker = FakeKeitaro()
    tracker.fail_on_stream_position = 2
    tracker.fail_delete = True
    with pytest.raises(creator.CreatorError, match="осталась на стенде"):
        create(session, tracker)
    assert len(tracker.campaigns) == 1
    assert len(tracker.stream_requests) == 1

    tracker.fail_on_stream_position = None
    tracker.fail_delete = False
    result = create(session, tracker)
    assert len(tracker.campaigns) == 1
    assert result.reused is True
    assert len(tracker.stream_requests) == 2
    stored = session.get(Campaign, result.campaign_id)
    assert stored is not None and {s.schema for s in stored.streams} == {"redirect", "landings"}


def test_repeat_with_other_geo_is_refused_not_silently_reused(session: Session) -> None:
    tracker = FakeKeitaro()
    first = create(session, tracker, name="Лима PE", geo="PE", offer_id=18813)
    assert len(tracker.stream_requests) == 2

    with pytest.raises(creator.CreatorError, match="уже ловит PE, а запрошено RU"):
        create(session, tracker, name="Лима PE", geo="RU", offer_id=18813)
    assert len(tracker.campaigns) == 1
    assert len(tracker.stream_requests) == 2
    assert first.campaign_id in tracker.campaigns
