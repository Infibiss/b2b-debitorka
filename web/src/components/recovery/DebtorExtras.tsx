import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Download } from 'lucide-react';
import { api, dateText, money, post, today } from '../../api';
import { t } from '../../i18n';
import type { DebtorDetail, Notify } from './types';

const kinds: [string, string][] = [
  ['contract', t('Договор')],
  ['performance', t('Акт, УПД или накладная')],
  ['reconciliation', t('Акт сверки')],
  ['correspondence', t('Переписка с должником')],
];
const MAX_FILE = 1_000_000;

type Evidence = {
  id: string;
  invoice_id: string;
  kind: string;
  reference: string;
  occurred_on: string;
  filename: string;
  download_url: string | null;
};

async function toBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}

/** Primary documents for the debt. They feed the court-readiness check. */
export function EvidencePanel({
  debtor,
  notify,
  onSaved,
}: {
  debtor: DebtorDetail;
  notify: Notify;
  onSaved: () => void;
}) {
  const open = debtor.invoices.filter((item) => item.balance > 0);
  const [items, setItems] = useState<Evidence[]>([]);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState('all');
  const ids = debtor.invoices.map((item) => item.id).join(',');
  const load = useCallback(() => {
    if (!ids) return;
    void Promise.all(
      ids.split(',').map((id) => api<{ items: Evidence[] }>(`/portfolio/invoices/${id}/evidence`))
    )
      .then((pages) => setItems(pages.flatMap((page) => page.items)))
      .catch((error) => notify(error.message, true));
  }, [ids, notify]);
  useEffect(load, [load]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get('file') as File | null;
    const attached = file && file.size > 0 ? file : null;
    if (attached && attached.size > MAX_FILE) {
      notify(t('Выберите PDF или изображение до 1 МБ.'), true);
      return;
    }
    setBusy(true);
    try {
      const content = attached ? await toBase64(attached) : '';
      const invoiceIds = target === 'all' ? open.map((item) => item.id) : [target];
      for (const invoiceId of invoiceIds)
        await post(`/portfolio/invoices/${invoiceId}/evidence`, {
          kind: data.get('kind'),
          reference: data.get('reference'),
          occurred_on: data.get('occurred_on'),
          note: '',
          filename: attached?.name ?? '',
          content_base64: content,
        });
      form.reset();
      setTarget('all');
      load();
      onSaved();
      notify(t('Документ добавлен'));
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const unique = items.filter(
    (item, index) =>
      items.findIndex((other) => other.kind === item.kind && other.reference === item.reference) ===
      index
  );
  const kindName = (kind: string) =>
    kinds.find(([key]) => key === kind)?.[1] ?? t('Другой документ');
  return (
    <section className="rc-card">
      <h2>{t('Документы по долгу')}</h2>
      <ul className="rc-documents">
        {unique.map((item) => (
          <li key={item.id}>
            <span>
              {kindName(item.kind)} · {item.reference} · {dateText(item.occurred_on)}
            </span>
            {item.download_url && (
              <a href={item.download_url}>
                <Download size={14} />
                {item.filename}
              </a>
            )}
          </li>
        ))}
        {unique.length === 0 && (
          <li className="rc-muted">
            {t('Добавьте договор и акт или УПД: без них суд не примет долг.')}
          </li>
        )}
      </ul>
      {open.length > 0 && (
        <form className="rc-action-form" onSubmit={(event) => void submit(event)}>
          <h3>{t('Добавить документ')}</h3>
          <label>
            {t('Вид документа')}
            <select name="kind" defaultValue="contract">
              {kinds.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Номер и название')}
            <input
              name="reference"
              required
              minLength={3}
              maxLength={1000}
              placeholder={t('Договор № 12 от 01.02.2026')}
            />
          </label>
          <label>
            {t('Дата документа')}
            <input name="occurred_on" type="date" required max={today()} defaultValue={today()} />
          </label>
          <label>
            {t('Каких счетов касается')}
            <select value={target} onChange={(event) => setTarget(event.target.value)}>
              <option value="all">{t('Все открытые счета')}</option>
              {open.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.number}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Файл (PDF или изображение до 1 МБ, необязательно)')}
            <input name="file" type="file" accept=".pdf,image/*" />
          </label>
          <div className="rc-action-buttons">
            <button className="button button-dark" disabled={busy}>
              {busy ? t('Сохраняем…') : t('Добавить документ')}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

type Entry = {
  id: string;
  created_at: string;
  title: string;
  body: string;
  amount: number | null;
};

/** Everything said and done with this debtor, across all its invoices, newest first. */
export function ConversationPanel({
  debtor,
  notify,
  onWrite,
  onReply,
}: {
  debtor: DebtorDetail;
  notify: Notify;
  onWrite: (invoiceId: string) => void;
  onReply: (invoiceId: string) => void;
}) {
  const [items, setItems] = useState<Entry[] | null>(null);
  const ids = debtor.invoices.map((item) => item.id).join(',');
  useEffect(() => {
    let alive = true;
    if (!ids) {
      setItems([]);
      return;
    }
    void Promise.all(
      ids
        .split(',')
        .map((id) =>
          api<{ items: Entry[] }>(`/workflow/invoices/${encodeURIComponent(id)}/timeline`)
        )
    )
      .then((pages) => {
        if (!alive) return;
        const seen = new Map(pages.flatMap((page) => page.items).map((item) => [item.id, item]));
        setItems([...seen.values()].sort((a, b) => b.created_at.localeCompare(a.created_at)));
      })
      .catch((error) => notify(error.message, true));
    return () => {
      alive = false;
    };
  }, [ids, notify]);
  const first = debtor.invoices.find((item) => item.balance > 0) ?? debtor.invoices[0];
  return (
    <section className="rc-card">
      <h2>{t('Переписка и события')}</h2>
      {first && (
        <div className="rc-action-list">
          <button className="button button-outline" onClick={() => onWrite(first.id)}>
            {t('Написать должнику')}
          </button>
          <button className="button button-outline" onClick={() => onReply(first.id)}>
            {t('Добавить ответ должника')}
          </button>
        </div>
      )}
      <ul className="rc-log">
        {items === null && <li className="rc-muted">{t('Загружаем…')}</li>}
        {items?.length === 0 && <li className="rc-muted">{t('Писем и событий пока нет.')}</li>}
        {items?.map((item) => (
          <li key={item.id}>
            <strong>{t(item.title)}</strong>
            <span>
              {dateText(item.created_at)}
              {item.amount != null && ` · ${money(item.amount)}`}
            </span>
            {item.body && <small>{item.body}</small>}
          </li>
        ))}
      </ul>
    </section>
  );
}
