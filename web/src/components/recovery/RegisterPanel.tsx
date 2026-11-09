import { useState, type FormEvent } from 'react';
import { ExternalLink } from 'lucide-react';
import { dateText, del, money, post, today, toKopeks } from '../../api';
import { t } from '../../i18n';
import type { DebtorDetail, Notify, RegisterEntry } from './types';

type Kind = RegisterEntry['kind'];
const sections: {
  kind: Kind;
  title: string;
  add: string;
  titleLabel: string;
  referenceLabel: string;
  amount?: string;
}[] = [
  {
    kind: 'court_event',
    title: t('Судебное дело'),
    add: t('Добавить событие'),
    titleLabel: t('Событие: заседание, определение, решение'),
    referenceLabel: t('Суд или судья'),
  },
  {
    kind: 'enforcement_case',
    title: t('Исполнительные производства'),
    add: t('Добавить производство'),
    titleLabel: t('Отделение приставов'),
    referenceLabel: t('Номер производства'),
    amount: t('Сумма, ₽'),
  },
  {
    kind: 'fns_request',
    title: t('Запросы в ФНС'),
    add: t('Добавить запрос'),
    titleLabel: t('Инспекция'),
    referenceLabel: t('Номер запроса'),
  },
  {
    kind: 'bank_account',
    title: t('Счета должника'),
    add: t('Добавить счёт'),
    titleLabel: t('Банк'),
    referenceLabel: t('Номер счёта'),
    amount: t('Остаток, ₽'),
  },
  {
    kind: 'measure',
    title: t('Другие меры'),
    add: t('Добавить меру'),
    titleLabel: t('Что сделано'),
    referenceLabel: t('Номер или ссылка'),
  },
];

export function RegisterPanel({
  debtor,
  notify,
  onSaved,
}: {
  debtor: DebtorDetail;
  notify: Notify;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState<Kind | null>(null);
  const [form, setForm] = useState({
    on_date: today(),
    title: '',
    reference: '',
    amount: '',
    status: '',
    note: '',
  });
  function submit(event: FormEvent, kind: Kind) {
    event.preventDefault();
    const { amount, ...rest } = form;
    post(`/recovery/debtors/${debtor.id}/register`, {
      kind,
      ...rest,
      ...(amount ? { amount: toKopeks(amount) } : {}),
    })
      .then(() => {
        setOpen(null);
        setForm({ on_date: today(), title: '', reference: '', amount: '', status: '', note: '' });
        onSaved();
      })
      .catch((error) => notify(error.message, true));
  }
  return (
    <div className="rc-register">
      {debtor.case_number && (
        <a
          className="button button-outline rc-kad"
          href="https://kad.arbitr.ru/"
          target="_blank"
          rel="noreferrer"
        >
          {t('Открыть картотеку: дело {0}', [debtor.case_number])}
          <ExternalLink size={14} aria-hidden="true" />
        </a>
      )}
      {sections.map((section) => {
        const rows = debtor.register.filter((row) => row.kind === section.kind);
        return (
          <section className="rc-card" key={section.kind}>
            <div className="rc-card-head">
              <h2>{section.title}</h2>
              {open !== section.kind && (
                <button className="wf-text-button" onClick={() => setOpen(section.kind)}>
                  {section.add}
                </button>
              )}
            </div>
            <ul className="rc-documents">
              {rows.map((row) => (
                <li key={row.id}>
                  <span>
                    {dateText(row.on_date)} · <strong>{row.title}</strong>
                    {row.reference ? ` · ${row.reference}` : ''}
                    {row.amount != null ? ` · ${money(row.amount, true)}` : ''}
                    {row.status ? ` · ${row.status}` : ''}
                    {row.note && <small>{row.note}</small>}
                  </span>
                  <button
                    className="wf-text-button"
                    onClick={() =>
                      void del(`/recovery/register/${row.id}`)
                        .then(onSaved)
                        .catch((error) => notify(error.message, true))
                    }
                  >
                    {t('Удалить')}
                  </button>
                </li>
              ))}
            </ul>
            {open === section.kind && (
              <form className="rc-details" onSubmit={(event) => submit(event, section.kind)}>
                <label>
                  {t('Дата')}
                  <input
                    type="date"
                    required
                    value={form.on_date}
                    onChange={(e) => setForm({ ...form, on_date: e.target.value })}
                  />
                </label>
                <label>
                  {section.titleLabel}
                  <input
                    required
                    value={form.title}
                    onChange={(e) => setForm({ ...form, title: e.target.value })}
                  />
                </label>
                <label>
                  {section.referenceLabel}
                  <input
                    value={form.reference}
                    onChange={(e) => setForm({ ...form, reference: e.target.value })}
                  />
                </label>
                {section.amount && (
                  <label>
                    {section.amount}
                    <input
                      inputMode="decimal"
                      value={form.amount}
                      onChange={(e) => setForm({ ...form, amount: e.target.value })}
                    />
                  </label>
                )}
                <label className="rc-span">
                  {t('Комментарий')}
                  <input
                    value={form.note}
                    onChange={(e) => setForm({ ...form, note: e.target.value })}
                  />
                </label>
                <div className="rc-action-buttons rc-span">
                  <button className="button button-dark">{t('Сохранить')}</button>
                  <button
                    type="button"
                    className="button button-outline"
                    onClick={() => setOpen(null)}
                  >
                    {t('Отмена')}
                  </button>
                </div>
              </form>
            )}
          </section>
        );
      })}
    </div>
  );
}
