import type { ReactNode } from 'react';

export type AlertKind = 'error' | 'ok' | 'info';

export interface AlertProps {
  kind: AlertKind;
  title?: string;
  children: ReactNode;
}
