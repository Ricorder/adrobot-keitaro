import type { OfferRowView, SyncStatus } from '../../api.types';

export interface OfferTableProps {
  rows: OfferRowView[];
  busy: boolean;
  onRemove: (rowId: number) => void;
  onRestore: (rowId: number) => void;
  onPin: (rowId: number, share: number | null) => void;
}

export type StatusCaptions = Record<SyncStatus, string>;
