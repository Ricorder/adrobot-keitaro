export interface PinControlProps {
  rowId: number;
  current: number | null;
  busy: boolean;
  onSubmit: (share: number | null) => void;
}
