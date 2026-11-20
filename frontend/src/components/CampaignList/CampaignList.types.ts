import type { CampaignView } from '../../api.types';

export interface CampaignListProps {
  campaigns: CampaignView[] | null;
  loading: boolean;
  error: string | null;
  activeId: number | null;
  onOpen: (campaignId: number) => void;
}
