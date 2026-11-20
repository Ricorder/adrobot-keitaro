import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { createCampaign, errorText } from '../../api';
import type { CreateCampaignPayload } from '../../api.types';
import { Alert } from '../../components/Alert/Alert';
import { Button } from '../../components/Button/Button';
import { OfferAutocomplete } from '../../components/OfferAutocomplete/OfferAutocomplete';
import styles from './CreatorPage.module.css';
import type {
  CreatedCampaign,
  CreatorPageProps,
  EditLink,
  LastAttempt,
  PickedOffer
} from './CreatorPage.types';

function makeIdempotencyKey(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return `creator-${uuid ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

function samePayload(left: CreateCampaignPayload, right: CreateCampaignPayload): boolean {
  return (
    left.name === right.name &&
    left.geo === right.geo &&
    left.offer_id === right.offer_id &&
    left.domain_id === right.domain_id
  );
}

function trackerCampaignUrl(baseUrl: string, campaignId: number): string {
  return `${baseUrl.replace(/\/+$/, '')}/admin/campaigns/${campaignId}`;
}

function editorUrl(campaignId: number): string {
  return `#/editor/${campaignId}`;
}

export function CreatorPage({ meta }: CreatorPageProps) {
  const [name, setName] = useState('');
  const [geo, setGeo] = useState('');
  const [offerText, setOfferText] = useState('');
  const [picked, setPicked] = useState<PickedOffer>(null);
  const [created, setCreated] = useState<CreatedCampaign>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lastAttempt = useRef<LastAttempt | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;

    const offerId = Number.parseInt(offerText.trim(), 10);
    if (Number.isNaN(offerId) || offerId <= 0) {
      setError('ID оффера должен быть целым числом больше нуля');
      return;
    }

    const payload: CreateCampaignPayload = {
      name: name.trim(),
      geo: geo.trim().toUpperCase(),
      offer_id: offerId
    };

    const previous = lastAttempt.current;
    const key =
      previous !== null && samePayload(previous.payload, payload)
        ? previous.key
        : makeIdempotencyKey();
    lastAttempt.current = { payload, key };

    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const campaign = await createCampaign(payload, key);
      setCreated(campaign);
      setName('');
      setGeo('');
      setOfferText('');
      setPicked(null);
      lastAttempt.current = null;
    } catch (submitError: unknown) {
      setError(errorText(submitError));
    } finally {
      setBusy(false);
    }
  };

  const links: EditLink[] =
    created === null
      ? []
      : [
          ...(meta === null
            ? []
            : [
                {
                  href: trackerCampaignUrl(meta.keitaro_base_url, created.id),
                  caption: 'кампания в админке Keitaro',
                  external: true
                }
              ]),
          {
            href: editorUrl(created.id),
            caption: 'та же кампания в редакторе потоков',
            external: false
          }
        ];

  return (
    <div className={styles.page}>
      <form className={styles.form} onSubmit={(event) => void submit(event)}>
        <h2 className={styles.heading}>Новая кампания</h2>

        <label className={styles.field}>
          <span className={styles.label}>Название кампании</span>
          <input
            className={styles.input}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="например: PE nutra sweep"
            required
            maxLength={255}
            autoComplete="off"
          />
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Гео — ISO2 код страны</span>
          <input
            className={styles.geo}
            value={geo}
            onChange={(event) => setGeo(event.target.value.toUpperCase())}
            placeholder="PE"
            required
            minLength={2}
            maxLength={2}
            autoComplete="off"
          />
          <span className={styles.hint}>Двухбуквенный код, подсказка: PE</span>
        </label>

        <div className={styles.field}>
          <span className={styles.label}>ID оффера в Keitaro</span>
          <OfferAutocomplete
            value={offerText}
            onValueChange={setOfferText}
            onPick={(option) => setPicked(option)}
            disabled={busy}
          />
          {picked === null ? (
            <span className={styles.hint}>
              автокомплит ищет по /api/offers: можно id или часть названия
            </span>
          ) : (
            <span className={styles.picked}>
              выбран оффер #{picked.id} — {picked.name}
            </span>
          )}
        </div>

        <div className={styles.actions}>
          <Button variant="primary" type="submit" disabled={busy}>
            {busy ? 'Создаю…' : 'Создать'}
          </Button>
        </div>
      </form>

      <div className={styles.side}>
        {error === null ? null : <Alert kind="error" title="Backend">{error}</Alert>}
        {created === null ? null : (
          <>
            <h2 className={styles.heading}>Готово</h2>
            <p className={styles.idLine}>
              <span>
                кампания <b>#{created.id}</b>
              </span>
              <span className={styles.alias}>{created.alias}</span>
              <span className={styles.hint}>
                состояние: {created.state} · потоков: {created.streams.length}
              </span>
            </p>
            <ul className={styles.links}>
              {links.map((link) => (
                <li key={link.href} className={styles.linkRow}>
                  <a
                    className={styles.linkValue}
                    href={link.href}
                    target={link.external ? '_blank' : undefined}
                    rel={link.external ? 'noreferrer' : undefined}
                  >
                    {link.href}
                  </a>
                  <span className={styles.caption}>{link.caption}</span>
                </li>
              ))}
            </ul>
            <div className={styles.actions}>
              <Button
                variant="primary"
                onClick={() => {
                  window.location.hash = editorUrl(created.id);
                }}
              >
                Открыть в редакторе
              </Button>
            </div>
          </>
        )}
        {created === null && error === null ? (
          <p className={styles.muted}>
            Backend создаст кампанию и два потока: гео-фильтр с редиректом на Google и офферный
            поток с долей 100 %. Ошибку показываем текстом из ответа сервера.
          </p>
        ) : null}
      </div>
    </div>
  );
}
