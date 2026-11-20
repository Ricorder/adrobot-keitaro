from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Campaign, Offer, Stream, StreamOffer, SyncStatus
from app.keitaro.client import KeitaroClient
from app.services import mirror


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> KeitaroClient:
    settings = Settings(
        keitaro_base_url="https://track.example",
        keitaro_api_key="test-key",
        keitaro_max_retries=0,
    )
    return KeitaroClient(settings, transport=httpx.MockTransport(handler), sleep=lambda _: None)


def campaign_payload(campaign_id: int) -> dict:
    return {
        "id": campaign_id,
        "alias": f"kolesnikov-{campaign_id}",
        "name": f"kolesnikov-кампания {campaign_id}",
        "type": "position",
        "state": "active",
        "domain_id": 1813,
        "group_id": 10332,
        "traffic_source_id": 836,
    }


def geo_stream(stream_id: int, campaign_id: int) -> dict:
    return {
        "id": stream_id,
        "campaign_id": campaign_id,
        "name": "Гео RU → Google",
        "position": 1,
        "type": "regular",
        "schema": "redirect",
        "action_type": "http",
        "action_options": {"url": "https://www.google.com"},
        "state": "active",
        "weight": 0,
        "collect_clicks": True,
        "filter_or": False,
        "filters": [{"id": stream_id * 10, "name": "country", "mode": "accept", "payload": ["RU"]}],
        "offers": [],
        "triggers": [],
        "landings": [],
    }


def offers_stream(stream_id: int, campaign_id: int, offers: list[dict]) -> dict:
    return {
        "id": stream_id,
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
        "offers": offers,
        "triggers": [],
        "landings": [],
    }


def reference_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/offers"):
        return httpx.Response(
            200,
            json=[
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
                }
            ],
        )
    if path.endswith("/groups"):
        group_type = request.url.params["type"]
        return httpx.Response(
            200,
            json=[
                {
                    "id": 10332 if group_type == "campaigns" else 15,
                    "name": group_type,
                    "type": group_type,
                }
            ],
        )
    if path.endswith("/domains"):
        return httpx.Response(
            200, json=[{"id": 1813, "name": "kylovoa.com", "is_ssl": True, "state": "active"}]
        )
    if path.endswith("/traffic_sources"):
        return httpx.Response(200, json=[{"id": 836, "name": "FORTESTS", "state": "active"}])
    return httpx.Response(404, json={"error": f"неожиданный путь {path}"})


def test_sync_reference_fills_lookups(session: Session) -> None:
    counts = mirror.sync_reference(session, make_client(reference_handler))
    session.commit()
    assert counts == {"offers": 1, "groups": 2, "domains": 1, "traffic_sources": 1}
    offer = session.get(Offer, 18813)
    assert offer is not None and offer.name.startswith("18813")


def test_sync_campaigns_follows_pagination(session: Session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        total = 103
        ids = list(range(offset, min(offset + limit, total)))
        return httpx.Response(200, json=[campaign_payload(i) for i in ids])

    count = mirror.sync_campaigns(session, make_client(handler))
    session.commit()
    assert count == 103
    assert session.query(Campaign).count() == 103


def test_sync_streams_mirrors_flows_filters_and_offers(session: Session) -> None:
    session.add(Campaign(id=500, alias="a500", name="n"))
    link = {"id": 9001, "stream_id": 502, "offer_id": 18813, "state": "active", "share": 100}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[geo_stream(501, 500), offers_stream(502, 500, [link])])

    stats = mirror.sync_streams(session, make_client(handler), 500)
    session.commit()

    assert stats.streams == 2
    assert stats.offers_in_streams == 1
    geo = session.get(Stream, 501)
    assert geo is not None
    assert geo.schema == "redirect"
    assert geo.action_options == {"url": "https://www.google.com"}
    assert [f.name for f in geo.filters] == ["country"]
    row = session.get(StreamOffer, 9001)
    assert row is not None and row.sync_status == SyncStatus.SYNCED and row.share == 100


def test_offer_deleted_in_keitaro_turns_grey_not_vanished(session: Session) -> None:
    session.add(Campaign(id=500, alias="a500", name="n"))
    link = {"id": 9001, "stream_id": 502, "offer_id": 18813, "state": "active", "share": 100}
    client = make_client(
        lambda request: httpx.Response(
            200, json=[geo_stream(501, 500), offers_stream(502, 500, [link])]
        )
    )
    mirror.sync_streams(session, client, 500)
    session.commit()

    # в трекере оффер удалили, потоки пришли без него
    client2 = make_client(
        lambda request: httpx.Response(
            200, json=[geo_stream(501, 500), offers_stream(502, 500, [])]
        )
    )
    stats = mirror.sync_streams(session, client2, 500)
    session.commit()

    assert stats.removed_externally == 1
    row = session.get(StreamOffer, 9001)
    assert row is not None
    assert row.sync_status == SyncStatus.REMOVED_EXTERNALLY
    assert row.share == 0


def test_offer_back_in_keitaro_is_synced_again(session: Session) -> None:
    session.add(Campaign(id=500, alias="a500", name="n"))
    link = {"id": 9001, "stream_id": 502, "offer_id": 18813, "state": "active", "share": 100}
    mirror.sync_streams(
        session,
        make_client(lambda r: httpx.Response(200, json=[offers_stream(502, 500, [])])),
        500,
    )
    session.commit()
    mirror.sync_streams(
        session,
        make_client(lambda r: httpx.Response(200, json=[offers_stream(502, 500, [link])])),
        500,
    )
    session.commit()
    row = session.get(StreamOffer, 9001)
    assert row is not None and row.sync_status == SyncStatus.SYNCED


def test_stream_removed_upstream_is_dropped_from_mirror(session: Session) -> None:
    session.add(Campaign(id=500, alias="a500", name="n"))
    mirror.sync_streams(
        session,
        make_client(
            lambda r: httpx.Response(200, json=[geo_stream(501, 500), offers_stream(502, 500, [])])
        ),
        500,
    )
    session.commit()

    mirror.sync_streams(
        session,
        make_client(lambda r: httpx.Response(200, json=[offers_stream(502, 500, [])])),
        500,
    )
    session.commit()
    assert session.get(Stream, 501) is None
    assert list(session.scalars(select(Stream))) and session.get(Stream, 502) is not None


def test_groups_are_requested_for_both_types(session: Session) -> None:
    """Группы в Keitaro отдаются только по типу; для кампаний и офферов это два разных запроса."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/groups"):
            seen.append(request.url.params["type"])
        return reference_handler(request)

    mirror.sync_reference(session, make_client(handler))
    assert seen == ["campaigns", "offers"]
