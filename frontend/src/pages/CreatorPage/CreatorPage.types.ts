import type { CampaignView, CreateCampaignPayload, MetaView, OfferOption } from '../../api.types';

export interface CreatorPageProps {
  meta: MetaView | null;
}

export interface EditLink {
  href: string;
  caption: string;
  external: boolean;
}

export interface LastAttempt {
  payload: CreateCampaignPayload;
  key: string;
}

export type PickedOffer = OfferOption | null;

export type CreatedCampaign = CampaignView | null;
