import { useEffect, useState, type FormEvent } from 'react';
import { api, del, money, post, put, toKopeks } from '../../api';
import { t } from '../../i18n';
import type { FinancingRequest, Meta, Notify } from './types';

const orgFields: [string, string][] = [
  ['full_name', t('Полное наименование')],
  ['inn', t('ИНН')],
  ['ogrn', t('ОГРН или ОГРНИП')],
  ['legal_address', t('Юридический адрес')],
  ['signatory', t('Кто подписывает: должность и ФИО')],
  ['poa_number', t('Номер доверенности представителя')],
];

export function OrganizationForm({ notify, onSaved }: { notify: Notify; onSaved: () => void }) {
  const [form, setForm] = useState<Record<string, string> | null>(null);
  useEffect(() => {
    api<Record<string, string>>('/recovery/organization')
      .then(setForm)
      .catch((error) => notify(error.message, true));
  }, [notify]);
  if (!form) return <div className="rc-empty">{t('Загружаем…')}</div>;
  function submit(event: FormEvent) {
    event.preventDefault();
    const { poa_valid_until, ...rest } = form!;
    put('/recovery/organization', { ...rest, ...(poa_valid_until ? { poa_valid_until } : {}) })
      .then(() => {
        notify(t('Реквизиты сохранены'));
        onSaved();
      })
      .catch((error) => notify(error.message, true));
  }
  return (
    <form className="rc-details rc-card" onSubmit={submit}>
      <h2>{t('Реквизиты компании')}</h2>
      {orgFields.map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            value={form[key] ?? ''}
            onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          />
        </label>
      ))}
      <label className="rc-span">
        {t('Банковские реквизиты')}
        <textarea
          rows={3}
          value={form.bank_details ?? ''}
          onChange={(e) => setForm({ ...form, bank_details: e.target.value })}
        />
      </label>
      <button className="button button-dark">{t('Сохранить')}</button>
    </form>
  );
}

type Channel = { enabled: boolean; min_amount: number; repeat_days: number };
type Automation = {
  enabled: boolean;
  min_amount: number;
  max_amount: number;
  start_after_overdue_days: number;
  claim_after_overdue_days: number;
  auto_prepare_claim: boolean;
  payment_control_days: number;
  pretrial_days: number;
  channels: Record<'email' | 'voice' | 'sms' | 'post', Channel>;
  weekdays: number[];
  start_hour: number;
  end_hour: number;
  mail_connected?: boolean;
};
const channelNames: Record<keyof Automation['channels'], string> = {
  email: t('Электронная почта'),
  voice: t('Голосовой звонок'),
  sms: t('SMS'),
  post: t('Заказное письмо'),
};
const days = [t('Пн'), t('Вт'), t('Ср'), t('Чт'), t('Пт'), t('Сб'), t('Вс')];

export function AutomationForm({ notify, onSaved }: { notify: Notify; onSaved: () => void }) {
  const [form, setForm] = useState<Automation | null>(null);
  useEffect(() => {
    api<Automation>('/recovery/automation')
      .then(setForm)
      .catch((error) => notify(error.message, true));
  }, [notify]);
  if (!form) return <div className="rc-empty">{t('Загружаем…')}</div>;
  const number = (key: keyof Automation) => (
    <input
      type="number"
      min={0}
      value={form[key] as number}
      onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
    />
  );
  function submit(event: FormEvent) {
    event.preventDefault();
    const { mail_connected: _ignored, ...body } = form!;
    put<Automation>('/recovery/automation', body)
      .then((saved) => {
        setForm(saved);
        notify(t('Правила сохранены'));
        onSaved();
      })
      .catch((error) => notify(error.message, true));
  }
  return (
    <form className="rc-settings rc-card" onSubmit={submit}>
      <h2>{t('Правила автоматизации')}</h2>
      <p className="rc-muted">
        {t(
          'Система работает только в этих рамках. Передача в суд всегда остаётся решением руководителя.'
        )}
      </p>
      <label className="rc-check">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
        />
        {t('Включить автоматизацию')}
      </label>
      {!form.mail_connected && (
        <p className="rc-note">
          {t('Почта не подключена: письма не будут уходить, пока вы её не подключите.')}
        </p>
      )}
      <div className="rc-grid">
        <label>
          {t('Работать с долгами от, ₽')}
          <input
            value={form.min_amount / 100}
            onChange={(e) => setForm({ ...form, min_amount: toKopeks(e.target.value || '0') })}
          />
        </label>
        <label>
          {t('до, ₽')}
          <input
            value={form.max_amount / 100}
            onChange={(e) => setForm({ ...form, max_amount: toKopeks(e.target.value || '0') })}
          />
        </label>
        <label>
          {t('Начинать напоминания после просрочки, дней')}
          {number('start_after_overdue_days')}
        </label>
        <label>
          {t('Готовить претензию после просрочки, дней')}
          {number('claim_after_overdue_days')}
        </label>
        <label>
          {t('Контроль обещания: дней после даты')}
          {number('payment_control_days')}
        </label>
        <label>
          {t('Срок ответа на претензию, дней')}
          {number('pretrial_days')}
        </label>
      </div>
      <label className="rc-check">
        <input
          type="checkbox"
          checked={form.auto_prepare_claim}
          onChange={(e) => setForm({ ...form, auto_prepare_claim: e.target.checked })}
        />
        {t('Готовить претензии автоматически')}
      </label>
      <h3>{t('Каналы')}</h3>
      <table className="rc-table">
        <thead>
          <tr>
            <th>{t('Канал')}</th>
            <th>{t('Включён')}</th>
            <th>{t('От суммы, ₽')}</th>
            <th>{t('Повтор, дней')}</th>
          </tr>
        </thead>
        <tbody>
          {(Object.keys(channelNames) as (keyof Automation['channels'])[]).map((key) => {
            const row = form.channels[key];
            const set = (patch: Partial<Channel>) =>
              setForm({ ...form, channels: { ...form.channels, [key]: { ...row, ...patch } } });
            const live = key === 'email';
            return (
              <tr key={key}>
                <td>
                  {channelNames[key]}
                  {!live && <small>{t('Подключается по заявке')}</small>}
                </td>
                <td>
                  <input
                    type="checkbox"
                    disabled={!live}
                    aria-label={channelNames[key]}
                    checked={row.enabled}
                    onChange={(e) => set({ enabled: e.target.checked })}
                  />
                </td>
                <td>
                  <input
                    aria-label={t('От суммы, ₽')}
                    value={row.min_amount / 100}
                    onChange={(e) => set({ min_amount: toKopeks(e.target.value || '0') })}
                  />
                </td>
                <td>
                  <input
                    aria-label={t('Повтор, дней')}
                    type="number"
                    min={1}
                    max={90}
                    value={row.repeat_days}
                    onChange={(e) => set({ repeat_days: Number(e.target.value) })}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <h3>{t('Расписание')}</h3>
      <div className="rc-weekdays">
        {days.map((label, index) => (
          <label key={label} className="rc-check">
            <input
              type="checkbox"
              checked={form.weekdays.includes(index)}
              onChange={(e) =>
                setForm({
                  ...form,
                  weekdays: e.target.checked
                    ? [...form.weekdays, index].sort()
                    : form.weekdays.filter((day) => day !== index),
                })
              }
            />
            {label}
          </label>
        ))}
      </div>
      <div className="rc-grid">
        <label>
          {t('С часа')}
          {number('start_hour')}
        </label>
        <label>
          {t('До часа')}
          {number('end_hour')}
        </label>
      </div>
      <button className="button button-dark">{t('Утвердить правила')}</button>
    </form>
  );
}

type Template = { kind: string; title: string; stage: string; body: string; default_body: string };

export function TemplatesDesk({ meta, notify }: { meta: Meta; notify: Notify }) {
  const [items, setItems] = useState<Template[]>([]);
  const [kind, setKind] = useState('claim');
  const [body, setBody] = useState('');
  const load = () =>
    api<{ items: Template[] }>('/recovery/templates')
      .then((result) => {
        setItems(result.items);
        setBody(result.items.find((row) => row.kind === kind)?.body ?? '');
      })
      .catch((error) => notify(error.message, true));
  useEffect(() => {
    void load();
  }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps
  const current = items.find((row) => row.kind === kind);
  return (
    <div className="rc-page">
      <header className="rc-head">
        <div>
          <h1>{t('Шаблоны документов')}</h1>
          <p>{t('Один текст фактов для претензии и суда. Меняются только шапка и требования.')}</p>
        </div>
      </header>
      <div className="rc-template">
        <nav aria-label={t('Шаблоны')}>
          {items.map((row) => (
            <button
              key={row.kind}
              className={row.kind === kind ? 'active' : ''}
              onClick={() => setKind(row.kind)}
            >
              {t(row.title)}
            </button>
          ))}
        </nav>
        <section className="rc-card">
          <textarea
            rows={18}
            value={body}
            aria-label={t('Текст шаблона')}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className="rc-action-buttons">
            <button
              className="button button-dark"
              onClick={() =>
                put(`/recovery/templates/${kind}`, { body })
                  .then(() => notify(t('Шаблон сохранён')))
                  .catch((error) => notify(error.message, true))
              }
            >
              {t('Сохранить')}
            </button>
            {current && current.body !== current.default_body && (
              <button
                className="button button-outline"
                onClick={() => void del(`/recovery/templates/${kind}`).then(load)}
              >
                {t('Вернуть исходный')}
              </button>
            )}
          </div>
          <details>
            <summary>{t('Переменные')}</summary>
            <ul className="rc-vars">
              {Object.entries(meta.variables).map(([key, label]) => (
                <li key={key}>
                  <code>{`{{${key}}}`}</code> {t(label)}
                </li>
              ))}
            </ul>
          </details>
        </section>
      </div>
    </div>
  );
}

export function FinancingDesk({ notify, isManager }: { notify: Notify; isManager: boolean }) {
  const [items, setItems] = useState<FinancingRequest[] | null>(null);
  const load = () =>
    api<{ items: FinancingRequest[] }>('/financing/requests')
      .then((result) => setItems(result.items))
      .catch((error) => notify(error.message, true));
  useEffect(() => {
    void load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="rc-page">
      <header className="rc-head">
        <div>
          <h1>{t('Финансирование')}</h1>
          <p>
            {t('Деньги сейчас, пока должник не заплатил. Партнёр получает возврат из поступлений.')}
          </p>
        </div>
      </header>
      {items?.length === 0 && (
        <div className="rc-empty">
          {t('Заявок пока нет. Откройте карточку должника и выберите подходящий вариант.')}
        </div>
      )}
      {!!items?.length && (
        <div className="rc-table-wrap">
          <table className="rc-table">
            <thead>
              <tr>
                <th>{t('Должник')}</th>
                <th>{t('Продукт')}</th>
                <th className="rc-num">{t('Сумма')}</th>
                <th>{t('Статус')}</th>
                <th className="rc-num">{t('Осталось вернуть')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td>{row.debtor_name}</td>
                  <td>{t(row.product_name)}</td>
                  <td className="rc-num">{money(row.amount, true)}</td>
                  <td>{t(row.status_label)}</td>
                  <td className="rc-num">
                    {row.remaining_amount == null ? '—' : money(row.remaining_amount, true)}
                  </td>
                  <td>
                    {isManager && ['requested', 'in_review', 'offer'].includes(row.status) && (
                      <button
                        className="wf-text-button"
                        onClick={() =>
                          post(`/financing/requests/${row.id}/withdraw`)
                            .then(load)
                            .catch((error) => notify(error.message, true))
                        }
                      >
                        {t('Отозвать')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

type Report = {
  recovered_amount: number;
  duties_paid_amount: number;
  stages: { stage: string; count: number; amount: number }[];
  by_status: { status: string; label: string; count: number; amount: number }[];
};

export function ReportsDesk({ notify }: { notify: Notify }) {
  const [report, setReport] = useState<Report | null>(null);
  useEffect(() => {
    api<Report>('/recovery/report')
      .then(setReport)
      .catch((error) => notify(error.message, true));
  }, [notify]);
  if (!report) return <div className="rc-empty">{t('Загружаем…')}</div>;
  return (
    <div className="rc-page">
      <header className="rc-head">
        <div>
          <h1>{t('Отчёты')}</h1>
          <p>{t('Сколько денег вернулось и где долги сейчас.')}</p>
        </div>
        <a className="button button-outline" href="/api/recovery/report.csv">
          {t('Скачать CSV')}
        </a>
      </header>
      <section className="rc-kpis">
        <div>
          <span>{t('Получено оплат')}</span>
          <strong>{money(report.recovered_amount, true)}</strong>
        </div>
        <div>
          <span>{t('Оплачено госпошлин')}</span>
          <strong>{money(report.duties_paid_amount, true)}</strong>
        </div>
      </section>
      <div className="rc-table-wrap">
        <table className="rc-table">
          <thead>
            <tr>
              <th>{t('Статус')}</th>
              <th className="rc-num">{t('Должников')}</th>
              <th className="rc-num">{t('Сумма')}</th>
            </tr>
          </thead>
          <tbody>
            {report.by_status.map((row) => (
              <tr key={row.status}>
                <td>{t(row.label)}</td>
                <td className="rc-num">{row.count}</td>
                <td className="rc-num">{money(row.amount, true)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
