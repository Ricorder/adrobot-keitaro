export type TabKey = 'creator' | 'editor';

export interface DeepLink {
  tab: TabKey;
  campaignId: number | null;
}

export interface TabItem {
  key: TabKey;
  label: string;
}
