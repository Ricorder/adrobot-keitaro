"""Зеркало сущностей Keitaro в нашей базе.

Keitaro остаётся источником истины, но редактор работает по этой базе: изменения копятся
локально (статус pending_*) и уезжают в трекер только по кнопке Push KT. Поэтому у каждой
строки есть и поле из Keitaro, и наш признак рассинхрона.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class SyncStatus(enum.StrEnum):
    """Состояние строки относительно трекера."""

    SYNCED = "synced"
    PENDING_ADD = "pending_add"
    PENDING_REMOVE = "pending_remove"
    REMOVED_EXTERNALLY = "removed_externally"


class CreationStatus(enum.StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    PARTIAL = "partial"


class Offer(Base):
    """Справочник офферов: нужен для поиска по ID/названию в редакторе."""

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(512))
    group_id: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32))
    payout_type: Mapped[str | None] = mapped_column(String(32))
    payout_value: Mapped[float | None] = mapped_column()
    payout_currency: Mapped[str | None] = mapped_column(String(8))
    offer_type: Mapped[str | None] = mapped_column(String(32))
    action_type: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))
    is_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrafficSource(Base):
    __tablename__ = "traffic_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    alias: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    type: Mapped[str] = mapped_column(String(16), default="position")
    state: Mapped[str] = mapped_column(String(16), default="active")
    domain_id: Mapped[int | None] = mapped_column(Integer)
    group_id: Mapped[int | None] = mapped_column(Integer)
    traffic_source_id: Mapped[int | None] = mapped_column(Integer)
    created_by_us: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    streams: Mapped[list[Stream]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="Stream.position"
    )


class Stream(Base):
    """Поток (flow). Жёлтый в интерфейсе == has_unpublished_changes."""

    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=1)
    type: Mapped[str] = mapped_column(String(16), default="regular")
    schema: Mapped[str] = mapped_column(String(32))
    action_type: Mapped[str | None] = mapped_column(String(64))
    action_options: Mapped[dict | None] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="active")
    weight: Mapped[float] = mapped_column(default=0)
    collect_clicks: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_or: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    filters: Mapped[list[StreamFilter]] = relationship(
        back_populates="stream", cascade="all, delete-orphan"
    )
    offers: Mapped[list[StreamOffer]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="StreamOffer.id"
    )

    @property
    def has_unpublished_changes(self) -> bool:
        pending = {SyncStatus.PENDING_ADD, SyncStatus.PENDING_REMOVE}
        return any(o.sync_status in pending for o in self.offers)


class StreamFilter(Base):
    __tablename__ = "stream_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    payload: Mapped[list | None] = mapped_column(JSON)

    stream: Mapped[Stream] = relationship(back_populates="filters")


class StreamOffer(Base):
    """Связка поток-оффер: здесь живёт доля (share) и закреплённый вес.

    Ключ локальный, id связки из Keitaro хранится отдельно: добавленный в редакторе оффер
    существует у нас до Push KT, и своего идентификатора у трекера он ещё не имеет.
    """

    __tablename__ = "stream_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), index=True)
    offer_id: Mapped[int] = mapped_column(Integer, index=True)
    share: Mapped[int] = mapped_column(Integer, default=100)
    state: Mapped[str] = mapped_column(String(16), default="active")
    sync_status: Mapped[str] = mapped_column(String(32), default=SyncStatus.SYNCED)
    pinned_share: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=1)

    stream: Mapped[Stream] = relationship(back_populates="offers")


class CreationRequest(Base):
    """Журнал создавателя: по idempotency_key повтор запроса не создаёт вторую кампанию."""

    __tablename__ = "creation_requests"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    geo: Mapped[str] = mapped_column(String(8))
    offer_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=CreationStatus.PENDING)
    campaign_id: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
