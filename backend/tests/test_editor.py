import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Campaign, Stream, StreamOffer, SyncStatus
from app.keitaro.client import KeitaroClient
from app.services import editor, mirror


class Remote:
    """Кусок трекера, который важен редактору: потоки, офферы и приём PUT."""

    def __init__(self, campaign_id: int, streams: list[dict]) -> None:
        self.campaign_id = campaign_id
        self.streams = {s["id"]: s for s in streams}
        self.put_payloads: list[dict] = []
        self._next_link = 5000

    def _link_id(self) -> int:
        self._next_link += 1
        return self._next_link

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}

        if "/offers/" in path and request.method == "GET":
            offer_id = int(path.rsplit("/", 1)[1])
            if offer_id >= 900000:
                return httpx.Response(404, json={"error": "Offer not found"})
            return httpx.Response(
                200, json={"id": offer_id, "name": f"оффер {offer_id}", "state": "active"}
            )
        if path.endswith(f"/campaigns/{self.campaign_id}/streams"):
            return httpx.Response(200, json=list(self.streams.values()))
        if request.method == "PUT" and "/streams/" in path:
            stream_id = int(path.rsplit("/", 1)[1])
            self.put_payloads.append(body)
            stream = self.streams[stream_id]
            stream["offers"] = [
                {
                    "id": self._link_id(),
                    "offer_id": o["offer_id"],
                    "share": o["share"],
                    "state": "active",
                }
                for o in body.get("offers", [])
            ]
            return httpx.Response(200, json={"id": stream_id})
        raise AssertionError(f"неожиданный запрос {request.method} {path}")


def offer_flow(offers: list[tuple[int, int]], campaign_id: int = 400, stream_id: int = 402) -> dict:
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
        "offers": [
            {"id": link_id, "offer_id": offer_id, "share": share, "state": "active"}
            for link_id, (offer_id, share) in zip(
                range(1001, 1001 + len(offers)), offers, strict=True
            )
        ],
        "triggers": [],
        "landings": [],
    }


def setup(session: Session, remote: Remote) -> KeitaroClient:
    session.add(Campaign(id=remote.campaign_id, alias="a", name="kolesnikov-тест"))
    client = KeitaroClient(
        Settings(
            keitaro_base_url="https://track.example", keitaro_api_key="k", keitaro_max_retries=0
        ),
        transport=httpx.MockTransport(remote.handler),
        sleep=lambda _: None,
    )
    mirror.sync_streams(session, client, remote.campaign_id)
    session.commit()
    return client


def row_of(session: Session, offer_id: int) -> StreamOffer:
    return session.scalar(select(StreamOffer).where(StreamOffer.offer_id == offer_id))


@pytest.fixture
def three_offers() -> Remote:
    return Remote(400, [offer_flow([(11, 34), (12, 33), (13, 33)])])


def test_add_offer_makes_four_equal_parts_and_stream_yellow(session, three_offers) -> None:
    client = setup(session, three_offers)
    view = editor.add_offer(session, client, 402, 14)

    assert sorted(v.share for v in view) == [25, 25, 25, 25]
    added = next(v for v in view if v.offer_id == 14)
    assert added.sync_status == SyncStatus.PENDING_ADD
    assert added.yellow is True and added.grey is False
    assert three_offers.put_payloads == []


def test_remove_offer_zeroes_it_and_rebalances(session, three_offers) -> None:
    setup(session, three_offers)
    target = row_of(session, 12)
    editor.remove_offer(session, target.id)

    assert target.share == 0
    assert target.sync_status == SyncStatus.PENDING_REMOVE
    assert row_of(session, 11).share + row_of(session, 13).share == 100
    assert {v.share for v in editor.offer_view(session, 402) if v.grey} == {0}


def test_removing_unpublished_offer_greys_it_without_remote_call(session, three_offers) -> None:
    """Не отправленный в трекер оффер ведёт себя как обычный: сереет и возвращается Back."""
    client = setup(session, three_offers)
    editor.add_offer(session, client, 402, 14)
    added = row_of(session, 14)

    editor.remove_offer(session, added.id)
    assert session.get(StreamOffer, added.id) is not None
    assert added.sync_status == SyncStatus.PENDING_REMOVE
    assert added.share == 0
    assert three_offers.put_payloads == []

    editor.restore_offer(session, added.id)
    assert added.sync_status == SyncStatus.PENDING_ADD
    assert added.share > 0


def test_push_drops_rows_marked_for_removal(session, three_offers) -> None:
    """Помеченная строка не улетает в трекер и после публикации исчезает из зеркала."""
    client = setup(session, three_offers)
    editor.add_offer(session, client, 402, 14)
    added = row_of(session, 14)
    editor.remove_offer(session, added.id)

    editor.push_stream(session, client, 402)

    # сверяем по офферу, а не по id строки: после удаления SQLite переиспользует ключ
    remaining = session.scalars(select(StreamOffer).where(StreamOffer.stream_id == 402)).all()
    assert sorted(row.offer_id for row in remaining) == [11, 12, 13]
    assert all(row.link_id is not None for row in remaining)
    sent = three_offers.put_payloads[-1]["offers"]
    assert sorted(item["offer_id"] for item in sent) == [11, 12, 13]
    assert sum(item["share"] for item in sent) == 100


def test_back_returns_the_removed_offer(session, three_offers) -> None:
    setup(session, three_offers)
    target = row_of(session, 12)
    editor.remove_offer(session, target.id)
    editor.restore_offer(session, target.id)

    assert target.sync_status == SyncStatus.SYNCED
    assert target.share > 0
    assert sum(v.share for v in editor.offer_view(session, 402)) == 100


def test_pinned_weight_survives_add(session, three_offers) -> None:
    client = setup(session, three_offers)
    editor.set_pin(session, row_of(session, 11).id, 25)
    view = editor.add_offer(session, client, 402, 14)

    assert next(v for v in view if v.offer_id == 11).share == 25
    assert sum(v.share for v in view) == 100
    assert next(v for v in view if v.pinned_share == 25).offer_id == 11


def test_conflicting_pins_are_rejected(session, three_offers) -> None:
    setup(session, three_offers)
    editor.set_pin(session, row_of(session, 11).id, 70)
    with pytest.raises(editor.EditorError, match="больше 100"):
        editor.set_pin(session, row_of(session, 12).id, 60)


def test_push_sends_live_offers_and_clears_pending(session, three_offers) -> None:
    client = setup(session, three_offers)
    editor.remove_offer(session, row_of(session, 12).id)
    editor.add_offer(session, client, 402, 14)

    editor.push_stream(session, client, 402)

    payload = three_offers.put_payloads[-1]
    assert {o["offer_id"] for o in payload["offers"]} == {11, 13, 14}
    assert sum(o["share"] for o in payload["offers"]) == 100
    assert session.get(Stream, 402).has_unpublished_changes is False
    assert row_of(session, 12) is None
    assert row_of(session, 14).link_id is not None
    assert row_of(session, 14).sync_status == SyncStatus.SYNCED


def test_push_refuses_empty_offer_flow(session, three_offers) -> None:
    client = setup(session, three_offers)
    for offer_id in (11, 12, 13):
        editor.remove_offer(session, row_of(session, offer_id).id)
    with pytest.raises(editor.EditorError, match="не осталось ни одного оффера"):
        editor.push_stream(session, client, 402)


def test_push_unknown_stream_is_a_clear_error(session, three_offers) -> None:
    client = setup(session, three_offers)
    with pytest.raises(editor.EditorError, match="не найден в зеркале"):
        editor.push_stream(session, client, 999)


def test_offer_absent_in_keitaro_turns_grey_and_back_readds_it(session, three_offers) -> None:
    client = setup(session, three_offers)
    # в трекере связку 1002 удалили
    three_offers.streams[402]["offers"] = [
        o for o in three_offers.streams[402]["offers"] if o["id"] != 1002
    ]
    mirror.sync_streams(session, client, 400)
    session.commit()

    lost = row_of(session, 12)
    assert lost.sync_status == SyncStatus.REMOVED_EXTERNALLY
    assert lost.share == 0

    editor.restore_offer(session, lost.id)
    assert lost.sync_status == SyncStatus.PENDING_ADD
    assert lost.link_id is None
    assert lost.share > 0


def test_duplicate_offer_in_same_flow_is_rejected(session, three_offers) -> None:
    client = setup(session, three_offers)
    with pytest.raises(editor.EditorError, match="уже стоит"):
        editor.add_offer(session, client, 402, 11)


def test_unknown_offer_id_is_reported(session, three_offers) -> None:
    client = setup(session, three_offers)
    with pytest.raises(editor.EditorError, match="не найден"):
        editor.add_offer(session, client, 402, 900001)


def test_push_keeps_row_identity_when_tracker_reissues_link_ids(session, three_offers) -> None:
    """Регрессия: PUT перевыпускает id связок, зеркало должно опознать свои строки по офферу.

    Без этого после каждой публикации поток выглядел так, будто все офферы удалили в трекере
    (серые строки) и добавили заново (новые строки с теми же офферами).
    """
    client = setup(session, three_offers)
    editor.add_offer(session, client, 402, 14)
    editor.push_stream(session, client, 402)

    rows = session.scalars(select(StreamOffer).where(StreamOffer.stream_id == 402)).all()
    assert sorted(row.offer_id for row in rows) == [11, 12, 13, 14]
    assert all(row.sync_status == SyncStatus.SYNCED for row in rows)
    assert all(row.link_id is not None for row in rows)
    assert sum(row.share for row in rows) == 100
