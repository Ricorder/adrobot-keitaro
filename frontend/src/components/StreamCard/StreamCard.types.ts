import type { StreamView } from '../../api.types';

export type FeedbackKind = 'error' | 'ok';

export interface StreamFeedback {
  streamId: number;
  kind: FeedbackKind;
  text: string;
}

export interface StreamCardProps {
  stream: StreamView;
  busy: boolean;
  feedback: StreamFeedback | null;
  onPush: (streamId: number) => void;
  onAddOffer: (streamId: number, offerId: number) => void;
  onRemoveRow: (streamId: number, rowId: number) => void;
  onRestoreRow: (streamId: number, rowId: number) => void;
  onPinRow: (streamId: number, rowId: number, share: number | null) => void;
}
