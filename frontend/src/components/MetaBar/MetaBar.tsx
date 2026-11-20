import styles from './MetaBar.module.css';
import type { MetaBarProps, MetaItem, MetaTone } from './MetaBar.types';

function toneClass(tone: MetaTone | undefined): string {
  if (tone === 'ok') return styles.ok;
  if (tone === 'warn') return styles.warn;
  return '';
}

export function MetaBar({ meta, loading }: MetaBarProps) {
  if (loading) {
    return <p className={styles.hint}>читаю конфигурацию трекера…</p>;
  }
  if (meta === null) {
    return null;
  }

  const items: MetaItem[] = [
    { label: 'трекер', value: meta.keitaro_base_url, href: meta.keitaro_base_url },
    { label: 'префикс', value: meta.keitaro_prefix },
    {
      label: 'API-ключ',
      value: meta.keitaro_key_configured ? 'настроен' : 'не настроен',
      tone: meta.keitaro_key_configured ? 'ok' : 'warn'
    },
    { label: 'гео-редирект', value: meta.google_redirect_url, href: meta.google_redirect_url }
  ];

  return (
    <div className={styles.bar}>
      {items.map((item) => (
        <span key={item.label} className={styles.chip}>
          <span className={styles.label}>{item.label}</span>
          {item.href === undefined ? (
            <span className={`${styles.value} ${toneClass(item.tone)}`}>{item.value}</span>
          ) : (
            <a className={`${styles.value} ${toneClass(item.tone)}`} href={item.href} target="_blank" rel="noreferrer">
              {item.value}
            </a>
          )}
        </span>
      ))}
    </div>
  );
}
