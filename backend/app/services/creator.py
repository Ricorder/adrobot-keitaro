"""Создаватор кампаний.

Один вызов = одна кампания с двумя потоками, как требует задание:
 поток 1 ловит указанную страну и редиректит на Google, поток 2 отдаёт выбранный оффер.
Обязательные доменные поля кампании (домен, группа, источник) тоже проставляются: группа и
источник заводятся с нашим префиксом, если их ещё нет, домен берётся из имеющихся на стенде.

Порядок шагов важнее красоты:
 - кампания попадает в зеркало сразу после создания в Keitaro, а не в конце. Иначе оборванная
   попытка оставляет на общем стенде сироту, которую повтор не находит и создаёт дубль;
 - если поток создать не удалось, кампания удаляется и следом убирается из зеркала;
 - повтор с тем же названием не плодит копию, а доделывает недостающие потоки.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Campaign, CreationRequest, CreationStatus, Stream, SyncStatus
from app.keitaro.client import KeitaroClient
from app.keitaro.errors import KeitaroAPIError
from app.services import mirror
from app.services.geo import normalize_geo
from app.services.slug import make_alias

GEO_SCHEMA = "redirect"
OFFER_SCHEMA = "landings"


class CreatorError(Exception):
    """Кампанию не удалось собрать; текст ошибки всегда человекочитаемый."""


@dataclass
class CreationResult:
    campaign_id: int
    alias: str
    group_id: int
    domain_id: int
    traffic_source_id: int
    geo_stream_id: int
    offer_stream_id: int
    reused: bool = False


def _existing_by_name(items: list[dict], name: str) -> dict | None:
    return next((item for item in items if item.get("name") == name), None)


def _resolve_group(client: KeitaroClient, settings: Settings) -> int:
    """Группу берём существующей по имени из настроек; создание правами API разрешено."""
    name = settings.keitaro_group_name
    found = _existing_by_name(client.groups("campaigns"), name)
    if found is not None:
        return int(found["id"])
    try:
        return int(client.create_group(name=name, group_type="campaigns")["id"])
    except KeitaroAPIError as exc:
        raise CreatorError(
            f"группа {name!r} не найдена и не создана: {exc}. "
            "Укажите в KEITARO_GROUP_NAME существующую группу."
        ) from exc


def _resolve_source(client: KeitaroClient, settings: Settings) -> int:
    """Источник только переиспользуется.

    На тестовом стенде POST /traffic_sources отвечает 403 «no permission» — проверено
    запросом, поэтому пытаться создать источник бессмысленно: вместо этого просим
    существующий по имени или по одному-единственному доступному.
    """
    name = settings.keitaro_source_name
    sources = client.traffic_sources()
    found = _existing_by_name(sources, name)
    if found is not None:
        return int(found["id"])
    if len(sources) == 1:
        return int(sources[0]["id"])
    names = ", ".join(sorted(str(s.get("name")) for s in sources)) or "нет ни одного"
    raise CreatorError(
        f"источник {name!r} не найден, а создание источников закрыто правами API. "
        f"Доступные: {names}. Укажите один из них в KEITARO_SOURCE_NAME."
    )


def _pick_domain(client: KeitaroClient, preferred: int | None) -> int:
    domains = [d for d in client.domains() if d.get("state", "active") == "active"]
    if not domains:
        raise CreatorError("на стенде нет ни одного активного домена — кампанию редиректить некуда")
    if preferred is not None:
        match = next((d for d in domains if d["id"] == preferred), None)
        if match is None:
            ids = [d["id"] for d in domains]
            raise CreatorError(f"домен {preferred} не найден среди активных: {ids}")
        return int(match["id"])
    return int(domains[0]["id"])


def _geo_stream_payload(campaign_id: int, geo: str, settings: Settings) -> dict:
    return {
        "campaign_id": campaign_id,
        "name": f"Гео {geo} → Google",
        "type": "regular",
        "position": 1,
        "schema": GEO_SCHEMA,
        "action_type": "http",
        "action_options": {"url": settings.google_redirect_url},
        "collect_clicks": True,
        "filter_or": False,
        "state": "active",
        "filters": [{"name": "country", "mode": "accept", "payload": [geo]}],
    }


def _offer_stream_payload(campaign_id: int, offer_id: int) -> dict:
    return {
        "campaign_id": campaign_id,
        "name": f"Оффер {offer_id}",
        "type": "regular",
        "position": 2,
        "schema": OFFER_SCHEMA,
        "action_type": "http",
        "collect_clicks": True,
        "filter_or": False,
        "state": "active",
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
    }


def _stream_geo(stream: Stream) -> str | None:
    for item in stream.filters:
        if item.name == "country" and isinstance(item.payload, list) and item.payload:
            return str(item.payload[0])
    return None


def _stream_offer_ids(stream: Stream) -> set[int]:
    return {o.offer_id for o in stream.offers if o.sync_status != SyncStatus.REMOVED_EXTERNALLY}


def _complete_streams(
    session: Session,
    client: KeitaroClient,
    settings: Settings,
    campaign: Campaign,
    *,
    geo: str,
    offer_id: int,
) -> CreationResult:
    """Доделывает кампании недостающие потоки и возвращает результат.

    Уже готовые потоки не трогаем, но проверяем их содержимое: молча вернуть кампанию с
    другой страной или другим оффером значило бы соврать вызывающему.
    """
    mirror.sync_streams(session, client, campaign.id)
    session.refresh(campaign)
    by_schema = {s.schema: s for s in campaign.streams}

    geo_stream = by_schema.get(GEO_SCHEMA)
    if geo_stream is not None and _stream_geo(geo_stream) != geo:
        raise CreatorError(
            f"кампания {campaign.name!r} (id {campaign.id}) уже ловит "
            f"{_stream_geo(geo_stream) or 'не определено'}, а запрошено {geo}. "
            "Изменить страну можно в редакторе потоков, повтор её не перезапишет."
        )

    offer_stream = by_schema.get(OFFER_SCHEMA)
    if offer_stream is not None and offer_id not in _stream_offer_ids(offer_stream):
        raise CreatorError(
            f"кампания {campaign.name!r} (id {campaign.id}) уже отдаёт офферы "
            f"{sorted(_stream_offer_ids(offer_stream))}, а запрошен {offer_id}. "
            "Добавить оффер можно в редакторе, повтор его не допишет."
        )

    try:
        if geo_stream is None:
            client.create_stream(_geo_stream_payload(campaign.id, geo, settings))
        if offer_stream is None:
            client.create_stream(_offer_stream_payload(campaign.id, offer_id))
    except KeitaroAPIError as exc:
        raise CreatorError(f"не удалось доделать потоки кампании {campaign.id}: {exc}") from exc

    mirror.sync_streams(session, client, campaign.id)
    session.refresh(campaign)
    stored_geo = next(s for s in campaign.streams if s.schema == GEO_SCHEMA)
    stored_offer = next(s for s in campaign.streams if s.schema == OFFER_SCHEMA)
    return CreationResult(
        campaign_id=campaign.id,
        alias=campaign.alias,
        group_id=campaign.group_id or 0,
        domain_id=campaign.domain_id or 0,
        traffic_source_id=campaign.traffic_source_id or 0,
        geo_stream_id=stored_geo.id,
        offer_stream_id=stored_offer.id,
        reused=True,
    )


def _find_twin(session: Session, name: str) -> Campaign | None:
    return session.scalar(
        select(Campaign).where(Campaign.name == name, Campaign.created_by_us.is_(True))
    )


def _drop_from_mirror(session: Session, campaign_id: int) -> None:
    stored = session.get(Campaign, campaign_id)
    if stored is not None:
        session.delete(stored)
        session.flush()


def create_campaign(
    session: Session,
    client: KeitaroClient,
    settings: Settings,
    *,
    name: str,
    geo: str,
    offer_id: int,
    domain_id: int | None = None,
    idempotency_key: str | None = None,
) -> CreationResult:
    clean_name = name.strip()
    if not clean_name:
        raise CreatorError("название кампании не может быть пустым")

    key = idempotency_key or f"auto-{secrets.token_hex(8)}"
    record = session.scalar(select(CreationRequest).where(CreationRequest.idempotency_key == key))
    if record is None:
        record = CreationRequest(
            id=uuid4(),
            idempotency_key=key,
            name=clean_name,
            geo="",
            offer_id=offer_id,
        )
        session.add(record)

    try:
        record.geo = normalize_geo(geo)
    except ValueError as exc:
        record.status = CreationStatus.FAILED
        record.error = str(exc)
        session.commit()
        raise CreatorError(str(exc)) from exc

    try:
        client.offer(offer_id)
    except KeitaroAPIError as exc:
        record.status = CreationStatus.FAILED
        record.error = f"оффер {offer_id} в Keitaro не найден: {exc}"
        session.commit()
        raise CreatorError(record.error) from exc

    twin = _find_twin(session, clean_name)
    if twin is not None:
        result = _complete_streams(
            session, client, settings, twin, geo=record.geo, offer_id=offer_id
        )
        record.status = CreationStatus.DONE
        record.campaign_id = result.campaign_id
        record.error = None
        session.commit()
        return result

    group_id = _resolve_group(client, settings)
    source_id = _resolve_source(client, settings)
    chosen_domain = _pick_domain(client, domain_id)
    alias = make_alias(clean_name, settings.keitaro_prefix)

    created = client.create_campaign(
        {
            "alias": alias,
            "name": clean_name,
            "type": "position",
            "domain_id": chosen_domain,
            "group_id": group_id,
            "traffic_source_id": source_id,
            "state": "active",
        }
    )
    campaign_id = int(created["id"])
    record.campaign_id = campaign_id
    # кампания уже существует в трекере — фиксируем это до создания потоков
    session.add(
        Campaign(
            id=campaign_id,
            alias=alias,
            name=clean_name,
            type="position",
            state="active",
            domain_id=chosen_domain,
            group_id=group_id,
            traffic_source_id=source_id,
            created_by_us=True,
        )
    )
    session.commit()

    try:
        client.create_stream(_geo_stream_payload(campaign_id, record.geo, settings))
        client.create_stream(_offer_stream_payload(campaign_id, offer_id))
    except KeitaroAPIError as exc:
        problem = _safe_delete_campaign(client, campaign_id)
        if problem is None:
            _drop_from_mirror(session, campaign_id)
            record.error = f"поток не создан, кампания {campaign_id} удалена: {exc}"
            record.campaign_id = None
        else:
            record.error = f"поток не создан, {problem}: {exc}"
        record.status = CreationStatus.PARTIAL
        session.commit()
        raise CreatorError(record.error) from exc

    mirror.sync_reference(session, client)
    mirror.sync_campaigns(session, client)
    mirror.sync_streams(session, client, campaign_id)
    stored = session.get(Campaign, campaign_id)
    if stored is not None:
        stored.created_by_us = True
    record.status = CreationStatus.DONE
    record.error = None
    session.commit()

    streams = {s.schema: s.id for s in (stored.streams if stored else [])}
    return CreationResult(
        campaign_id=campaign_id,
        alias=alias,
        group_id=group_id,
        domain_id=chosen_domain,
        traffic_source_id=source_id,
        geo_stream_id=streams[GEO_SCHEMA],
        offer_stream_id=streams[OFFER_SCHEMA],
    )


def _safe_delete_campaign(client: KeitaroClient, campaign_id: int) -> str | None:
    """Компенсация. Возвращает текст проблемы, если удалить не удалось."""
    try:
        client.delete_campaign(campaign_id)
    except KeitaroAPIError as exc:
        return f"кампания {campaign_id} осталась на стенде, удалите её вручную: {exc}"
    return None
