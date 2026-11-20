import { useEffect, useState } from 'react';
import { errorText, fetchMeta } from '../api';
import type { MetaView } from '../api.types';
import { MetaBar } from '../components/MetaBar/MetaBar';
import { CreatorPage } from '../pages/CreatorPage/CreatorPage';
import { EditorPage } from '../pages/EditorPage/EditorPage';
import styles from './App.module.css';
import type { DeepLink, TabItem, TabKey } from './App.types';

const TABS: TabItem[] = [
  { key: 'creator', label: 'Создаватор' },
  { key: 'editor', label: 'Редактор' }
];

function parseHash(hash: string): DeepLink {
  const parts = hash.replace(/^#\/?/, '').split('/').filter((part) => part.length > 0);
  const tab: TabKey = parts[0] === 'editor' ? 'editor' : 'creator';
  const candidate = Number.parseInt(parts[1] ?? '', 10);
  return { tab, campaignId: Number.isNaN(candidate) ? null : candidate };
}

export function App() {
  const [link, setLink] = useState<DeepLink>(() => parseHash(window.location.hash));
  const [meta, setMeta] = useState<MetaView | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetchMeta()
      .then((value) => {
        if (alive) {
          setMeta(value);
          setMetaError(null);
        }
      })
      .catch((error: unknown) => {
        if (alive) setMetaError(errorText(error));
      })
      .finally(() => {
        if (alive) setMetaLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const onHashChange = () => setLink(parseHash(window.location.hash));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const selectTab = (tab: TabKey) => {
    window.location.hash = `#/${tab}`;
  };

  return (
    <div className={styles.shell}>
      <header className={styles.topLine}>
        <div>
          <h1 className={styles.title}>Adrobot — обёртка над Keitaro</h1>
          <p className={styles.subtitle}>Создаватор кампаний и редактор потоков</p>
        </div>
        {metaError === null ? null : <p className={styles.metaError}>meta: {metaError}</p>}
      </header>

      <MetaBar meta={meta} loading={metaLoading} />

      <nav className={styles.tabs}>
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={link.tab === item.key ? `${styles.tab} ${styles.tabActive}` : styles.tab}
            aria-pressed={link.tab === item.key}
            onClick={() => selectTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {link.tab === 'creator' ? (
        <CreatorPage meta={meta} />
      ) : (
        <EditorPage requestedCampaignId={link.campaignId} />
      )}
    </div>
  );
}
