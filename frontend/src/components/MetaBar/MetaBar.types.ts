import type { MetaView } from '../../api.types';

export type MetaTone = 'ok' | 'warn';

export interface MetaItem {
  label: string;
  value: string;
  href?: string;
  tone?: MetaTone;
}

export interface MetaBarProps {
  meta: MetaView | null;
  loading: boolean;
}
