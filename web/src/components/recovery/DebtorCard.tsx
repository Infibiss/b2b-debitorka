import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, Check, Download } from 'lucide-react';
import { api, dateText, money, patch, post, today, toKopeks } from '../../api';
import { t } from '../../i18n';
import { ConversationPanel, EvidencePanel } from './DebtorExtras';
import { RegisterPanel } from './RegisterPanel';
import { stageNames } from './RecoveryHome';
import type { DebtorDetail, FinancingOffer, Meta, Notify } from './types';

type Tab =
  | 'overview'
  | 'invoices'
  | 'documents'
  | 'conversation'
  | 'cases'
  | 'financing'
  | 'history';
const tabs: [Tab, string][] = [
  ['overview', t('Обзор')],
  ['invoices', t('Счета')],
  ['documents', t('Документы')],
  ['conversation', t('Переписка')],
  ['cases', t('Суд и взыскание')],
  ['financing', t('Финансирование')],
  ['history', t('История')],
];
const fieldLabels: Record<string, string> = {
  note: t('Комментарий'),
  reference: t('Номер или ссылка на подтверждение'),
  case_number: t('Номер дела'),
  promise_date: t('Дата обещанной оплаты'),
  sent_on: t('Дата отправки'),
  filed_on: t('Дата подачи'),
  act_on: t('Дата документа'),
  route: t('Маршрут'),
};
const routeNames: Record<string, string> = {
  court_order: t('Судебный приказ'),
  statement_of_claim: t('Исковое заявление'),
};
const dateFields = new Set(['promise_date', 'sent_on', 'filed_on', 'act_on']);

function ActionForm({
  action,
  meta,
  defaultRoute,
  onCancel,
  onSubmit,
}: {
  action: string;
  meta: Meta;
  defaultRoute: string;
  onCancel: () => void;
  onSubmit: (values: Record<string, string>) => Promise<void>;
}) {
  const required = meta.actions[action].required;
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      required.map((key) => [
        key,
        key === 'route' ? defaultRoute : dateFields.has(key) ? today() : '',
      ])
    )
  );
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await onSubmit(values);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="rc-action-form" onSubmit={(e) => void submit(e)}>
      <h3>{t(meta.action_labels[action])}</h3>
      {required.map((key) => (
        <label key={key}>
          {fieldLabels[key] ?? key}
          {key === 'route' ? (
            <select
              value={values[key]}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
            >
              {Object.entries(routeNames).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          ) : (
            <input
              required
              type={dateFields.has(key) ? 'date' : 'text'}
              value={values[key]}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
            />
          )}
        </label>
      ))}
      <div className="rc-action-buttons">
        <button className="button button-dark" disabled={busy}>
          {t('Подтвердить')}
        </button>
        <button type="button" className="button button-outline" onClick={onCancel}>
          {t('Отмена')}
        </button>
      </div>
    </form>
  );
}

function DetailsForm({
  debtor,
  notify,
  onSaved,
}: {
  debtor: DebtorDetail;
  notify: Notify;
  onSaved: () => void;
}) {
  const initial = {
    legal_address: '',
    ogrn: '',
    contract: '',
    performance_documents: '',
    court_name: '',
    court_address: '',
    bank_name: '',
    contact_person: '',
    phone: '',
    cedent: '',
    ...debtor.details,
    custom_status: debtor.custom_status,
  };
  const [form, setForm] = useState(initial);
  const rows: [keyof typeof form, string][] = [
    ['legal_address', t('Юридический адрес должника')],
    ['ogrn', t('ОГРН должника')],
    ['contract', t('Договор: номер и дата')],
    ['performance_documents', t('Акты, УПД, накладные')],
    ['court_name', t('Арбитражный суд')],
    ['court_address', t('Адрес суда')],
    ['bank_name', t('Банк должника')],
    ['contact_person', t('Контактное лицо')],
    ['phone', t('Телефон')],
    ['cedent', t('Первоначальный кредитор (при цессии)')],
    ['custom_status', t('Мой статус')],
  ];
  return (
    <form
      className="rc-details"
      onSubmit={(event) => {
        event.preventDefault();
        patch('/recovery/debtors/' + debtor.id, form)
          .then(() => {
            notify(t('Данные сохранены'));
            onSaved();
          })
          .catch((error) => notify(error.message, true));
      }}
    >
      {rows.map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            value={form[key] ?? ''}
            onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          />
        </label>
      ))}
      <button className="button button-outline">{t('Сохранить')}</button>
    </form>
  );
}

function FinancingPanel({
  debtor,
  notify,
  onDone,
}: {
  debtor: DebtorDetail;
  notify: Notify;
  onDone: () => void;
}) {
  const [offer, setOffer] = useState<FinancingOffer | null>(null);
  const [amount, setAmount] = useState('');
  const [consent, setConsent] = useState(false);
  function submit(event: FormEvent) {
    event.preventDefault();
    post(`/financing/debtors/${debtor.id}/requests`, {
      product_id: offer!.id,
      amount: toKopeks(amount),
      consent,
    })
      .then(() => {
        notify(t('Заявка принята'));
        setOffer(null);
        onDone();
      })
      .catch((error) => notify(error.message, true));
  }
  return (
    <div className="rc-financing">
      <p className="rc-muted">
        {t(
          'Не ждите оплаты: получите часть денег сейчас. Решение принимает банк или финансовая компания, Mandato передаёт заявку с вашего согласия.'
        )}
      </p>
      {debtor.financing.has_active_request && (
        <p className="rc-note">{t('По этому должнику уже есть активная заявка.')}</p>
      )}
      <div className="rc-offers">
        {debtor.financing.items.map((item) => (
          <article key={item.id} className={item.eligible ? '' : 'is-off'}>
            <h3>{t(item.name)}</h3>
            <p>{t(item.summary)}</p>
            <dl>
              <div>
                <dt>{t('Предварительно')}</dt>
                <dd>
                  {money(item.amount_from, true)} – {money(item.amount_to, true)}
                </dd>
              </div>
              {item.annual_rate_percent && (
                <div>
                  <dt>{t('Ориентир ставки')}</dt>
                  <dd>{t('от {0}% годовых', [item.annual_rate_percent])}</dd>
                </div>
              )}
            </dl>
            {item.reasons.map((reason) => (
              <small key={reason}>{t(reason)}</small>
            ))}
            {item.eligible && (
              <button
                className="button button-outline"
                onClick={() => {
                  setOffer(item);
                  setAmount(String(Math.round(item.amount_to / 100)));
                  setConsent(false);
                }}
              >
                {t('Подать заявку')}
              </button>
            )}
          </article>
        ))}
      </div>
      {offer && (
        <form className="rc-action-form" onSubmit={submit}>
          <h3>{t(offer.name)}</h3>
          <label>
            {t('Сумма, ₽')}
            <input required value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label className="rc-check">
            <input
              type="checkbox"
              required
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            {t('Согласен передать данные о долге и документы финансовому партнёру')}
          </label>
          <small>
            {t(
              'Условия предварительные и не являются офертой. Окончательные условия определит партнёр.'
            )}
          </small>
          <div className="rc-action-buttons">
            <button className="button button-dark">{t('Отправить заявку')}</button>
            <button type="button" className="button button-outline" onClick={() => setOffer(null)}>
              {t('Отмена')}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export function DebtorCard({
  id,
  meta,
  isManager,
  onBack,
  onChanged,
  onOpenInvoice,
  onReply,
  notify,
}: {
  id: string;
  meta: Meta;
  isManager: boolean;
  onBack: () => void;
  onChanged: () => void;
  onOpenInvoice: (invoiceId: string) => void;
  onReply: (invoiceId: string) => void;
  notify: Notify;
}) {
  const [debtor, setDebtor] = useState<DebtorDetail | null>(null);
  const [tab, setTab] = useState<Tab>('overview');
  const [pending, setPending] = useState<string | null>(null);
  const load = useCallback(
    () =>
      api<DebtorDetail>(`/recovery/debtors/${id}`)
        .then(setDebtor)
        .catch((error) => notify(error.message, true)),
    [id, notify]
  );
  useEffect(() => {
    void load();
  }, [load]);
  if (!debtor) return <div className="rc-empty">{t('Загружаем…')}</div>;
  async function run(action: string, values: Record<string, string> = {}) {
    try {
      const body = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== ''));
      const result = await post<{ reminders_active?: boolean }>(`/recovery/debtors/${id}/actions`, {
        action,
        ...body,
      });
      setPending(null);
      await load();
      onChanged();
      notify(
        action === 'start' && !result.reminders_active
          ? t('Должник в работе. Письма пойдут после подключения почты и утверждения правил.')
          : t('Готово')
      );
    } catch (error) {
      notify((error as Error).message, true);
    }
  }
  const click = (action: string) =>
    meta.actions[action].required.length ? setPending(action) : void run(action);
  const primary = debtor.next_step?.action;
  const secondary = debtor.actions.filter(
    (action) => action !== primary && !['settle', 'write_off', 'withdraw'].includes(action)
  );
  const closing = debtor.actions.filter((action) =>
    ['settle', 'write_off', 'withdraw'].includes(action)
  );
  const canRun = (action: string) => isManager || !meta.actions[action].manager_only;
  const kinds = [
    ...Object.entries(meta.document_kinds).filter(([, kind]) => kind.stage === debtor.stage),
    ...debtor.custom_templates
      .filter((kind) => kind.stage === debtor.stage)
      .map((kind): [string, { title: string }] => [kind.kind, kind]),
  ];
  return (
    <div className="rc-page">
      <button className="wf-text-button rc-back" onClick={onBack}>
        <ArrowLeft size={14} />
        {t('Все должники')}
      </button>
      <header className="rc-head">
        <div>
          <h1>{debtor.name}</h1>
          <p>
            {debtor.inn ? t('ИНН {0}', [debtor.inn]) : t('ИНН не указан')} ·{' '}
            {stageNames[debtor.stage]} · {t(debtor.status_label)}
          </p>
        </div>
        <div className="rc-amount">
          <strong>{money(debtor.balance)}</strong>
          <small>{t('{0} дн. просрочки', [debtor.days_overdue])}</small>
        </div>
      </header>

      {debtor.steps.length > 0 && (
        <ol className="rc-steps">
          {debtor.steps.map((step) => (
            <li key={step.key} className={`rc-step-${step.state}`}>
              <span>{step.state === 'done' && <Check size={12} />}</span>
              {t(step.label)}
            </li>
          ))}
        </ol>
      )}

      {debtor.next_step && (
        <section className="rc-next-card">
          <div>
            <small>{t('Следующий шаг')}</small>
            <p>{t(debtor.next_step.reason)}</p>
          </div>
          {primary &&
            (canRun(primary) ? (
              <button className="button button-dark" onClick={() => click(primary)}>
                {t(meta.action_labels[primary])}
              </button>
            ) : (
              <small>{t('Решение принимает руководитель')}</small>
            ))}
        </section>
      )}
      {debtor.status === 'reminders' && !debtor.mail_connected && (
        <p className="rc-note">
          {t(
            'Почта не подключена, поэтому напоминания этому должнику пока не уходят. Подключить её можно в настройках, вкладка «Почта».'
          )}
        </p>
      )}
      {pending && (
        <ActionForm
          action={pending}
          meta={meta}
          defaultRoute={debtor.route || debtor.recommendation.route}
          onCancel={() => setPending(null)}
          onSubmit={(values) => run(pending, values)}
        />
      )}

      <nav className="rc-tabs" aria-label={t('Разделы карточки')}>
        {tabs.map(([key, label]) => (
          <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </nav>

      {tab === 'overview' && (
        <div className="rc-columns">
          <section className="rc-card">
            <h2>{t('Готовность к суду: {0}%', [debtor.evidence.score])}</h2>
            <ul className="rc-evidence">
              {debtor.evidence.items.map((item) => (
                <li key={item.key} className={item.present ? 'is-done' : ''}>
                  <span className="rc-setup-mark">{item.present && <Check size={14} />}</span>
                  <div>
                    <strong>
                      {t(item.label)}
                      {!item.required && <em> · {t('желательно')}</em>}
                    </strong>
                    {!item.present && <small>{t(item.hint)}</small>}
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <section className="rc-card">
            <h2>{t('Оценка дела')}</h2>
            <dl className="rc-facts">
              <div>
                <dt>{t('Должник')}</dt>
                <dd>{t(debtor.solvency.label)}</dd>
              </div>
              <div>
                <dt>{t('Рекомендуемый маршрут')}</dt>
                <dd>{routeNames[debtor.recommendation.route]}</dd>
              </div>
              {debtor.economics && (
                <>
                  <div>
                    <dt>{t('Госпошлина')}</dt>
                    <dd>{money(debtor.economics.duty_amount, true)}</dd>
                  </div>
                  <div>
                    <dt>{t('Подготовка пакета')}</dt>
                    <dd>{money(debtor.economics.package_amount, true)}</dd>
                  </div>
                </>
              )}
              {debtor.deadlines.map((item) => (
                <div key={item.key}>
                  <dt>{t(item.label)}</dt>
                  <dd>
                    {dateText(item.on)} · {t('{0} дн.', [item.days_left])}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="rc-muted">{t(debtor.recommendation.reason)}</p>
            {debtor.inn && (
              <button
                className="button button-outline"
                onClick={() =>
                  post('/integrations/registry/check', { inn: debtor.inn })
                    .then(() => load())
                    .then(() => notify(t('Проверка выполнена')))
                    .catch((error) => notify(error.message, true))
                }
              >
                {t('Проверить должника')}
              </button>
            )}
            {debtor.solvency.warning && <p className="rc-note">{t(debtor.solvency.warning)}</p>}
            {debtor.economics?.warnings.map((text) => (
              <p className="rc-note" key={text}>
                {t(text)}
              </p>
            ))}
          </section>
          <section className="rc-card rc-span">
            <h2>{t('Данные для документов')}</h2>
            <DetailsForm debtor={debtor} notify={notify} onSaved={() => void load()} />
          </section>
          {(secondary.length > 0 || closing.length > 0) && (
            <section className="rc-card rc-span">
              <h2>{t('Другие действия')}</h2>
              <div className="rc-action-list">
                {[...secondary, ...closing].filter(canRun).map((action) => (
                  <button
                    key={action}
                    className="button button-outline"
                    onClick={() => setPending(action)}
                  >
                    {t(meta.action_labels[action])}
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {tab === 'invoices' && (
        <div className="rc-table-wrap">
          <table className="rc-table">
            <thead>
              <tr>
                <th>{t('Счёт')}</th>
                <th>{t('Срок оплаты')}</th>
                <th className="rc-num">{t('Сумма')}</th>
                <th className="rc-num">{t('Остаток')}</th>
              </tr>
            </thead>
            <tbody>
              {debtor.invoices.map((item) => (
                <tr key={item.id}>
                  <td>
                    <button className="wf-text-button" onClick={() => onOpenInvoice(item.id)}>
                      {item.number}
                    </button>
                  </td>
                  <td>{dateText(item.due_on)}</td>
                  <td className="rc-num">{money(item.amount)}</td>
                  <td className="rc-num">{money(item.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'conversation' && (
        <ConversationPanel
          debtor={debtor}
          notify={notify}
          onWrite={onOpenInvoice}
          onReply={onReply}
        />
      )}

      {tab === 'documents' && (
        <EvidencePanel debtor={debtor} notify={notify} onSaved={() => void load()} />
      )}

      {tab === 'documents' && (
        <div className="rc-card">
          <h2>{t('Претензии и заявления')}</h2>
          {kinds.length > 0 && (
            <div className="rc-action-list">
              {kinds.map(([kind, item]) => (
                <button
                  key={kind}
                  className="button button-outline"
                  onClick={() =>
                    post(`/recovery/debtors/${id}/documents`, { kind })
                      .then(() => load())
                      .catch((error) => notify(error.message, true))
                  }
                >
                  {t(item.title)}
                </button>
              ))}
            </div>
          )}
          <ul className="rc-documents">
            {debtor.documents.map((doc) => (
              <li key={doc.id}>
                <span>
                  {t(doc.title)} · {t('версия {0}', [doc.version])}
                </span>
                <a href={`/api/recovery/documents/${doc.id}/download`}>
                  <Download size={14} />
                  DOCX
                </a>
              </li>
            ))}
            {debtor.documents.length === 0 && (
              <li className="rc-muted">{t('Документы появятся по мере движения дела.')}</li>
            )}
          </ul>
        </div>
      )}

      {tab === 'cases' && (
        <RegisterPanel debtor={debtor} notify={notify} onSaved={() => void load()} />
      )}

      {tab === 'financing' && (
        <FinancingPanel debtor={debtor} notify={notify} onDone={() => void load()} />
      )}

      {tab === 'history' && (
        <ul className="rc-log rc-card">
          {debtor.log.length === 0 && <li className="rc-muted">{t('Действий пока нет.')}</li>}
          {debtor.log.map((row) => (
            <li key={row.id}>
              <strong>{t(meta.action_labels[row.action] ?? row.action)}</strong>
              <span>
                {dateText(row.created_at)} · {row.actor_name}
              </span>
              {row.detail && <small>{t(row.detail)}</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
