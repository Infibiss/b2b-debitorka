import { useCallback, useEffect, useState } from 'react';
import { FileUp } from 'lucide-react';
import { api, dateText, del, money, post } from '../../api';
import { t } from '../../i18n';
import type { Debtor, Notify } from './types';

type Item = {
  id: string;
  filename: string;
  kind: string;
  kind_label: string;
  debtor_id: string | null;
  action: string | null;
  source: 'text' | 'ocr';
  fields: {
    case_number: string;
    act_on: string;
    amount: number | null;
    reference: string;
    court: string;
    purpose: string;
    inns: string[];
  };
};
const documentActions = [
  'order_issued',
  'order_cancelled',
  'accepted',
  'without_motion',
  'court_returned',
  'decision_won',
  'decision_lost',
  'writ_received',
  'duty_paid',
];

const readBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(t('Не удалось прочитать файл')));
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.readAsDataURL(file);
  });

function Card({
  item,
  debtors,
  labels,
  notify,
  onDone,
}: {
  item: Item;
  debtors: Debtor[];
  labels: Record<string, string>;
  notify: Notify;
  onDone: () => void;
}) {
  const [debtor, setDebtor] = useState(item.debtor_id ?? '');
  const [action, setAction] = useState(item.action ?? '');
  const [caseNumber, setCaseNumber] = useState(item.fields.case_number);
  const [actOn, setActOn] = useState(item.fields.act_on);
  const [reference, setReference] = useState(item.fields.reference);
  function apply() {
    post(`/recovery/recognitions/${item.id}/apply`, {
      debtor_id: debtor,
      action,
      case_number: caseNumber,
      reference,
      ...(actOn ? { act_on: actOn } : {}),
    })
      .then(() => {
        notify(t('Готово'));
        onDone();
      })
      .catch((error) => notify(error.message, true));
  }
  return (
    <article className="rc-card rc-recognition">
      <div className="rc-card-head">
        <h2>{t(item.kind_label)}</h2>
        <a className="wf-text-button" href={`/api/recovery/recognitions/${item.id}/file`}>
          {item.filename}
        </a>
      </div>
      <dl className="rc-facts">
        {item.fields.court && (
          <div>
            <dt>{t('Суд')}</dt>
            <dd>{item.fields.court}</dd>
          </div>
        )}
        {item.fields.amount != null && (
          <div>
            <dt>{t('Сумма')}</dt>
            <dd>{money(item.fields.amount)}</dd>
          </div>
        )}
        {item.fields.act_on && (
          <div>
            <dt>{t('Дата документа')}</dt>
            <dd>{dateText(item.fields.act_on)}</dd>
          </div>
        )}
        {item.fields.purpose && (
          <div>
            <dt>{t('Назначение')}</dt>
            <dd>{item.fields.purpose}</dd>
          </div>
        )}
      </dl>
      <div className="rc-details">
        <label>
          {t('Должник')}
          <select value={debtor} onChange={(e) => setDebtor(e.target.value)}>
            <option value="">{t('Выберите должника')}</option>
            {debtors.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('Что сделать')}
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">{t('Только приложить к карточке')}</option>
            {documentActions.map((key) => (
              <option key={key} value={key}>
                {t(labels[key] ?? key)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('Номер дела')}
          <input value={caseNumber} onChange={(e) => setCaseNumber(e.target.value)} />
        </label>
        <label>
          {t('Дата документа')}
          <input type="date" value={actOn} onChange={(e) => setActOn(e.target.value)} />
        </label>
        <label>
          {t('Номер документа')}
          <input value={reference} onChange={(e) => setReference(e.target.value)} />
        </label>
      </div>
      <div className="rc-action-buttons">
        <button className="button button-dark" disabled={!debtor} onClick={apply}>
          {t('Подтвердить')}
        </button>
        <button
          className="button button-outline"
          onClick={() =>
            void del(`/recovery/recognitions/${item.id}`)
              .then(onDone)
              .catch((error) => notify(error.message, true))
          }
        >
          {t('Удалить')}
        </button>
      </div>
    </article>
  );
}

export function RecognizeDesk({ notify, onChanged }: { notify: Notify; onChanged: () => void }) {
  const [items, setItems] = useState<Item[] | null>(null);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [debtors, setDebtors] = useState<Debtor[]>([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const [list, people] = await Promise.all([
      api<{ items: Item[]; action_labels: Record<string, string> }>('/recovery/recognitions'),
      api<{ items: Debtor[] }>('/recovery/debtors'),
    ]);
    setItems(list.items);
    setLabels(list.action_labels);
    setDebtors(people.items.filter((row) => !row.archived));
  }, []);
  useEffect(() => {
    load().catch((error) => notify(error.message, true));
  }, [load, notify]);
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    let done = 0;
    for (const file of Array.from(files)) {
      try {
        if (file.size > 8_000_000) throw new Error(t('PDF больше 8 МБ'));
        await post('/recovery/recognitions', {
          filename: file.name,
          content: await readBase64(file),
        });
        done += 1;
      } catch (error) {
        notify(`${file.name}: ${(error as Error).message}`, true);
      }
    }
    setBusy(false);
    if (done) notify(t('Распознано: {0}', [done]));
    await load().catch((error) => notify(error.message, true));
  }
  if (!items) return <div className="rc-empty">{t('Загружаем…')}</div>;
  return (
    <div className="rc-page">
      <header className="rc-head">
        <h1>{t('Распознавание')}</h1>
        <label className={`button button-dark rc-upload ${busy ? 'is-busy' : ''}`}>
          <FileUp size={15} aria-hidden="true" />
          {busy ? t('Читаем…') : t('Загрузить PDF')}
          <input
            type="file"
            accept="application/pdf"
            multiple
            disabled={busy}
            aria-label={t('Загрузить PDF')}
            onChange={(e) => {
              void upload(e.target.files);
              e.target.value = '';
            }}
          />
        </label>
      </header>
      {items.length === 0 && (
        <div className="rc-empty">
          {t(
            'Загрузите судебные приказы, определения, решения и платёжные поручения. Статус изменится только после вашего подтверждения.'
          )}
        </div>
      )}
      {items.map((item) => (
        <Card
          key={item.id}
          item={item}
          debtors={debtors}
          labels={labels}
          notify={notify}
          onDone={() => {
            onChanged();
            void load().catch((error) => notify(error.message, true));
          }}
        />
      ))}
    </div>
  );
}
