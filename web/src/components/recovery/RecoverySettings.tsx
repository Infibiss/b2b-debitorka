import { useEffect, useState, type FormEvent } from 'react';
import { api, del, money, post, put, toKopeks } from '../../api';
import { t } from '../../i18n';
import type { FinancingRequest, Meta, Notify } from './types';
import { ReportSchedules } from './ReportSchedules';

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
  month_days: number[];
  claim_tiers: { min_amount: number; kind: 'claim_soft' | 'claim' | 'claim_final' }[];
  auto_to_court: boolean;
  court_min_amount: number;
  auto_enforcement: boolean;
  auto_archive_paid: boolean;
};
const tierNames = {
  claim_soft: t('Мягкое уведомление'),
  claim: t('Претензия'),
  claim_final: t('Последняя претензия'),
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
      <h3>{t('Тексты по сумме долга')}</h3>
      <p className="rc-muted">
        {t('Чем больше долг, тем строже письмо. Без правил уходит обычная претензия.')}
      </p>
      {(['claim_soft', 'claim', 'claim_final'] as const).map((kind) => {
        const tier = form.claim_tiers.find((item) => item.kind === kind);
        const others = form.claim_tiers.filter((item) => item.kind !== kind);
        return (
          <div className="rc-tier" key={kind}>
            <label className="rc-check">
              <input
                type="checkbox"
                checked={Boolean(tier)}
                onChange={(e) =>
                  setForm({
                    ...form,
                    claim_tiers: e.target.checked ? [...others, { kind, min_amount: 0 }] : others,
                  })
                }
              />
              {tierNames[kind]}
            </label>
            {tier && (
              <label>
                {t('от, ₽')}
                <input
                  value={tier.min_amount / 100}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      claim_tiers: [
                        ...others,
                        { kind, min_amount: toKopeks(e.target.value || '0') },
                      ],
                    })
                  }
                />
              </label>
            )}
          </div>
        );
      })}
      <h3>{t('Суд и исполнение')}</h3>
      <label className="rc-check">
        <input
          type="checkbox"
          checked={form.auto_to_court}
          onChange={(e) => setForm({ ...form, auto_to_court: e.target.checked })}
        />
        {t(
          'Передавать в суд автоматически, когда истёк срок ответа на претензию и документы готовы'
        )}
      </label>
      {form.auto_to_court && (
        <div className="rc-grid">
          <label>
            {t('Только для долгов от, ₽')}
            <input
              value={form.court_min_amount / 100}
              onChange={(e) =>
                setForm({ ...form, court_min_amount: toKopeks(e.target.value || '0') })
              }
            />
          </label>
        </div>
      )}
      <label className="rc-check">
        <input
          type="checkbox"
          checked={form.auto_enforcement}
          onChange={(e) => setForm({ ...form, auto_enforcement: e.target.checked })}
        />
        {t(
          'Переводить в исполнение, когда решение вступило в силу или истёк срок возражений на приказ'
        )}
      </label>
      <label className="rc-check">
        <input
          type="checkbox"
          checked={form.auto_archive_paid}
          onChange={(e) => setForm({ ...form, auto_archive_paid: e.target.checked })}
        />
        {t('Убирать оплаченных должников в архив')}
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
      <label>
        {t('Только в эти числа месяца (через запятую, пусто — каждый день)')}
        <input
          value={form.month_days.join(', ')}
          onChange={(e) =>
            setForm({
              ...form,
              month_days: e.target.value
                .split(',')
                .map((part) => Number(part.trim()))
                .filter((day) => day >= 1 && day <= 31),
            })
          }
        />
      </label>
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
type CustomTemplate = {
  id: string;
  title: string;
  stage: string;
  heading: string;
  address: string;
  body: string;
};
const stageTitles: Record<string, string> = {
  pretrial: t('Досудебная работа'),
  court: t('Суд'),
  enforcement: t('Исполнение'),
};
const blankCustom = { title: '', stage: 'pretrial', heading: '', address: '', body: '' };

function CustomTemplates({ notify }: { notify: Notify }) {
  const [items, setItems] = useState<CustomTemplate[]>([]);
  const [draft, setDraft] = useState<typeof blankCustom | null>(null);
  const load = () =>
    api<{ items: CustomTemplate[] }>('/recovery/custom-templates')
      .then((result) => setItems(result.items))
      .catch((error) => notify(error.message, true));
  useEffect(() => {
    void load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  function submit(event: FormEvent) {
    event.preventDefault();
    post('/recovery/custom-templates', draft)
      .then(() => {
        setDraft(null);
        notify(t('Шаблон сохранён'));
        return load();
      })
      .catch((error) => notify(error.message, true));
  }
  return (
    <section className="rc-card">
      <div className="rc-card-head">
        <h2>{t('Мои документы')}</h2>
        {!draft && (
          <button className="button button-outline" onClick={() => setDraft(blankCustom)}>
            {t('Новый документ')}
          </button>
        )}
      </div>
      {items.length === 0 && !draft && (
        <p className="rc-muted">
          {t('Свои документы появятся в карточке должника на выбранном этапе.')}
        </p>
      )}
      <ul className="rc-documents">
        {items.map((row) => (
          <li key={row.id}>
            <span>
              {row.title} · {stageTitles[row.stage]}
            </span>
            <button
              className="wf-text-button"
              onClick={() =>
                void del(`/recovery/custom-templates/${row.id}`)
                  .then(load)
                  .catch((error) => notify(error.message, true))
              }
            >
              {t('Удалить')}
            </button>
          </li>
        ))}
      </ul>
      {draft && (
        <form className="rc-details" onSubmit={submit}>
          <label>
            {t('Название')}
            <input
              required
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </label>
          <label>
            {t('Этап')}
            <select
              value={draft.stage}
              onChange={(e) => setDraft({ ...draft, stage: e.target.value })}
            >
              {Object.entries(stageTitles).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="rc-span">
            {t('Заголовок документа')}
            <input
              required
              value={draft.heading}
              onChange={(e) => setDraft({ ...draft, heading: e.target.value })}
            />
          </label>
          <label className="rc-span">
            {t('Кому и от кого')}
            <textarea
              rows={3}
              value={draft.address}
              onChange={(e) => setDraft({ ...draft, address: e.target.value })}
            />
          </label>
          <label className="rc-span">
            {t('Текст')}
            <textarea
              required
              rows={10}
              value={draft.body}
              onChange={(e) => setDraft({ ...draft, body: e.target.value })}
            />
          </label>
          <div className="rc-action-buttons rc-span">
            <button className="button button-dark">{t('Сохранить')}</button>
            <button type="button" className="button button-outline" onClick={() => setDraft(null)}>
              {t('Отмена')}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

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
      <CustomTemplates notify={notify} />
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

function ReportBuilder({ notify }: { notify: Notify }) {
  const [options, setOptions] = useState<{ key: string; label: string }[]>([]);
  const [columns, setColumns] = useState(['name', 'inn', 'stage', 'status', 'balance', 'days']);
  const [stage, setStage] = useState('');
  const [minDays, setMinDays] = useState('0');
  useEffect(() => {
    api<{ items: { key: string; label: string }[] }>('/recovery/report/columns')
      .then((result) => setOptions(result.items))
      .catch((error) => notify(error.message, true));
  }, [notify]);
  const query = new URLSearchParams({
    columns: columns.join(','),
    stage,
    min_days: minDays || '0',
  });
  return (
    <section className="rc-card">
      <h2>{t('Свой отчёт')}</h2>
      <div className="rc-grid">
        <label>
          {t('Этап')}
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="">{t('Все этапы')}</option>
            {Object.entries(stageTitles).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('Просрочка от, дней')}
          <input value={minDays} inputMode="numeric" onChange={(e) => setMinDays(e.target.value)} />
        </label>
      </div>
      <div className="rc-report-columns">
        {options.map((option) => (
          <label key={option.key} className="rc-check">
            <input
              type="checkbox"
              checked={columns.includes(option.key)}
              onChange={(e) =>
                setColumns(
                  e.target.checked
                    ? [...columns, option.key]
                    : columns.filter((key) => key !== option.key)
                )
              }
            />
            {t(option.label)}
          </label>
        ))}
      </div>
      <div className="rc-action-buttons">
        <a className="button button-dark" href={`/api/recovery/report/build.csv?${query}`}>
          {t('Скачать отчёт')}
        </a>
        <a className="button button-outline" href="/api/recovery/report/aging.csv">
          {t('Долг по срокам')}
        </a>
      </div>
    </section>
  );
}

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
        </div>
        <a className="button button-outline" href="/api/recovery/report.csv">
          {t('Скачать CSV')}
        </a>
      </header>
      <ReportBuilder notify={notify} />
      <ReportSchedules notify={notify} />
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
