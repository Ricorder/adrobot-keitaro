"""Модели запросов и ответов HTTP API."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class CreateCampaignBody(BaseModel):
    name: str = Field(min_length=1, description="Название кампании")
    geo: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2, например PE")
    offer_id: int = Field(gt=0, description="Идентификатор оффера в Keitaro")
    domain_id: int | None = Field(default=None, description="Если не указан — берём активный домен")


class AddOfferBody(BaseModel):
    offer_id: int = Field(gt=0)


class PinBody(BaseModel):
    share: int | None = Field(default=None, ge=0, le=100, description="null — снять закрепление")


class OfferRowView(BaseModel):
    id: int
    link_id: int | None
    offer_id: int
    name: str
    share: int
    pinned_share: int | None
    sync_status: str
    grey: bool
    yellow: bool


class FilterView(BaseModel):
    name: str
    mode: str
    payload: list | None


class StreamView(BaseModel):
    # поле называется flow_schema: schema затеняет атрибут BaseModel и Pydantic на это ругается,
    # а в JSON ключ остаётся прежним — трекер и фронт говорят словом schema
    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str | None
    position: int
    flow_schema: str = Field(
        validation_alias=AliasChoices("schema", "flow_schema"), serialization_alias="schema"
    )
    action_type: str | None
    action_options: dict | None
    state: str
    yellow: bool
    unassigned_percent: int
    filters: list[FilterView]
    offers: list[OfferRowView]


class CampaignView(BaseModel):
    id: int
    alias: str
    name: str
    state: str
    domain_id: int | None
    group_id: int | None
    traffic_source_id: int | None
    created_by_us: bool
    streams: list[StreamView]


class OfferOption(BaseModel):
    id: int
    name: str
    state: str
