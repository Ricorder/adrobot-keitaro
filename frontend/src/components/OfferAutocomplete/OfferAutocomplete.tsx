import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, MouseEvent } from 'react';
import { errorText, searchOffers } from '../../api';
import type { OfferOption } from '../../api.types';
import styles from './OfferAutocomplete.module.css';
import type { OfferAutocompleteProps } from './OfferAutocomplete.types';

const DEBOUNCE_MS = 300;

export function OfferAutocomplete({
  value,
  onValueChange,
  onPick,
  placeholder = 'ID или часть названия',
  disabled = false,
  id
}: OfferAutocompleteProps) {
  const [options, setOptions] = useState<OfferOption[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const requestId = useRef(0);
  // после выбора в поле остаётся id — он триггернул бы новый поиск и снова открыл подсказки
  const skipNextSearch = useRef(false);

  const load = useCallback((query: string) => {
    const current = requestId.current + 1;
    requestId.current = current;
    setLoading(true);
    setError(null);
    searchOffers(query.length > 0 ? query : undefined)
      .then((rows) => {
        if (requestId.current !== current) return;
        setOptions(rows);
        setHighlight(-1);
        setOpen(true);
      })
      .catch((loadError: unknown) => {
        if (requestId.current !== current) return;
        setOptions(null);
        setError(errorText(loadError));
        setOpen(true);
      })
      .finally(() => {
        if (requestId.current === current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    const trimmed = value.trim();
    if (skipNextSearch.current) {
      skipNextSearch.current = false;
      return;
    }
    if (trimmed.length === 0) {
      setOptions(null);
      setOpen(false);
      return;
    }
    const timer = window.setTimeout(() => load(trimmed), DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [value, load]);

  const choose = (option: OfferOption) => {
    skipNextSearch.current = true;
    requestId.current += 1;
    setOpen(false);
    setOptions(null);
    onValueChange(String(option.id));
    onPick(option);
  };

  const list = options ?? [];

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false);
      return;
    }
    if (!open || list.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlight((index) => (index + 1) % list.length);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlight((index) => (index <= 0 ? list.length - 1 : index - 1));
      return;
    }
    if (event.key === 'Enter' && highlight >= 0 && highlight < list.length) {
      event.preventDefault();
      choose(list[highlight]);
    }
  };

  const keepFocusOnMousedown = (event: MouseEvent) => {
    event.preventDefault();
  };

  return (
    <div className={styles.wrap}>
      <input
        id={id}
        className={styles.input}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        onChange={(event) => onValueChange(event.target.value)}
        onFocus={() => {
          if (options === null) load(value.trim());
        }}
        onBlur={() => setOpen(false)}
        onKeyDown={handleKeyDown}
      />
      {open ? (
        <ul className={styles.list} onMouseDown={keepFocusOnMousedown}>
          {loading ? <li className={styles.note}>ищу офферы…</li> : null}
          {error !== null ? <li className={styles.note}>ошибка поиска: {error}</li> : null}
          {!loading && error === null && options !== null && options.length === 0 ? (
            <li className={styles.note}>ничего не найдено</li>
          ) : null}
          {list.map((option, index) => (
            <li key={option.id}>
              <button
                type="button"
                className={index === highlight ? `${styles.item} ${styles.itemActive}` : styles.item}
                onMouseDown={keepFocusOnMousedown}
                onClick={() => choose(option)}
              >
                <span className={styles.itemId}>#{option.id}</span>
                <span className={styles.itemName}>{option.name}</span>
                <span className={styles.itemState}>{option.state}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
