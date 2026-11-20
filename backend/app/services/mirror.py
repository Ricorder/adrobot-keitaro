"""Зеркало Keitaro в нашей базе.

Что и как синхронизируется:
 - справочники (офферы, группы, домены, источники) и список кампаний — целиком, это три
   запроса даже при 250+ кампаниях на стенде;
 - потоки подтягиваются только по одной кампании: это ровно то поведение, что показано
   в демонстрации (кнопка F-Streams забирает потоки выбранной кампании).

Внешнее удаление. Если оффер пропал из ответа Keitaro, но был в нашей базе, строка не
выбрасывается: она помечается removed_externally и получает 0 %. Так интерфейс может показать
серый оффер и кнопку возврата, а не молча его потерять.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Campaign,
    Domain,
    Group,
    Offer,
    Stream,
    StreamFilter,
    StreamOffer,
    SyncStatus,
    TrafficSource,
)
from app.keitaro.client import KeitaroClient


@dataclass
class SyncStats:
    campaigns: int = 0
    streams: int = 0
    offers_in_streams: int = 0
    removed_externally: int = 0
    reference: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaigns": self.campaigns,
            "streams": self.streams,
            "offers_in_streams": self.offers_in_streams,
            "removed_externally": self.removed_externally,
            "reference": self.reference,
            "at": datetime.now(UTC).isoformat(),
        }


def _merge(session: Session, model: Any, primary: str, values: dict[str, Any]) -> None:
    """Вставляет строку или обновляет существующую по первичному ключу."""
    instance = session.get(model, values[primary])
    if instance is None:
        session.add(model(**values))
        return
    for key, value in values.items():
        if key != primary:
            setattr(instance, key, value)


def sync_reference(session: Session, client: KeitaroClient) -> dict[str, int]:
    counts: dict[str, int] = {}

    offers = client.offers()
    for offer in offers:
        _merge(
            session,
            Offer,
            "id",
            {
                "id": offer["id"],
                "name": offer["name"],
                "group_id": offer.get("group_id"),
                "state": offer.get("state", "active"),
                "payout_type": offer.get("payout_type"),
                "payout_value": offer.get("payout_value"),
                "payout_currency": offer.get("payout_currency"),
                "offer_type": offer.get("offer_type"),
                "action_type": offer.get("action_type"),
                "fetched_at": datetime.now(UTC),
            },
        )
    counts["offers"] = len(offers)

    groups: list[dict[str, Any]] = []
    for group_type in ("campaigns", "offers"):
        groups.extend(client.groups(group_type))
    for group in groups:
        _merge(
            session,
            Group,
            "id",
            {"id": group["id"], "name": group["name"], "type": group["type"]},
        )
    counts["groups"] = len(groups)

    domains = client.domains()
    for domain in domains:
        _merge(
            session,
            Domain,
            "id",
            {
                "id": domain["id"],
                "name": domain["name"],
                "is_ssl": bool(domain.get("is_ssl")),
                "state": domain.get("state", "active"),
            },
        )
    counts["domains"] = len(domains)

    sources = client.traffic_sources()
    for source in sources:
        _merge(
            session,
            TrafficSource,
            "id",
            {"id": source["id"], "name": source["name"], "state": source.get("state", "active")},
        )
    counts["traffic_sources"] = len(sources)

    session.flush()
    return counts


def sync_campaigns(session: Session, client: KeitaroClient) -> int:
    count = 0
    for campaign in client.iter_campaigns():
        _merge(
            session,
            Campaign,
            "id",
            {
                "id": campaign["id"],
                "alias": campaign["alias"],
                "name": campaign["name"],
                "type": campaign.get("type", "position"),
                "state": campaign.get("state", "active"),
                "domain_id": campaign.get("domain_id"),
                "group_id": campaign.get("group_id"),
                "traffic_source_id": campaign.get("traffic_source_id"),
                "fetched_at": datetime.now(UTC),
            },
        )
        count += 1
    session.flush()
    return count


def sync_streams(session: Session, client: KeitaroClient, campaign_id: int) -> SyncStats:
    """Потоки одной кампании: обновляет зеркало и находит удалённые в Keitaro офферы."""
    stats = SyncStats()
    remote = client.streams(campaign_id)
    remote_stream_ids = {stream["id"] for stream in remote}
    now = datetime.now(UTC)

    known_streams = list(session.scalars(select(Stream).where(Stream.campaign_id == campaign_id)))

    # Поток, исчезший из трекера целиком, убираем и из зеркала: его офферы уже некуда возвращать.
    for stale in known_streams:
        if stale.id not in remote_stream_ids:
            session.delete(stale)
    session.flush()

    for payload in remote:
        stream = session.get(Stream, payload["id"]) or Stream(id=payload["id"])
        stream.campaign_id = payload["campaign_id"]
        stream.name = payload.get("name")
        stream.position = payload.get("position", 1)
        stream.type = payload.get("type", "regular")
        stream.schema = payload["schema"]
        stream.action_type = payload.get("action_type")
        stream.action_options = payload.get("action_options")
        stream.state = payload.get("state", "active")
        stream.weight = payload.get("weight", 0)
        stream.collect_clicks = bool(payload.get("collect_clicks", True))
        stream.filter_or = bool(payload.get("filter_or", False))
        stream.fetched_at = now
        if stream not in known_streams:
            session.add(stream)

        wanted_filter_ids = {item["id"] for item in payload.get("filters", [])}
        for item in payload.get("filters", []):
            _merge(
                session,
                StreamFilter,
                "id",
                {
                    "id": item["id"],
                    "stream_id": stream.id,
                    "name": item["name"],
                    "mode": item["mode"],
                    "payload": item.get("payload"),
                },
            )
        for stale_filter in list(stream.filters):
            if stale_filter.id not in wanted_filter_ids:
                session.delete(stale_filter)

        remote_offers = payload.get("offers", [])
        wanted_offer_link_ids = {item["id"] for item in remote_offers}
        for item in remote_offers:
            link = session.get(StreamOffer, item["id"]) or StreamOffer(id=item["id"])
            link.stream_id = stream.id
            link.offer_id = item["offer_id"]
            link.share = item.get("share", 100)
            link.state = item.get("state", "active")
            link.sync_status = SyncStatus.SYNCED
            if link not in stream.offers:
                stream.offers.append(link)
            stats.offers_in_streams += 1

        for link in list(stream.offers):
            if link.id not in wanted_offer_link_ids and link.sync_status != SyncStatus.PENDING_ADD:
                link.sync_status = SyncStatus.REMOVED_EXTERNALLY
                link.share = 0
                stats.removed_externally += 1

        stats.streams += 1

    session.flush()
    return stats


def sync_all(session: Session, client: KeitaroClient) -> SyncStats:
    stats = SyncStats()
    stats.reference = sync_reference(session, client)
    stats.campaigns = sync_campaigns(session, client)
    session.commit()
    return stats
