import type { FilterView } from '../../api.types';
import { Alert } from '../Alert/Alert';
import { Button } from '../Button/Button';
import { OfferSearch } from '../OfferSearch/OfferSearch';
import { OfferTable } from '../OfferTable/OfferTable';
import styles from './StreamCard.module.css';
import type { StreamCardProps } from './StreamCard.types';

const OFFER_SCHEMA = 'landings';

function filterCaption(filter: FilterView): string {
  const payload =
    filter.payload === null ? 'без параметров' : filter.payload.map((item) => String(item)).join(', ');
  return `${filter.name} · ${filter.mode} · ${payload}`;
}

export function StreamCard({
  stream,
  busy,
  feedback,
  onPush,
  onAddOffer,
  onRemoveRow,
  onRestoreRow,
  onPinRow
}: StreamCardProps) {
  const isOfferFlow = stream.schema === OFFER_SCHEMA;
  const classes = stream.yellow ? `${styles.card} ${styles.cardYellow}` : styles.card;

  return (
    <section className={classes}>
      <div className={styles.head}>
        <div className={styles.titles}>
          <h3 className={styles.title}>Поток #{stream.id}</h3>
          <span className={styles.position}>
            позиция {stream.position} · {stream.name ?? 'без названия'}
          </span>
        </div>
        <div className={styles.badges}>
          <span className={styles.badge}>schema: {stream.schema}</span>
          <span className={styles.badge}>state: {stream.state}</span>
          <span className={styles.badge}>офферов: {stream.offers.length}</span>
          {stream.yellow ? (
            <span className={`${styles.badge} ${styles.yellowBadge}`}>
              жёлтый — есть неопубликованные изменения
            </span>
          ) : null}
          {stream.unassigned_percent > 0 ? (
            <span className={styles.unassigned}>
              не распределено {stream.unassigned_percent} %
            </span>
          ) : null}
          <Button variant="primary" disabled={busy} onClick={() => onPush(stream.id)}>
            Push KT
          </Button>
        </div>
      </div>

      {feedback === null ? null : (
        <Alert kind={feedback.kind} title={feedback.kind === 'error' ? 'Операция не прошла' : 'Push KT'}>
          {feedback.text}
        </Alert>
      )}

      <div className={styles.meta}>
        <div className={styles.metaItem}>
          <span className={styles.metaLabel}>действие</span>
          <span className={styles.metaValue}>{stream.action_type ?? '—'}</span>
        </div>
        <div className={styles.metaItem}>
          <span className={styles.metaLabel}>параметры действия</span>
          <pre className={styles.json}>
            {stream.action_options === null ? '—' : JSON.stringify(stream.action_options, null, 2)}
          </pre>
        </div>
        <div className={styles.metaItem}>
          <span className={styles.metaLabel}>фильтры</span>
          {stream.filters.length === 0 ? (
            <span className={styles.metaValue}>фильтров нет</span>
          ) : (
            stream.filters.map((filter) => (
              <span key={`${filter.name}-${filter.mode}`} className={styles.metaValue}>
                {filterCaption(filter)}
              </span>
            ))
          )}
        </div>
      </div>

      {isOfferFlow ? (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>офферы потока</h4>
          <OfferSearch busy={busy} onAdd={(offerId) => onAddOffer(stream.id, offerId)} />
          <OfferTable
            rows={stream.offers}
            busy={busy}
            onRemove={(rowId) => onRemoveRow(stream.id, rowId)}
            onRestore={(rowId) => onRestoreRow(stream.id, rowId)}
            onPin={(rowId, share) => onPinRow(stream.id, rowId, share)}
          />
        </div>
      ) : null}
    </section>
  );
}
