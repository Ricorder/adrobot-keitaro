"""Сквозная проверка: наш клиент и сервисы против Keitaro-подобного сервера по loopback.

Мок (`tools/mock_keitaro.py`) повторяет формы ответов настоящего стенда, включая 403 на
создание источника/домена/оффера, поэтому эти тесты ловят расхождение между нашим кодом и
реальным API без обращения к чужому серверу.
"""

import socket
import threading
import time

import pytest
import uvicorn
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Campaign, Stream
from app.keitaro.client import KeitaroClient
from app.services import creator, editor, mirror
from tools.mock_keitaro import API_KEY, create_mock_app


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def mock_server():
    port = free_port()
    config = uvicorn.Config(create_mock_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        raise RuntimeError("мок-трекер не поднялся за 10 секунд")

    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def settings(mock_server: str) -> Settings:
    return Settings(
        keitaro_base_url=mock_server,
        keitaro_api_key=API_KEY,
        keitaro_prefix="kolesnikov-",
        keitaro_max_retries=0,
    )


@pytest.fixture
def client(settings: Settings) -> KeitaroClient:
    return KeitaroClient(settings)


def test_bad_key_is_rejected(mock_server: str) -> None:
    from app.keitaro.errors import KeitaroAuthError

    wrong = KeitaroClient(
        Settings(keitaro_base_url=mock_server, keitaro_api_key="wrong-key", keitaro_max_retries=0)
    )
    with pytest.raises(KeitaroAuthError):
        wrong.offers()


def test_source_and_domain_creation_is_forbidden(client: KeitaroClient) -> None:
    """Поведение стенда: эти сущности создавать нельзя, только переиспользовать."""
    from app.keitaro.errors import KeitaroAPIError

    with pytest.raises(KeitaroAPIError, match="no permission"):
        client._request("POST", "/traffic_sources", json_body={"name": "x"})
    with pytest.raises(KeitaroAPIError, match="no permission"):
        client._request("POST", "/domains", json_body={"name": "x"})


def test_full_cycle_against_mock(
    session: Session, client: KeitaroClient, settings: Settings
) -> None:
    mirror.sync_reference(session, client)
    campaigns = mirror.sync_campaigns(session, client)
    session.commit()
    assert campaigns == 2

    result = creator.create_campaign(
        session, client, settings, name="Сквозной тест", geo="AU", offer_id=18816
    )
    assert result.group_id == 10332
    assert result.traffic_source_id == 836
    assert result.domain_id == 1813
    assert result.alias.startswith("kolesnikov-")

    stored = session.get(Campaign, result.campaign_id)
    assert stored is not None
    geo_flow = next(s for s in stored.streams if s.schema == "redirect")
    offer_flow = next(s for s in stored.streams if s.schema == "landings")
    assert [f.payload for f in geo_flow.filters] == [["AU"]]
    assert [o.share for o in offer_flow.offers] == [100]

    # добавляем второй оффер: доли становятся 50/50
    rows = editor.add_offer(session, client, offer_flow.id, 18813)
    assert sorted(row.share for row in rows) == [50, 50]
    assert any(row.sync_status == "pending_add" for row in rows)

    # закрепляем 20 % за новым и убираем первый: оставшийся держит свои 20 %,
    # а 80 % не распределены — обёртка не доливает их молча
    added = next(row for row in rows if row.offer_id == 18813)
    editor.set_pin(session, added.id, 20)
    first = next(row for row in rows if row.offer_id == 18816)
    editor.remove_offer(session, first.id)

    stats = editor.push_stream(session, client, offer_flow.id)
    assert stats.streams == 2
    published = session.get(Stream, offer_flow.id)
    assert published is not None
    assert published.has_unpublished_changes is False
    assert [(o.offer_id, o.share) for o in published.offers] == [(18813, 20)]


def test_mirror_marks_offer_deleted_in_tracker(session: Session, client: KeitaroClient) -> None:
    mirror.sync_reference(session, client)
    mirror.sync_campaigns(session, client)
    session.commit()

    # берём именно демо-кампанию мока: сервер в тестах один на модуль, а «первая в списке»
    # может оказаться созданной предыдущим тестом
    target = next(c for c in client.iter_campaigns() if c["alias"].startswith("demo-"))
    mirror.sync_streams(session, client, target["id"])
    session.commit()

    campaign = session.get(Campaign, target["id"])
    offer_flow = next(s for s in campaign.streams if s.schema == "landings")
    survivors = list(offer_flow.offers[1:])
    assert survivors, "в демо-кампании должно быть больше одного оффера"

    # кто-то убрал первый оффер прямо в трекере
    client.update_stream(
        offer_flow.id,
        {
            "campaign_id": target["id"],
            "schema": "landings",
            "action_type": "http",
            "offers": [{"offer_id": o.offer_id, "share": o.share} for o in survivors],
        },
    )

    stats = mirror.sync_streams(session, client, target["id"])
    session.commit()
    assert stats.removed_externally == 1
    lost = offer_flow.offers[0]
    assert lost.sync_status == "removed_externally"
    assert lost.share == 0
