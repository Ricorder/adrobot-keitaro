"""Редактор существующей кампании.

Логика повторяет показанный в демонстрации инструмент:

 - F-Streams подтягивает потоки из Keitaro, локальные неопубликованные правки при этом
   не затираются;
 - добавили оффер -> пересчитались доли (4 оффера = по 25 %), поток стал жёлтым;
 - Remove -> оффер сереет, его доля становится 0 %, поток снова жёлтый;
 - Back -> возвращает помеченный оффер;
 - Push KT -> единственный момент, когда что-то улетает в трекер;
 - закреплённый вес не меняется при добавлении и удалении, остальные делят остаток.

Удалённые офферы уходят в архив Keitaro, а не исчезают бесследно: локальная строка
живёт до Push KT, поэтому после публикации мы её убираем из зеркала сами.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Offer, Stream, StreamOffer, SyncStatus
from app.keitaro.client import KeitaroClient
from app.keitaro.errors import KeitaroAPIError
from app.services import mirror, weights


class EditorError(Exception):
    """Операция над потоком невозможна; текст идёт прямо в интерфейс."""


@dataclass
class OfferView:
    id: int
    link_id: int | None
    offer_id: int
    name: str
    share: int
    pinned_share: int | None
    sync_status: str
    grey: bool
    yellow: bool


def _stream_or_fail(session: Session, stream_id: int) -> Stream:
    stream = session.get(Stream, stream_id)
    if stream is None:
        raise EditorError(f"поток {stream_id} не найден в зеркале — сначала F-Streams")
    return stream


def _weights_of(stream: Stream) -> list[weights.OfferWeight]:
    return [
        weights.OfferWeight(
            offer_id=row.id,
            pinned=row.pinned_share,
            removed=row.sync_status == SyncStatus.PENDING_REMOVE,
        )
        for row in stream.offers
    ]


def _apply_shares(stream: Stream) -> dict[int, int]:
    """Пересчитывает доли. Неопубликованные на удаление строки получают 0 и не участвуют.

    Сумма может быть меньше 100 % только в одном случае: остались одни закрепления. Тогда
    интерфейс показывает недобранный остаток отдельным числом, а не молча доливает его.
    """
    shares = weights.recalculate(_weights_of(stream))
    for row in stream.offers:
        row.share = shares[row.id]
    return shares


def add_offer(
    session: Session, client: KeitaroClient, stream_id: int, offer_id: int
) -> list[OfferView]:
    stream = _stream_or_fail(session, stream_id)
    try:
        remote = client.offer(offer_id)
    except KeitaroAPIError as exc:
        raise EditorError(f"оффер {offer_id} в Keitaro не найден: {exc}") from exc

    existing = session.scalar(
        select(StreamOffer).where(
            StreamOffer.stream_id == stream.id,
            StreamOffer.offer_id == offer_id,
            StreamOffer.sync_status.in_([SyncStatus.SYNCED, SyncStatus.PENDING_ADD]),
        )
    )
    if existing is not None:
        raise EditorError(f"оффер {offer_id} уже стоит в этом потоке")

    row = StreamOffer(
        link_id=None,
        offer_id=offer_id,
        share=0,
        state="active",
        sync_status=SyncStatus.PENDING_ADD,
        position=len(stream.offers) + 1,
    )
    # вешаем на отношение, а не просто session.add: пересчёт ниже идёт по stream.offers,
    # и новая строка обязана в него попасть
    stream.offers.append(row)
    if remote.get("name"):
        known = session.get(Offer, offer_id)
        if known is None:
            # справочник пополняем только названием: остальные поля принадлежат трекеру
            session.add(
                Offer(id=offer_id, name=remote["name"], state=remote.get("state", "active"))
            )
    _apply_shares(stream)
    session.commit()
    return offer_view(session, stream.id)


def remove_offer(session: Session, row_id: int) -> None:
    row = session.get(StreamOffer, row_id)
    if row is None:
        raise EditorError(f"строка {row_id} не найдена")
    # Помечаем, а не удаляем сразу: и опубликованный, и ещё не отправленный в трекер оффер
    # должен сереть и возвращаться кнопкой Back. Из зеркала строка уйдёт после Push KT.
    row.sync_status = SyncStatus.PENDING_REMOVE
    _apply_shares(row.stream)
    session.commit()


def restore_offer(session: Session, row_id: int) -> None:
    row = session.get(StreamOffer, row_id)
    if row is None:
        raise EditorError(f"строка {row_id} не найдена")
    if row.sync_status == SyncStatus.PENDING_REMOVE:
        # строка без link_id в трекере никогда не существовала — возвращаем её как новую
        row.sync_status = SyncStatus.SYNCED if row.link_id is not None else SyncStatus.PENDING_ADD
    elif row.sync_status == SyncStatus.REMOVED_EXTERNALLY:
        # в трекере связки уже нет: вернём её как новое добавление с новым id
        row.sync_status = SyncStatus.PENDING_ADD
        row.link_id = None
    else:
        raise EditorError(f"строка {row_id} не помечена на удаление, возвращать нечего")
    _apply_shares(row.stream)
    session.commit()


def set_pin(session: Session, row_id: int, pinned_share: int | None) -> None:
    row = session.get(StreamOffer, row_id)
    if row is None:
        raise EditorError(f"строка {row_id} не найдена")
    if pinned_share is not None and not 0 <= pinned_share <= 100:
        raise EditorError(f"закрепляемая доля должна быть от 0 до 100, получено {pinned_share}")
    row.pinned_share = pinned_share
    try:
        _apply_shares(row.stream)
    except weights.WeightConflict as exc:
        raise EditorError(str(exc)) from exc
    session.commit()


def push_stream(session: Session, client: KeitaroClient, stream_id: int) -> mirror.SyncStats:
    """Единственная операция, которая пишет в Keitaro."""
    stream = _stream_or_fail(session, stream_id)
    # список перечитываем: добавленная строка может ещё не состоять в коллекции relationship
    rows = list(session.scalars(select(StreamOffer).where(StreamOffer.stream_id == stream.id)))
    live_rows = [row for row in rows if row.sync_status != SyncStatus.PENDING_REMOVE]
    if not live_rows and stream.schema == "landings":
        raise EditorError("в офферном потоке не осталось ни одного оффера — Push KT не нужен")

    payload: dict = {
        "campaign_id": stream.campaign_id,
        "name": stream.name,
        "type": stream.type,
        "position": stream.position,
        "schema": stream.schema,
        "action_type": stream.action_type,
        "action_options": stream.action_options,
        "state": stream.state,
        "collect_clicks": stream.collect_clicks,
        "filter_or": stream.filter_or,
        "filters": [
            {"id": f.id, "name": f.name, "mode": f.mode, "payload": f.payload}
            for f in stream.filters
        ],
        "offers": [
            {"offer_id": row.offer_id, "share": row.share, "state": "active"} for row in live_rows
        ],
    }

    try:
        client.update_stream(stream.id, payload)
    except KeitaroAPIError as exc:
        raise EditorError(f"Keitaro не принял поток {stream.id}: {exc}") from exc

    # опубликованные строки больше не «черновик»: снимаем статус здесь, а не в зеркале,
    # иначе обычное F-Streams перестало бы защищать несохранённые правки
    for row in live_rows:
        row.sync_status = SyncStatus.SYNCED

    # Удаляем bulk-запросом: session.delete() для строки, которая ещё лежит в загруженной
    # коллекции родителя с delete-orphan, откатывается обратно при flush.
    doomed = [row.id for row in rows if row.sync_status == SyncStatus.PENDING_REMOVE]
    if doomed:
        session.execute(delete(StreamOffer).where(StreamOffer.id.in_(doomed)))
        session.expire_all()
    session.commit()

    return mirror.sync_streams(session, client, stream.campaign_id)


def offer_view(session: Session, stream_id: int) -> list[OfferView]:
    """Строки потока для интерфейса: кто серый, кто жёлтый, как зовут оффер."""
    stream = _stream_or_fail(session, stream_id)
    offer_ids = [row.offer_id for row in stream.offers]
    names = (
        {o.id: o.name for o in session.scalars(select(Offer).where(Offer.id.in_(offer_ids)))}
        if offer_ids
        else {}
    )
    yellow = stream.has_unpublished_changes
    return [
        OfferView(
            id=row.id,
            link_id=row.link_id,
            offer_id=row.offer_id,
            name=names.get(row.offer_id, f"оффер {row.offer_id}"),
            share=row.share,
            pinned_share=row.pinned_share,
            sync_status=row.sync_status,
            grey=row.sync_status in (SyncStatus.PENDING_REMOVE, SyncStatus.REMOVED_EXTERNALLY),
            yellow=yellow,
        )
        for row in sorted(stream.offers, key=lambda r: (r.position, r.id))
    ]
