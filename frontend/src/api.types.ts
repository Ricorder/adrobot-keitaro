export interface MetaView {
  keitaro_base_url: string;
  keitaro_prefix: string;
  keitaro_key_configured: boolean;
  google_redirect_url: string;
}

export interface OfferOption {
  id: number;
  name: string;
  state: string;
}

export type SyncStatus = 'synced' | 'pending_add' | 'pending_remove' | 'removed_externally';

export type StreamSchema = 'redirect' | 'landings' | 'action' | string;

export type ShareMap = Record<string, number>;

export interface OfferRowView {
  id: number;
  link_id: number | null;
  offer_id: number;
  name: string;
  share: number;
  pinned_share: number | null;
  sync_status: SyncStatus;
  grey: boolean;
  yellow: boolean;
}

export interface FilterView {
  name: string;
  mode: string;
  payload: unknown[] | null;
}

export interface StreamView {
  id: number;
  name: string | null;
  position: number;
  schema: StreamSchema;
  action_type: string | null;
  action_options: Record<string, unknown> | null;
  state: string;
  yellow: boolean;
  unassigned_percent: number;
  filters: FilterView[];
  offers: OfferRowView[];
}

export interface CampaignView {
  id: number;
  alias: string;
  name: string;
  state: string;
  domain_id: number | null;
  group_id: number | null;
  traffic_source_id: number | null;
  created_by_us: boolean;
  streams: StreamView[];
}

export interface SyncStats {
  campaigns: number;
  streams: number;
  offers_in_streams: number;
  removed_externally: number;
  kept_pending: number;
  reference: Record<string, number>;
  at: string;
}

export interface PushResult extends SyncStats {
  yellow: boolean;
  shares: ShareMap;
}

export interface CreateCampaignPayload {
  name: string;
  geo: string;
  offer_id: number;
  domain_id?: number | null;
}

export interface CampaignQuery {
  q?: string;
  only_ours?: boolean;
  limit?: number;
}
