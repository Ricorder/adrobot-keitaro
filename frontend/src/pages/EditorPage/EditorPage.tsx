import { useCallback, useEffect, useRef, useState } from 'react';
import {
  addStreamOffer,
  errorText,
  fetchCampaign,
  listCampaigns,
  pinOfferRow,
  pushStream,
  removeOfferRow,
  restoreOfferRow,
  runSync
} from '../../api';
import type { PushResult, SyncStats } from '../../api.types';
import { Alert } from '../../components/Alert/Alert';
import { Button } from '../../components/Button/Button';
import { CampaignList } from '../../components/CampaignList/CampaignList';
import { StreamCard } from '../../components/StreamCard/StreamCard';
import type { StreamFeedback } from '../../components/StreamCard/StreamCard.types';
import styles from './EditorPage.module.css';
import type {
  CampaignListState,
  EditorPageProps,
  OpenedCampaign
} from './EditorPage.types';

const LIST_LIMIT = 100;
const SEARCH_DEBOUNCE_MS = 350;

function pushSummary(result: PushResult): string {
  const shares = Object.entries(result.shares)
    .map(([offerId, share]) => `#${offerId} → ${share} %`)
    .join(', ');
  return [
    `потоков ${result.streams}`,
    `офферов в потоках ${result.offers_in_streams}`,
    `удалено вне нас ${result.removed_externally}`,
    `сохранено неопубликованного ${result.kept_pending}`,
    `жёлтый после пуша: ${result.yellow ? 'да' : 'нет'}`,
    shares.length > 0 ? `доли из трекера: ${shares}` : 'долей нет'
  ].join(' · ');
}

function syncSummary(stats: SyncStats): string {
  const reference = Object.entries(stats.reference)
    .map(([name, count]) => `${name} ${count}`)
    .join(', ');
  return [
    `кампаний ${stats.campaigns}`,
    `потоков ${stats.streams}`,
    `офферов в потоках ${stats.offers_in_streams}`,
    `удалено вне нас ${stats.removed_externally}`,
    `сохранено неопубликованного ${stats.kept_pending}`,
    `справочник: ${reference}`,
    `в ${stats.at}`
  ].join(' · ');
}

export function EditorPage({ requestedCampaignId }: EditorPageProps) {
  const [q, setQ] = useState('');
  const [onlyOurs, setOnlyOurs] = useState(false);
  const [campaigns, setCampaigns] = useState<CampaignListState>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [listNote, setListNote] = useState<string | null>(null);

  const [openedId, setOpenedId] = useState<number | null>(null);
  const [opened, setOpened] = useState<OpenedCampaign>(null);
  const [openedLoading, setOpenedLoading] = useState(false);
  const [openedError, setOpenedError] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [feedback, setFeedback] = useState<StreamFeedback | null>(null);
  const listRequest = useRef(0);

  const loadList = useCallback(async (query: string, oursOnly: boolean) => {
    const current = listRequest.current + 1;
    listRequest.current = current;
    setListLoading(true);
    setListError(null);
    const trimmed = query.trim();
    try {
      const rows = await listCampaigns({
        q: trimmed.length > 0 ? trimmed : undefined,
        only_ours: oursOnly,
        limit: LIST_LIMIT
      });
      if (listRequest.current === current) setCampaigns(rows);
    } catch (error: unknown) {
      if (listRequest.current === current) {
        setCampaigns(null);
        setListError(errorText(error));
      }
    } finally {
      if (listRequest.current === current) setListLoading(false);
    }
  }, []);

  useEffect(() => {
    const delay = q.trim().length > 0 ? SEARCH_DEBOUNCE_MS : 0;
    const timer = window.setTimeout(() => {
      void loadList(q, onlyOurs);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [q, onlyOurs, loadList]);

  const openCampaign = useCallback(async (campaignId: number) => {
    setOpenedId(campaignId);
    setOpenedLoading(true);
    setOpenedError(null);
    setFeedback(null);
    try {
      setOpened(await fetchCampaign(campaignId));
    } catch (error: unknown) {
      setOpened(null);
      setOpenedError(errorText(error));
    } finally {
      setOpenedLoading(false);
    }
  }, []);

  const reloadOpened = useCallback(async (campaignId: number) => {
    try {
      setOpened(await fetchCampaign(campaignId));
    } catch (error: unknown) {
      setOpenedError(errorText(error));
    }
  }, []);

  useEffect(() => {
    if (requestedCampaignId !== null) void openCampaign(requestedCampaignId);
  }, [requestedCampaignId, openCampaign]);

  // доли после любой правки перечитываем у backend: на клиенте они не пересчитываются
  const runOp = async (streamId: number, op: () => Promise<unknown>): Promise<void> => {
    if (busy || openedId === null) return;
    setBusy(true);
    setFeedback(null);
    try {
      await op();
      await reloadOpened(openedId);
    } catch (error: unknown) {
      setFeedback({ streamId, kind: 'error', text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const push = async (streamId: number): Promise<void> => {
    if (busy || openedId === null) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await pushStream(streamId);
      await reloadOpened(openedId);
      setFeedback({ streamId, kind: 'ok', text: pushSummary(result) });
    } catch (error: unknown) {
      setFeedback({ streamId, kind: 'error', text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const sync = async (): Promise<void> => {
    if (syncing) return;
    setSyncing(true);
    setListNote(null);
    setListError(null);
    try {
      const stats = await runSync();
      setListNote(syncSummary(stats));
      await loadList(q, onlyOurs);
      if (openedId !== null) await reloadOpened(openedId);
    } catch (error: unknown) {
      setListError(errorText(error));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className={styles.page}>
      <aside className={styles.side}>
        <div className={styles.toolbar}>
          <input
            className={styles.search}
            value={q}
            placeholder="поиск по названию или alias"
            onChange={(event) => setQ(event.target.value)}
          />
          <div className={styles.filtersRow}>
            <label className={styles.check}>
              <input
                className={styles.checkInput}
                type="checkbox"
                checked={onlyOurs}
                onChange={(event) => setOnlyOurs(event.target.checked)}
              />
              только наши
            </label>
            <Button disabled={syncing || busy} onClick={() => void sync()}>
              {syncing ? 'Синхронизирую…' : 'Синхронизировать'}
            </Button>
          </div>
          {listNote === null ? null : <p className={styles.note}>{listNote}</p>}
          {listLoading ? <p className={styles.note}>обновляю список…</p> : null}
        </div>

        <CampaignList
          campaigns={campaigns}
          loading={listLoading}
          error={listError}
          activeId={openedId}
          onOpen={(campaignId) => void openCampaign(campaignId)}
        />
      </aside>

      <section className={styles.panel}>
        {openedId === null ? (
          <p className={styles.empty}>Выберите кампанию слева — откроются её потоки.</p>
        ) : (
          <>
            <div className={styles.panelHead}>
              <div>
                <h2 className={styles.heading}>{opened?.name ?? `кампания #${openedId}`}</h2>
                <div className={styles.sub}>
                  <span>#{openedId}</span>
                  {opened === null ? null : (
                    <>
                      <span className={styles.alias}>{opened.alias}</span>
                      <span className={styles.badge}>state {opened.state}</span>
                      <span className={styles.badge}>domain {opened.domain_id ?? '—'}</span>
                      <span className={styles.badge}>group {opened.group_id ?? '—'}</span>
                      <span className={styles.badge}>
                        source {opened.traffic_source_id ?? '—'}
                      </span>
                      <span className={styles.badge}>
                        {opened.created_by_us ? 'создана нами' : 'не наша'}
                      </span>
                    </>
                  )}
                </div>
              </div>
              <Button
                variant="primary"
                disabled={busy || openedLoading}
                onClick={() => void openCampaign(openedId)}
              >
                F-Streams
              </Button>
            </div>

            {openedLoading ? <p className={styles.note}>читаю потоки из трекера…</p> : null}
            {busy ? <p className={styles.note}>выполняю операцию…</p> : null}
            {openedError === null ? null : <Alert kind="error">{openedError}</Alert>}

            {opened === null ? null : opened.streams.length === 0 ? (
              <p className={styles.empty}>у кампании нет потоков — нажмите F-Streams.</p>
            ) : (
              <div className={styles.streams}>
                {opened.streams.map((stream) => (
                  <StreamCard
                    key={stream.id}
                    stream={stream}
                    busy={busy}
                    feedback={feedback !== null && feedback.streamId === stream.id ? feedback : null}
                    onPush={(streamId) => void push(streamId)}
                    onAddOffer={(streamId, offerId) =>
                      void runOp(streamId, () => addStreamOffer(streamId, offerId))
                    }
                    onRemoveRow={(streamId, rowId) =>
                      void runOp(streamId, () => removeOfferRow(rowId))
                    }
                    onRestoreRow={(streamId, rowId) =>
                      void runOp(streamId, () => restoreOfferRow(rowId))
                    }
                    onPinRow={(streamId, rowId, share) =>
                      void runOp(streamId, () => pinOfferRow(rowId, share))
                    }
                  />
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
