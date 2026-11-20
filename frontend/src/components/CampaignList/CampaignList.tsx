import styles from './CampaignList.module.css';
import type { CampaignListProps } from './CampaignList.types';

export function CampaignList({ campaigns, loading, error, activeId, onOpen }: CampaignListProps) {
  if (error !== null) {
    return <p className={styles.error}>список не загрузился: {error}</p>;
  }
  if (loading && campaigns === null) {
    return <p className={styles.note}>грузю кампании…</p>;
  }
  if (campaigns === null) {
    return <p className={styles.note}>список ещё не загружен.</p>;
  }
  if (campaigns.length === 0) {
    return <p className={styles.note}>кампаний по фильтру нет.</p>;
  }

  return (
    <ul className={styles.list}>
      {campaigns.map((campaign) => (
        <li key={campaign.id}>
          <button
            type="button"
            className={
              campaign.id === activeId ? `${styles.item} ${styles.itemActive}` : styles.item
            }
            onClick={() => onOpen(campaign.id)}
          >
            <span className={styles.name}>{campaign.name}</span>
            <span className={styles.sub}>
              <span>#{campaign.id}</span>
              <span className={styles.alias}>{campaign.alias}</span>
              <span className={styles.badge}>{campaign.state}</span>
              <span className={styles.badge}>потоков {campaign.streams.length}</span>
              {campaign.created_by_us ? (
                <span className={`${styles.badge} ${styles.ours}`}>наша</span>
              ) : (
                <span className={styles.badge}>не наша</span>
              )}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
