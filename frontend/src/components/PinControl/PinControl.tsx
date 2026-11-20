import { useEffect, useState } from 'react';
import { Button } from '../Button/Button';
import styles from './PinControl.module.css';
import type { PinControlProps } from './PinControl.types';

export function PinControl({ rowId, current, busy, onSubmit }: PinControlProps) {
  const [draft, setDraft] = useState<string>(current === null ? '' : String(current));

  useEffect(() => {
    setDraft(current === null ? '' : String(current));
  }, [current]);

  const trimmed = draft.trim();
  const parsed = Number.parseInt(trimmed, 10);
  const isNumber = trimmed.length > 0 && !Number.isNaN(parsed);
  const inRange = isNumber && parsed >= 0 && parsed <= 100;

  return (
    <span className={styles.wrap}>
      <input
        id={`pin-${rowId}`}
        className={isNumber && !inRange ? `${styles.input} ${styles.inputInvalid}` : styles.input}
        value={draft}
        inputMode="numeric"
        placeholder="—"
        disabled={busy}
        onChange={(event) => setDraft(event.target.value)}
      />
      <Button disabled={busy || !inRange} onClick={() => onSubmit(parsed)}>
        {current === null ? 'Закрепить' : 'Обновить'}
      </Button>
      {current === null ? null : (
        <Button disabled={busy} onClick={() => onSubmit(null)}>
          Снять
        </Button>
      )}
      {isNumber && !inRange ? <span className={styles.hint}>доля 0–100</span> : null}
    </span>
  );
}
