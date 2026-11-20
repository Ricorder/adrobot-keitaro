import type { OfferRowView } from '../../api.types';
import { Button } from '../Button/Button';
import { PinControl } from '../PinControl/PinControl';
import styles from './OfferTable.module.css';
import type { OfferTableProps, StatusCaptions } from './OfferTable.types';

const STATUS_CAPTIONS: StatusCaptions = {
  synced: 'синхронизировано',
  pending_add: 'не опубликован',
  pending_remove: 'помечен на удаление',
  removed_externally: 'удалён в трекере'
};

function rowClass(row: OfferRowView): string {
  const classes = [styles.row];
  if (row.grey) classes.push(styles.grey);
  if (row.yellow) classes.push(styles.yellow);
  return classes.join(' ');
}

export function OfferTable({ rows, busy, onRemove, onRestore, onPin }: OfferTableProps) {
  if (rows.length === 0) {
    return <p className={styles.empty}>в потоке пока нет ни одного оффера</p>;
  }

  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.th}>Название</th>
            <th className={styles.th}>id</th>
            <th className={styles.th}>доля, %</th>
            <th className={styles.th}>статус</th>
            <th className={styles.th}>закреплено</th>
            <th className={styles.th}>действия</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className={rowClass(row)}>
              <td className={styles.td}>{row.name}</td>
              <td className={`${styles.td} ${styles.mono}`}>#{row.offer_id}</td>
              <td className={`${styles.td} ${styles.share}`}>{row.share} %</td>
              <td className={styles.td}>
                <span className={styles.badge}>{STATUS_CAPTIONS[row.sync_status]}</span>
              </td>
              <td className={styles.td}>
                {row.pinned_share === null ? (
                  <span className={styles.badge}>нет</span>
                ) : (
                  <span className={`${styles.badge} ${styles.badgePinned}`}>
                    {row.pinned_share} %
                  </span>
                )}
              </td>
              <td className={styles.td}>
                <div className={styles.actions}>
                  <PinControl
                    rowId={row.id}
                    current={row.pinned_share}
                    busy={busy}
                    onSubmit={(share) => onPin(row.id, share)}
                  />
                  {row.grey ? (
                    <Button disabled={busy} onClick={() => onRestore(row.id)}>
                      Back
                    </Button>
                  ) : (
                    <Button variant="danger" disabled={busy} onClick={() => onRemove(row.id)}>
                      Remove
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
