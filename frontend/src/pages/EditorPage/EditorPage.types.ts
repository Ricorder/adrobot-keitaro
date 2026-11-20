import type { CampaignView } from '../../api.types';

export interface EditorPageProps {
  requestedCampaignId: number | null;
}

export interface CampaignFilter {
  q: string;
  onlyOurs: boolean;
}

export type CampaignListState = CampaignView[] | null;

export type OpenedCampaign = CampaignView | null;
