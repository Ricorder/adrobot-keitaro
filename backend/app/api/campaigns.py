"""HTTP API: создаватель кампаний и редактор потоков."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AddOfferBody,
    CampaignView,
    CreateCampaignBody,
    FilterView,
    OfferOption,
    OfferRowView,
    PinBody,
    StreamView,
)
from app.db.models import Campaign, Offer, Stream, SyncStatus
from app.deps import KeitaroDep, SessionDep
from app.keitaro.errors import KeitaroNotFoundError
from app.services import creator, editor, mirror

router = APIRouter(prefix="/api")


def _offer_rows(session: Session, stream: Stream) -> list[OfferRowView]:
    return [OfferRowView(**vars(v)) for v in editor.offer_view(session, stream.id)]


def _stream_view(session: Session, stream: Stream) -> StreamView:
    rows = _offer_rows(session, stream)
    active = [r for r in rows if r.sync_status != SyncStatus.PENDING_REMOVE]
    # «не распределено» осмысленно только там, где поток раздаёт офферы: в редирект-потоке
    # офферов нет по замыслу, и 100 % свободного места там было бы выдумкой
    unassigned = max(0, 100 - sum(r.share for r in active)) if rows else 0
    return StreamView(
        id=stream.id,
        name=stream.name,
        position=stream.position,
        flow_schema=stream.schema,
        action_type=stream.action_type,
        action_options=stream.action_options,
        state=stream.state,
        yellow=stream.has_unpublished_changes,
        unassigned_percent=unassigned,
        filters=[FilterView(name=f.name, mode=f.mode, payload=f.payload) for f in stream.filters],
        offers=rows,
    )


def _campaign_view(session: Session, campaign: Campaign) -> CampaignView:
    return CampaignView(
        id=campaign.id,
        alias=campaign.alias,
        name=campaign.name,
        state=campaign.state,
        domain_id=campaign.domain_id,
        group_id=campaign.group_id,
        traffic_source_id=campaign.traffic_source_id,
        created_by_us=campaign.created_by_us,
        streams=[
            _stream_view(session, s)
            for s in sorted(campaign.streams, key=lambda item: item.position)
        ],
    )


@router.post("/sync")
def sync(session: SessionDep, client: KeitaroDep) -> dict:
    stats = mirror.sync_all(session, client)
    return stats.as_dict()


@router.get("/campaigns", response_model=list[CampaignView])
def list_campaigns(
    session: SessionDep,
    q: str | None = Query(default=None, description="поиск по названию или alias"),
    only_ours: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[CampaignView]:
    stmt = select(Campaign)
    if only_ours:
        stmt = stmt.where(Campaign.created_by_us.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Campaign.name.ilike(like), Campaign.alias.ilike(like)))
    campaigns = session.scalars(stmt.order_by(Campaign.id.desc()).limit(limit)).all()
    return [_campaign_view(session, c) for c in campaigns]


@router.get("/campaigns/{campaign_id}", response_model=CampaignView)
def get_campaign(
    campaign_id: int,
    session: SessionDep,
    client: KeitaroDep,
) -> CampaignView:
    """Открывает кампанию и заодно подтягивает её потоки из трекера (кнопка F-Streams)."""
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        mirror.sync_campaigns(session, client)
        campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise creator.CreatorError(f"кампания {campaign_id} не найдена в Keitaro")
    mirror.sync_streams(session, client, campaign_id)
    session.refresh(campaign)
    return _campaign_view(session, campaign)


@router.post("/campaigns", response_model=CampaignView, status_code=status.HTTP_201_CREATED)
def create_campaign(
    body: CreateCampaignBody,
    request: Request,
    session: SessionDep,
    client: KeitaroDep,
) -> CampaignView:
    idempotency_key = request.headers.get("Idempotency-Key")
    result = creator.create_campaign(
        session,
        client,
        request.app.state.settings,
        name=body.name,
        geo=body.geo,
        offer_id=body.offer_id,
        domain_id=body.domain_id,
        idempotency_key=idempotency_key,
    )
    campaign = session.get(Campaign, result.campaign_id)
    if campaign is None:
        raise creator.CreatorError(
            f"кампания {result.campaign_id} создана в Keitaro, но не попала в зеркало"
        )
    return _campaign_view(session, campaign)


@router.get("/offers", response_model=list[OfferOption])
def search_offers(
    session: SessionDep,
    client: KeitaroDep,
    q: str | None = Query(default=None, description="id или часть названия"),
    limit: int = Query(default=30, ge=1, le=200),
) -> list[OfferOption]:
    """Автокомплит поиска офферов: сначала зеркало, при пропуске — один живой запрос."""
    if session.scalar(select(func.count()).select_from(Offer)) == 0:
        mirror.sync_reference(session, client)

    stmt = select(Offer).order_by(Offer.id.desc()).limit(limit)
    if q:
        like = f"%{q}%"
        clauses = [Offer.name.ilike(like)]
        if q.strip().isdigit():
            clauses.append(Offer.id == int(q.strip()))
        stmt = stmt.where(or_(*clauses))

    rows = session.scalars(stmt).all()
    if not rows and q and q.strip().isdigit():
        # в зеркале ровно те офферы, что мы качали: ищем один точный id в трекере.
        # 404 — это «такого оффера нет», пустой список, а не ошибка связи.
        try:
            remote = client.offer(int(q.strip()))
        except KeitaroNotFoundError:
            remote = None
        if remote is not None:
            rows = [
                Offer(
                    id=remote["id"],
                    name=remote.get("name", ""),
                    state=remote.get("state", "active"),
                )
            ]
    return [OfferOption(id=o.id, name=o.name, state=o.state) for o in rows]


@router.post("/streams/{stream_id}/offers", response_model=list[OfferRowView])
def add_offer(
    stream_id: int,
    body: AddOfferBody,
    session: SessionDep,
    client: KeitaroDep,
) -> list[OfferRowView]:
    view = editor.add_offer(session, client, stream_id, body.offer_id)
    return [OfferRowView(**vars(row)) for row in view]


@router.delete("/streams/offers/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_offer(row_id: int, session: SessionDep) -> None:
    editor.remove_offer(session, row_id)


@router.post("/streams/offers/{row_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_offer(row_id: int, session: SessionDep) -> None:
    editor.restore_offer(session, row_id)


@router.put("/streams/offers/{row_id}/pin", status_code=status.HTTP_204_NO_CONTENT)
def pin_offer(row_id: int, body: PinBody, session: SessionDep) -> None:
    editor.set_pin(session, row_id, body.share)


@router.post("/streams/{stream_id}/push")
def push_stream(
    stream_id: int,
    session: SessionDep,
    client: KeitaroDep,
) -> dict:
    stats = editor.push_stream(session, client, stream_id)
    stream = session.get(Stream, stream_id)
    rows = stream.offers if stream is not None else []
    return {
        **stats.as_dict(),
        "yellow": stream.has_unpublished_changes if stream is not None else False,
        "shares": {row.offer_id: row.share for row in rows},
    }
