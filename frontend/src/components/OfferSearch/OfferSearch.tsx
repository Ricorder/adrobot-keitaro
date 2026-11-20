import { useState } from 'react';
import { errorText, searchOffers } from '../../api';
import type { OfferOption } from '../../api.types';
import { Button } from '../Button/Button';
import styles from './OfferSearch.module.css';
import type { OfferSearchProps } from './OfferSearch.types';

export function OfferSearch({ busy, onAdd }: OfferSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<OfferOption[] | null>(null);
  const [selected, setSelected] = useState<OfferOption | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const find = async () => {
    setLoading(true);
    setError(null);
    setSelected(null);
    const trimmed = query.trim();
    try {
      setResults(await searchOffers(trimmed.length > 0 ? trimmed : undefined));
    } catch (findError: unknown) {
      setResults(null);
      setError(errorText(findError));
    } finally {
      setLoading(false);
    }
  };

  const add = () => {
    if (selected === null) return;
    onAdd(selected.id);
    setSelected(null);
    setResults(null);
    setQuery('');
  };

  return (
    <div>
      <div className={styles.bar}>
        <input
          className={styles.input}
          value={query}
          placeholder="id или часть названия"
          disabled={busy || loading}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button disabled={busy || loading} onClick={() => void find()}>
          {loading ? 'Ищу…' : 'Найти'}
        </Button>
        <Button variant="primary" disabled={busy || selected === null} onClick={add}>
          Добавить
        </Button>
      </div>

      {error === null ? null : <p className={styles.error}>поиск не удался: {error}</p>}
      {results === null ? null : results.length === 0 ? (
        <p className={styles.note}>офферов по запросу нет</p>
      ) : (
        <ul className={styles.results}>
          {results.map((option) => (
            <li key={option.id}>
              <button
                type="button"
                className={
                  selected?.id === option.id ? `${styles.pick} ${styles.pickSelected}` : styles.pick
                }
                disabled={busy}
                onClick={() => setSelected(option)}
              >
                <span className={styles.id}>#{option.id}</span>
                <span>{option.name}</span>
                <span className={styles.id}>{option.state}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
