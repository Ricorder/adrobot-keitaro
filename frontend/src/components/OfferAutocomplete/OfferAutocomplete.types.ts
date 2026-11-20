import type { OfferOption } from '../../api.types';

export interface OfferAutocompleteProps {
  value: string;
  onValueChange: (value: string) => void;
  onPick: (option: OfferOption) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
}
