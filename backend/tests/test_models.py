from sqlalchemy.orm import Session

from app.db.models import Campaign, Stream, StreamFilter, StreamOffer, SyncStatus


def build_campaign(session: Session, *, campaign_id: int = 1) -> Campaign:
    """Кампания как её отдаёт Keitaro: поток с гео-фильтром на Google + офферный поток."""
    campaign = Campaign(
        id=campaign_id,
        alias=f"kolesnikov-{campaign_id}",
        name="kolesnikov-тест",
        type="position",
        domain_id=1813,
        group_id=10332,
        traffic_source_id=836,
        created_by_us=True,
    )
    campaign.streams = [
        Stream(
            id=campaign_id * 100 + 1,
            name="Гео RU → Google",
            position=1,
            schema="redirect",
            action_type="http",
            action_options={"url": "https://www.google.com"},
            filters=[StreamFilter(id=1, name="country", mode="accept", payload=["RU"])],
        ),
        Stream(
            id=campaign_id * 100 + 2,
            name="Офферы",
            position=2,
            schema="landings",
            action_type="http",
            offers=[
                StreamOffer(link_id=1, offer_id=18813, share=100),
            ],
        ),
    ]
    session.add(campaign)
    session.flush()
    return campaign


def test_fresh_stream_from_keitaro_is_not_marked_unpublished(session) -> None:
    campaign = build_campaign(session)
    offers_stream = campaign.streams[1]
    assert offers_stream.has_unpublished_changes is False


def test_added_offer_marks_stream_yellow(session) -> None:
    campaign = build_campaign(session)
    offers_stream = campaign.streams[1]
    offers_stream.offers.append(
        StreamOffer(link_id=2, offer_id=18814, share=50, sync_status=SyncStatus.PENDING_ADD)
    )
    session.flush()
    assert offers_stream.has_unpublished_changes is True


def test_pending_remove_keeps_the_row_until_push(session) -> None:
    """Удалённый в интерфейсе оффер ещё жив в базе: он уедет в Keitaro только по Push KT."""
    campaign = build_campaign(session)
    offer_row = campaign.streams[1].offers[0]
    offer_row.sync_status = SyncStatus.PENDING_REMOVE
    offer_row.share = 0
    session.flush()
    assert offer_row.share == 0
    assert offer_row.sync_status == SyncStatus.PENDING_REMOVE


def test_removing_stream_cascades_to_offers_and_filters(session) -> None:
    campaign = build_campaign(session)
    geo_stream, offers_stream = campaign.streams
    session.delete(geo_stream)
    session.delete(offers_stream)
    session.flush()
    assert session.query(StreamOffer).count() == 0
    assert session.query(StreamFilter).count() == 0
