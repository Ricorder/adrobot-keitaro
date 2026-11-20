import styles from './Alert.module.css';
import type { AlertKind, AlertProps } from './Alert.types';

const KIND_CLASS: Record<AlertKind, string> = {
  error: styles.error,
  ok: styles.ok,
  info: styles.info
};

export function Alert({ kind, title, children }: AlertProps) {
  return (
    <p className={`${styles.alert} ${KIND_CLASS[kind]}`} role={kind === 'error' ? 'alert' : 'status'}>
      {title === undefined ? null : <b className={styles.title}>{title}</b>}
      <span className={styles.text}>{children}</span>
    </p>
  );
}
