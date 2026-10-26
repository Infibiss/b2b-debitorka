import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  ArrowRight,
  Bot,
  Check,
  CircleCheck,
  Clock3,
  FileText,
  LayoutGrid,
  List,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  Users,
  AlertCircle,
  Link2,
  Mail,
  Download,
} from 'lucide-react';
import { api, post, money, dateText, type Invoice, type InvoiceEvent, type Message } from '../api';
import { Dialog } from './Dialog';
import './workflow.css';

type Queue = 'needs_decision' | 'in_progress' | 'results';
type Stage =
  | 'verification'
  | 'documents'
  | 'contact'
  | 'waiting'
  | 'agreement'
  | 'paid'
  | 'disputed'
  | 'paused';
type WorkCase = {
  id: string;
  counterparty_id: string;
  company: string;
  inn: string;
  email: string;
  contract_id: string | null;
  contract_number: string | null;
  contract_known: boolean;
  invoice_ids: string[];
  invoice_count: number;
  balance: number;
  overdue_amount: number;
  paid_amount: number;
  stage: Stage;
  queue: Queue;
  automation_active: boolean;
  next_action: string;
  exceptions_count: number;
  legal_escalation?: boolean;
  legal_stage?: string | null;
  deadlines?: { id: string; review_on: string; basis?: string; kind?: string }[];
};
type Exception = {
  id: string;
  kind: string;
  title: string;
  detail: string;
  status: string;
  required_role?: string;
  resolution?: string;
};
type Document = {
  id: string;
  download_url?: string | null;
  reference?: string;
  filename?: string;
  kind?: string;
  occurred_on?: string;
  created_at?: string;
};
type FinancialEvent = {
  id: string;
  type?: string;
  kind?: string;
  title?: string;
  amount?: number;
  signed_amount?: number;
  paid_on?: string;
  occurred_on?: string;
  created_at?: string;
  effective_on?: string;
  confirmed?: boolean;
  reference?: string;
};
type CaseDetail = WorkCase & {
  invoices: Invoice[];
  events: InvoiceEvent[];
  messages: Message[];
  documents: Document[];
  financial_events: FinancialEvent[];
  exceptions: Exception[];
};
type CaseList = { items: WorkCase[]; summary: Record<Queue, number> };
type Policy = {
  version: number;
  enabled: boolean;
  cooldown_days: number;
  weekdays: number[];
  start_hour: number;
  end_hour: number;
  auto_record_promises: boolean;
  auto_record_disputes: boolean;
  smtp_configured: boolean;
};
type Team = {
  role: 'manager' | 'accountant';
  members: { id: string; name: string; email: string; role: string }[];
  invitations: { id: string; email: string; expires_at: string; accepted_at: string | null }[];
};
type Navigate = (tab: string) => void;
type Notify = (text: string, error?: boolean) => void;
const queues: { id: Queue; name: string; detail: string; icon: typeof AlertCircle }[] = [
  {
    id: 'needs_decision',
    name: 'Требует решения',
    detail: 'Проверки и исключения',
    icon: AlertCircle,
  },
  {
    id: 'in_progress',
    name: 'В работе у Mandato',
    detail: 'Следующий шаг под контролем',
    icon: Bot,
  },
  { id: 'results', name: 'Результаты', detail: 'Закрытые обязательства', icon: CircleCheck },
];
const stages: Record<Stage, string> = {
  verification: 'Проверка',
  documents: 'Документы',
  contact: 'Контакт',
  waiting: 'Ожидание',
  agreement: 'Договорённость',
  paid: 'Обязательства закрыты',
  disputed: 'Спор',
  paused: 'Приостановлено',
};
const documentNames: Record<string, string> = {
  contract: 'Договор',
  performance: 'Исполнение',
  payment_terms: 'Условия оплаты',
  reconciliation: 'Акт сверки',
  correspondence: 'Переписка',
  other: 'Документ',
};
const financialNames: Record<string, string> = {
  opening: 'Оплата на начало учёта',
  payment: 'Поступление',
  allocation: 'Распределение оплаты',
  reversal: 'Отмена операции',
  adjustment: 'Корректировка',
  promise: 'Обещание оплаты',
};
const messageNames: Record<string, string> = {
  draft: 'Черновик',
  approved: 'Согласовано',
  sent: 'Отправлено',
  failed: 'Ошибка отправки',
  received: 'Входящее',
};
const failure = (error: unknown) =>
  error instanceof Error ? error.message : 'Не удалось загрузить данные. Попробуйте ещё раз.';
const casePath = (id: string) => `/workflow/cases/${encodeURIComponent(id)}`;

export function WorkflowDesk({
  invoices,
  totals,
  onOpenInvoice,
  onNavigate,
  onImport,
  onCreate,
  notify,
  refreshKey,
}: {
  invoices: Invoice[];
  totals?: {
    total_outstanding: number;
    overdue_amount: number;
    promised_amount: number;
    collected_amount: number;
  };
  onOpenInvoice: (id: string) => void;
  onNavigate: Navigate;
  onImport: () => void;
  onCreate: () => void;
  notify: Notify;
  refreshKey?: unknown;
}) {
  const [data, setData] = useState<CaseList | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [queue, setQueue] = useState<Queue | ''>('');
  const [view, setView] = useState<'board' | 'table'>('board');
  const [selected, setSelected] = useState<string | null>(null);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api<CaseList>('/workflow/cases'));
      setError('');
    } catch (e) {
      setError(failure(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload, invoices, refreshKey]);
  const items = (data?.items || []).filter(
    (item) =>
      (!queue || item.queue === queue) &&
      `${item.company} ${item.inn} ${item.contract_number || ''}`
        .toLocaleLowerCase('ru')
        .includes(query.toLocaleLowerCase('ru'))
  );
  return (
    <div className="wf-desk" data-tour="workflow-board">
      <div className="wf-heading">
        <div>
          <span className="wf-eyebrow">Единый рабочий процесс</span>
          <h1>Работа по дебиторке</h1>
          <p>Mandato ведёт дела. Вы подключаетесь там, где нужно решение.</p>
        </div>
        <div className="wf-actions">
          <button className="button button-white" data-tour="work-import" onClick={onImport}>
            <Upload size={15} />
            Импортировать
          </button>
          <button className="button button-dark" onClick={onCreate}>
            <Plus size={15} />
            Добавить счёт
          </button>
        </div>
      </div>
      <section className="wf-portfolio-sums" aria-label="Суммы по портфелю">
        {[
          ['Осталось к оплате', totals?.total_outstanding],
          ['Просрочено', totals?.overdue_amount],
          ['Обещано к оплате', totals?.promised_amount],
          ['Поступило', totals?.collected_amount],
        ].map(([label, value]) => (
          <div key={String(label)}>
            <span>{label}</span>
            <strong
              title={money(typeof value === 'number' ? value : 0)}
              aria-label={money(typeof value === 'number' ? value : 0)}
            >
              {money(typeof value === 'number' ? value : 0, true)}
            </strong>
          </div>
        ))}
      </section>
      <div className="wf-metrics" data-tour="workflow-queues">
        {queues.map(({ id, name, detail, icon: Icon }) => (
          <button
            key={id}
            className={`wf-metric wf-${id} ${queue === id ? 'is-selected' : ''}`}
            aria-pressed={queue === id}
            onClick={() => setQueue(queue === id ? '' : id)}
          >
            <span className="wf-metric-top">
              <Icon size={19} />
              {name}
              <ArrowRight size={15} />
            </span>
            <strong>{data?.summary[id] ?? '—'}</strong>
            <small>{detail}</small>
          </button>
        ))}
      </div>
      <div className="wf-route" aria-label="Этапы работы">
        <span>Проверка</span>
        <ArrowRight size={12} />
        <span>Документы</span>
        <ArrowRight size={12} />
        <span>Контакт</span>
        <ArrowRight size={12} />
        <span>Договорённость</span>
        <ArrowRight size={12} />
        <span>
          <CircleCheck size={12} />
          Оплата
        </span>
      </div>
      <section className="wf-work">
        <div className="wf-toolbar">
          <div className="wf-search">
            <Search size={16} />
            <input
              aria-label="Поиск дел"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Контрагент, ИНН или договор"
            />
          </div>
          <div className="wf-view" aria-label="Вид дел">
            <button
              aria-label="Доска"
              aria-pressed={view === 'board'}
              className={view === 'board' ? 'active' : ''}
              onClick={() => setView('board')}
            >
              <LayoutGrid size={15} />
              <span>Доска</span>
            </button>
            <button
              aria-label="Таблица"
              aria-pressed={view === 'table'}
              className={view === 'table' ? 'active' : ''}
              onClick={() => setView('table')}
            >
              <List size={15} />
              <span>Таблица</span>
            </button>
          </div>
          <button
            className="icon-button"
            aria-label="Обновить дела"
            onClick={() => void reload()}
            disabled={loading}
          >
            <RefreshCw size={16} className={loading ? 'wf-spinning' : ''} />
          </button>
        </div>
        {queue && (
          <div className="wf-filter">
            {queues.find((item) => item.id === queue)?.name}
            <button onClick={() => setQueue('')}>Показать все дела</button>
          </div>
        )}
        {error && (
          <div className="wf-error" role="alert">
            {error}
            <button onClick={() => void reload()}>Повторить</button>
          </div>
        )}
        {loading && !data ? (
          <div className="wf-empty" role="status">
            <RefreshCw className="wf-spinning" size={25} />
            <p>Собираем дела…</p>
          </div>
        ) : data?.items.length === 0 ? (
          <div className="wf-empty">
            <div className="wf-empty-icon">
              <FileText size={28} />
            </div>
            <h2>Начните с вашего реестра</h2>
            <p>
              Загрузите счета — Mandato соберёт дела по контрагентам и договорам, покажет пробелы и
              предложит следующий шаг.
            </p>
            <div className="wf-actions" data-tour="workflow-empty">
              <button className="button button-dark" onClick={onImport}>
                <Upload size={15} />
                Загрузить реестр
              </button>
              <button className="button button-white" onClick={() => onNavigate('connections')}>
                Подключить источник
                <ArrowRight size={14} />
              </button>
            </div>
            <span className="wf-empty-note">
              <ShieldCheck size={14} />
              Автоматические напоминания включаются в управлении
            </span>
          </div>
        ) : !items.length && data ? (
          <div className="wf-empty">
            <Search size={24} />
            <h2>Дела не найдены</h2>
            <p>Попробуйте другой запрос или снимите фильтр.</p>
            <button
              className="button button-white"
              data-tour="workflow-filter-empty"
              onClick={() => {
                setQuery('');
                setQueue('');
              }}
            >
              Сбросить фильтры
            </button>
          </div>
        ) : view === 'board' ? (
          <div className={`wf-board ${queue ? 'wf-board-filtered' : ''}`}>
            {queues
              .filter((column) => !queue || column.id === queue)
              .map((column) => (
                <section className={`wf-column wf-${column.id}`} key={column.id}>
                  <header>
                    <span className="wf-column-dot" />
                    <h2>{column.name}</h2>
                    <b>{items.filter((item) => item.queue === column.id).length}</b>
                  </header>
                  <div className="wf-column-cards">
                    {items
                      .filter((item) => item.queue === column.id)
                      .map((item) => (
                        <CaseCard key={item.id} item={item} onOpen={() => setSelected(item.id)} />
                      ))}
                    {!items.some((item) => item.queue === column.id) && (
                      <p className="wf-column-empty">
                        {column.id === 'needs_decision'
                          ? 'Нет дел, требующих решения'
                          : column.id === 'in_progress'
                            ? 'Здесь появятся запущенные дела'
                            : 'Здесь появятся закрытые дела'}
                      </p>
                    )}
                  </div>
                </section>
              ))}
          </div>
        ) : (
          <div className="wf-table" role="table" aria-label="Дела по дебиторке">
            <div className="wf-table-head" role="row">
              <span role="columnheader">Контрагент и договор</span>
              <span role="columnheader">Остаток</span>
              <span role="columnheader">Этап</span>
              <span role="columnheader">Следующее действие</span>
            </div>
            {items.map((item) => (
              <button
                className="wf-table-row"
                data-tour="workflow-case"
                role="row"
                key={item.id}
                aria-label={`Открыть дело ${item.company}`}
                onClick={() => setSelected(item.id)}
              >
                <span role="cell">
                  <strong>{item.company}</strong>
                  <small>
                    {contractText(item)} · Счетов: {item.invoice_count}
                  </small>
                </span>
                <span role="cell">
                  <b>{money(item.balance)}</b>
                  {item.overdue_amount > 0 && (
                    <small className="wf-overdue">Просрочено {money(item.overdue_amount)}</small>
                  )}
                </span>
                <span role="cell">
                  <StageBadge stage={item.stage} />
                </span>
                <span role="cell" className="wf-table-next">
                  {item.next_action}
                  <ArrowRight size={15} />
                </span>
              </button>
            ))}
          </div>
        )}
      </section>
      <div className="wf-toolstrip">
        <span>
          <ShieldCheck size={16} />
          Этапы меняются по событиям и документам
        </span>
        <button onClick={() => onNavigate('audit')}>
          Проверить реестр
          <ArrowRight size={14} />
        </button>
        <button onClick={() => onNavigate('finance')}>
          Разобрать поступления
          <ArrowRight size={14} />
        </button>
      </div>
      {selected && (
        <CaseDialog
          id={selected}
          onClose={() => setSelected(null)}
          onNavigate={(tab) => {
            setSelected(null);
            onNavigate(tab);
          }}
          onOpenInvoice={(id) => {
            setSelected(null);
            onOpenInvoice(id);
          }}
          notify={notify}
          onChanged={reload}
          allInvoices={invoices}
        />
      )}
    </div>
  );
}
function exceptionTool(kind: string): { tab: string; label: string } {
  if (kind.includes('payment')) return { tab: 'finance', label: 'Сверить поступление' };
  if (kind.includes('document')) return { tab: 'audit', label: 'Проверить документы' };
  if (kind.includes('legal')) return { tab: 'legal', label: 'Проверить юридическое дело' };
  if (kind.includes('delivery') || kind.includes('contact'))
    return { tab: 'settings', label: 'Проверить канал и контакты' };
  if (kind.includes('incoming')) return { tab: 'agent', label: 'Разобрать ответ контрагента' };
  return { tab: 'intelligence', label: 'Проверить условия и согласования' };
}
function contractText(item: WorkCase) {
  return item.contract_known
    ? `Договор ${item.contract_number || 'без номера'}`
    : 'Договор не определён';
}
function StageBadge({ stage }: { stage: Stage }) {
  return <span className={`wf-stage wf-stage-${stage}`}>{stages[stage] || 'Проверка'}</span>;
}
function CaseCard({ item, onOpen }: { item: WorkCase; onOpen: () => void }) {
  return (
    <button
      className="wf-case"
      data-tour="workflow-case"
      aria-label={`Открыть дело ${item.company}`}
      onClick={onOpen}
    >
      <div className="wf-case-top">
        <StageBadge stage={item.stage} />
        {item.legal_escalation && (
          <span className="wf-stage wf-stage-disputed">Юридическая работа</span>
        )}
        {item.automation_active && <Bot size={15} aria-label="Автоматизация активна" />}
      </div>
      <h3>{item.company}</h3>
      <p className={!item.contract_known ? 'wf-unknown' : ''}>{contractText(item)}</p>
      <div className="wf-case-amount">
        <strong>{money(item.balance)}</strong>
        <span>Счетов: {item.invoice_count}</span>
      </div>
      {item.overdue_amount > 0 && (
        <small className="wf-overdue">В том числе просрочено {money(item.overdue_amount)}</small>
      )}
      <div className="wf-case-next">
        <span>{item.next_action}</span>
        <ArrowRight size={15} />
      </div>
      {item.exceptions_count > 0 && (
        <span className="wf-case-exceptions">
          <AlertCircle size={12} />
          Исключений: {item.exceptions_count}
        </span>
      )}
    </button>
  );
}

function CaseDialog({
  id,
  onClose,
  onOpenInvoice,
  onNavigate,
  notify,
  onChanged,
  allInvoices,
}: {
  id: string;
  onClose: () => void;
  onOpenInvoice: (id: string) => void;
  onNavigate: Navigate;
  notify: Notify;
  onChanged: () => Promise<void>;
  allInvoices: Invoice[];
}) {
  const [item, setItem] = useState<CaseDetail | null>(null);
  const [role, setRole] = useState('accountant');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<'invoices' | 'history' | 'documents' | 'messages' | 'finance'>(
    'invoices'
  );
  const [assigning, setAssigning] = useState(false);
  const [currentId, setCurrentId] = useState(id);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [result, team] = await Promise.all([
        api<CaseDetail>(casePath(currentId)),
        api<Team>('/workflow/team'),
      ]);
      setItem(result);
      setRole(team.role);
      setError('');
    } catch (e) {
      setError(failure(e));
    } finally {
      setLoading(false);
    }
  }, [currentId]);
  useEffect(() => {
    void reload();
  }, [reload]);
  async function act(action: 'start' | 'pause' | 'resume') {
    setBusy(true);
    setError('');
    try {
      await post(
        `${casePath(currentId)}/${action}`,
        action === 'pause' ? { reason: 'Приостановлено пользователем из карточки дела' } : {}
      );
      await reload();
      await onChanged();
      notify(action === 'pause' ? 'Работа по делу приостановлена' : 'Работа по делу запущена');
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  async function assign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!item) return;
    const values = new FormData(event.currentTarget);
    const invoiceIds = values.getAll('invoice_ids').map(String);
    setBusy(true);
    setError('');
    try {
      const result = await post<{ case_id: string }>('/workflow/contracts', {
        counterparty_id: item.counterparty_id,
        number: String(values.get('number')).trim(),
        invoice_ids: invoiceIds,
      });
      setAssigning(false);
      setCurrentId(result.case_id);
      if (result.case_id === currentId) await reload();
      await onChanged();
      notify('Договор указан. Проверьте объединённое дело перед запуском.');
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  async function resolve(event: FormEvent<HTMLFormElement>, exceptionId: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError('');
    try {
      await post(`/workflow/exceptions/${encodeURIComponent(exceptionId)}/resolve`, {
        resolution: form.get('resolution'),
      });
      await reload();
      await onChanged();
      notify('Решение по исключению сохранено');
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  const relatedInvoices = allInvoices.filter(
    (invoice) =>
      (!!item?.inn && invoice.inn === item.inn) || !!item?.invoice_ids.includes(invoice.id)
  );
  return (
    <Dialog title="Карточка дела" onClose={onClose} wide>
      <div className="wf-case-dialog">
        {error && (
          <div className="wf-error" role="alert">
            {error}
            <button onClick={() => void reload()}>Повторить</button>
          </div>
        )}
        {loading && !item ? (
          <p role="status">Загружаем дело…</p>
        ) : (
          item && (
            <>
              <div className="wf-case-identity">
                <div>
                  <span className="wf-eyebrow">{contractText(item)}</span>
                  <h3>{item.company}</h3>
                  <p>
                    ИНН {item.inn || 'не указан'} · {item.email || 'Email не указан'}
                  </p>
                </div>
                <StageBadge stage={item.stage} />
              </div>
              <div className="wf-case-totals">
                <div>
                  <span>Остаток</span>
                  <strong>{money(item.balance)}</strong>
                </div>
                <div>
                  <span>Просрочено</span>
                  <strong>{money(item.overdue_amount)}</strong>
                </div>
                <div>
                  <span>Оплата по реестру</span>
                  <strong>{money(item.paid_amount)}</strong>
                </div>
              </div>
              <div className="wf-next-action">
                <Bot size={23} />
                <div>
                  <small>Следующий шаг</small>
                  <strong>{item.next_action}</strong>
                  <p>
                    {item.automation_active
                      ? 'Mandato работает по утверждённым правилам.'
                      : 'Автоматическая работа по делу не активна.'}
                  </p>
                  {!item.automation_active && item.balance > 0 && (
                    <button className="wf-text-button" onClick={() => onNavigate('management')}>
                      Проверить правила работы
                      <ArrowRight size={13} />
                    </button>
                  )}
                </div>
              </div>
              {!!item.deadlines?.length && (
                <section className="wf-exceptions">
                  <h4>
                    <Clock3 size={16} />
                    Контрольные сроки
                  </h4>
                  {item.deadlines.map((deadline) => (
                    <article key={deadline.id}>
                      <strong>Проверка до {dateText(deadline.review_on)}</strong>
                      {deadline.basis && <p>{deadline.basis}</p>}
                    </article>
                  ))}
                  <button className="wf-text-button" onClick={() => onNavigate('legal')}>
                    Открыть юридическую работу
                    <ArrowRight size={13} />
                  </button>
                </section>
              )}
              <div className="wf-actions wf-case-controls">
                {item.balance > 0 &&
                  (item.automation_active ? (
                    <button
                      disabled={busy}
                      className="button button-white"
                      onClick={() => void act('pause')}
                    >
                      <Pause size={14} />
                      Приостановить
                    </button>
                  ) : (
                    <button
                      disabled={busy}
                      className="button button-dark"
                      onClick={() => void act(item.stage === 'paused' ? 'resume' : 'start')}
                    >
                      <Play size={14} />
                      Запустить работу
                    </button>
                  ))}
                <button className="button button-white" onClick={() => setAssigning(!assigning)}>
                  <Link2 size={14} />
                  {item.contract_known ? 'Уточнить договор' : 'Указать договор'}
                </button>
                <button className="button button-white" onClick={() => onNavigate('intelligence')}>
                  Условия и согласования
                  <ArrowRight size={14} />
                </button>
              </div>
              {assigning && (
                <form onSubmit={assign} className="wf-inline-form">
                  <h4>Объединить счета по договору</h4>
                  <label>
                    Номер договора
                    <input
                      required
                      name="number"
                      defaultValue={item.contract_number || ''}
                      maxLength={120}
                      placeholder="Например, 24/2026"
                    />
                  </label>
                  <fieldset>
                    <legend>Счета этого контрагента</legend>
                    {relatedInvoices.map((invoice) => (
                      <label className="wf-check" key={invoice.id}>
                        <input
                          type="checkbox"
                          name="invoice_ids"
                          value={invoice.id}
                          defaultChecked={item.invoice_ids.includes(invoice.id)}
                        />
                        {invoice.number} · {money(invoice.balance)}
                      </label>
                    ))}
                  </fieldset>
                  <p>После объединения автоматизацию нужно запустить снова.</p>
                  <button className="button button-dark" disabled={busy}>
                    Сохранить договор
                  </button>
                </form>
              )}
              {item.exceptions?.some((exception) => exception.status !== 'resolved') && (
                <section className="wf-exceptions">
                  <h4>
                    <AlertCircle size={16} />
                    Требует решения
                  </h4>
                  {item.exceptions
                    .filter((exception) => exception.status !== 'resolved')
                    .map((exception) => (
                      <article key={exception.id}>
                        <strong>{exception.title}</strong>
                        <p>{exception.detail}</p>
                        {role === 'manager' || exception.required_role === 'accountant' ? (
                          <form onSubmit={(event) => void resolve(event, exception.id)}>
                            <label>
                              {exception.required_role === 'manager'
                                ? 'Решение руководителя'
                                : 'Результат проверки'}
                              <input
                                name="resolution"
                                required
                                minLength={3}
                                maxLength={2000}
                                placeholder="Основание и принятое решение"
                              />
                            </label>
                            <div className="wf-actions">
                              <button className="button button-white" disabled={busy}>
                                <Check size={14} />
                                Зафиксировать решение
                              </button>
                              <button
                                type="button"
                                className="wf-text-button"
                                onClick={() => onNavigate(exceptionTool(exception.kind).tab)}
                              >
                                {exceptionTool(exception.kind).label}
                              </button>
                            </div>
                            <small>
                              Денежные операции и изменение условий оформляются отдельно.
                            </small>
                          </form>
                        ) : (
                          <>
                            <small>Решение принимает руководитель.</small>
                            <button
                              className="wf-text-button"
                              onClick={() => onNavigate(exceptionTool(exception.kind).tab)}
                            >
                              {exceptionTool(exception.kind).label}
                              <ArrowRight size={13} />
                            </button>
                          </>
                        )}
                      </article>
                    ))}
                </section>
              )}
              <div className="wf-detail-tabs" role="tablist" aria-label="Материалы дела">
                {(
                  [
                    ['invoices', 'Счета'],
                    ['history', 'История'],
                    ['documents', 'Документы'],
                    ['messages', 'Переписка'],
                    ['finance', 'Финансовый реестр'],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    role="tab"
                    aria-selected={tab === key}
                    key={key}
                    onClick={() => setTab(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div
                className="wf-detail-content"
                role="tabpanel"
                aria-label={
                  {
                    invoices: 'Счета',
                    history: 'История',
                    documents: 'Документы',
                    messages: 'Переписка',
                    finance: 'Финансовый реестр',
                  }[tab]
                }
              >
                {tab === 'invoices' && (
                  <>
                    {item.invoices?.map((invoice) => (
                      <button
                        className="wf-invoice"
                        key={invoice.id}
                        aria-label={`Открыть счёт ${invoice.number}`}
                        onClick={() => onOpenInvoice(invoice.id)}
                      >
                        <FileText size={19} />
                        <span>
                          <strong>{invoice.number}</strong>
                          <small>
                            Оплата до {dateText(invoice.due_on)}
                            {invoice.days_overdue > 0 && invoice.balance > 0
                              ? ` · Просрочка ${invoice.days_overdue} дн.`
                              : ''}
                          </small>
                        </span>
                        <b>{money(invoice.balance)}</b>
                        <ArrowRight size={16} />
                      </button>
                    ))}
                    {!item.invoices?.length && <p className="wf-muted">Счета не найдены.</p>}
                  </>
                )}
                {tab === 'history' && (
                  <ol className="wf-timeline">
                    {item.events?.map((event) => (
                      <li key={event.id}>
                        <span className="wf-timeline-dot" />
                        <div>
                          <strong>{event.title}</strong>
                          <p>{event.detail}</p>
                          <small>{event.created_at ? dateText(event.created_at) : ''}</small>
                        </div>
                      </li>
                    ))}
                    {!item.events?.length && (
                      <p className="wf-muted">История появится после первых действий по делу.</p>
                    )}
                  </ol>
                )}
                {tab === 'documents' && (
                  <>
                    {item.documents?.map((document, index) => (
                      <div className="wf-material" key={document.id || index}>
                        <FileText size={18} />
                        <div>
                          <strong>
                            {document.reference ||
                              document.filename ||
                              documentNames[document.kind || ''] ||
                              'Документ'}
                          </strong>
                          <small>
                            {documentNames[document.kind || ''] || 'Документ'}
                            {document.occurred_on ? ` · ${dateText(document.occurred_on)}` : ''}
                          </small>
                        </div>
                        {document.download_url && (
                          <a
                            className="wf-document-download"
                            href={document.download_url}
                            download
                            aria-label={`Скачать документ ${document.reference || document.filename || 'без названия'}`}
                          >
                            <Download size={15} />
                            <span>Скачать</span>
                          </a>
                        )}
                      </div>
                    ))}
                    {!item.documents?.length && (
                      <p className="wf-muted">По делу пока нет зарегистрированных документов.</p>
                    )}
                    <button className="button button-white" onClick={() => onNavigate('audit')}>
                      Проверить и добавить документы
                      <ArrowRight size={14} />
                    </button>
                  </>
                )}
                {tab === 'messages' && (
                  <>
                    {item.messages?.map((message) => (
                      <article className="wf-message" key={message.id}>
                        <div>
                          <span>{messageNames[message.status] || 'Сообщение'}</span>
                          <small>{dateText(message.created_at)}</small>
                        </div>
                        <h4>{message.subject}</h4>
                        <small>{message.recipient}</small>
                        <p>{message.body}</p>
                      </article>
                    ))}
                    {!item.messages?.length && (
                      <p className="wf-muted">Переписки по делу пока нет.</p>
                    )}
                    <button className="button button-white" onClick={() => onNavigate('agent')}>
                      <Mail size={14} />
                      Открыть работу с ответами
                    </button>
                  </>
                )}
                {tab === 'finance' && (
                  <>
                    {item.financial_events?.map((event, index) => (
                      <div className="wf-material" key={event.id || index}>
                        <CircleCheck size={18} />
                        <div>
                          <strong>
                            {event.title ||
                              financialNames[event.type || event.kind || ''] ||
                              'Финансовое событие'}
                          </strong>
                          <small>
                            {event.reference}
                            {(event.paid_on ||
                              event.effective_on ||
                              event.occurred_on ||
                              event.created_at) &&
                              ` · ${dateText((event.paid_on || event.effective_on || event.occurred_on || event.created_at)!)}`}
                          </small>
                        </div>
                        {typeof (event.amount ?? event.signed_amount) === 'number' && (
                          <b>{money((event.amount ?? event.signed_amount)!)}</b>
                        )}
                      </div>
                    ))}
                    {!item.financial_events?.length && (
                      <p className="wf-muted">Финансовых событий пока нет.</p>
                    )}
                    <button className="button button-white" onClick={() => onNavigate('finance')}>
                      Проверить поступления и распределение
                      <ArrowRight size={14} />
                    </button>
                  </>
                )}
              </div>
            </>
          )
        )}
      </div>
    </Dialog>
  );
}

export function WorkflowManagement({
  notify,
  onNavigate,
}: {
  notify: Notify;
  onNavigate?: Navigate;
}) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [inviteLink, setInviteLink] = useState('');
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [rules, people] = await Promise.all([
        api<Policy>('/workflow/policy'),
        api<Team>('/workflow/team'),
      ]);
      setPolicy(rules);
      setTeam(people);
      setError('');
    } catch (e) {
      setError(failure(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy) return;
    setBusy(true);
    setError('');
    try {
      await api('/workflow/policy', {
        method: 'PUT',
        body: JSON.stringify({
          expected_version: policy.version,
          enabled: policy.enabled,
          cooldown_days: policy.cooldown_days,
          weekdays: policy.weekdays,
          start_hour: policy.start_hour,
          end_hour: policy.end_hour,
          auto_record_promises: policy.auto_record_promises,
          auto_record_disputes: policy.auto_record_disputes,
        }),
      });
      await reload();
      notify('Правила работы сохранены');
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const email = String(new FormData(form).get('email')).trim();
    setBusy(true);
    setError('');
    try {
      const result = await post<{ token: string }>('/workflow/invitations', { email });
      setInviteLink(`${window.location.origin}/app#invite=${encodeURIComponent(result.token)}`);
      form.reset();
      await reload();
      notify('Приглашение создано. Передайте ссылку бухгалтеру.');
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  const manager = team?.role === 'manager';
  return (
    <div className="wf-desk" data-tour="workflow-policy">
      <div className="wf-heading">
        <div>
          <span className="wf-eyebrow">Полномочия и контроль</span>
          <h1>Правила и команда</h1>
          <p>Задайте рамки, в которых Mandato работает самостоятельно.</p>
        </div>
        <ShieldCheck className="wf-heading-icon" size={31} />
      </div>
      {error && (
        <div className="wf-error" role="alert">
          {error}
          <button onClick={() => void reload()}>Обновить данные</button>
        </div>
      )}
      {loading && !policy ? (
        <p role="status">Загружаем правила и команду…</p>
      ) : (
        policy && (
          <div className="wf-management-grid">
            <section className="wf-panel">
              <div className="wf-panel-title">
                <Bot size={21} />
                <div>
                  <h2>Работа Mandato</h2>
                  <p>Обычные напоминания — по утверждённым правилам</p>
                </div>
              </div>
              <form onSubmit={save}>
                <label className="wf-switch">
                  <input
                    type="checkbox"
                    aria-label="Автоматические напоминания"
                    checked={policy.enabled}
                    disabled={!manager || busy}
                    onChange={(e) => setPolicy({ ...policy, enabled: e.target.checked })}
                  />
                  <span>
                    <strong>Автоматические напоминания</strong>
                    <small>
                      {policy.enabled
                        ? 'Включены для запущенных дел'
                        : 'Выключены. Сначала проверьте канал и расписание.'}
                    </small>
                  </span>
                </label>
                <div className={`wf-channel ${policy.smtp_configured ? 'wf-channel-ok' : ''}`}>
                  <Mail size={17} />
                  <div>
                    <strong>
                      {policy.smtp_configured
                        ? 'Почтовый канал настроен'
                        : 'Почтовый канал не подключён'}
                    </strong>
                    <p>
                      {policy.smtp_configured
                        ? 'Перед отправкой проверяются остаток, контакт и ограничения.'
                        : 'Для автоматических писем требуется настройка SMTP.'}
                    </p>
                    {!policy.smtp_configured && onNavigate && (
                      <button
                        type="button"
                        className="wf-text-button"
                        onClick={() => onNavigate('settings')}
                      >
                        Открыть настройки отправителя
                        <ArrowRight size={13} />
                      </button>
                    )}
                  </div>
                </div>
                <fieldset disabled={!manager || busy} className="wf-policy-fields">
                  <legend>Расписание · московское время</legend>
                  <div className="wf-form-pair">
                    <label>
                      Начало
                      <input
                        type="number"
                        min="0"
                        max="23"
                        required
                        value={policy.start_hour}
                        onChange={(e) =>
                          setPolicy({ ...policy, start_hour: Number(e.target.value) })
                        }
                      />
                    </label>
                    <label>
                      Окончание
                      <input
                        type="number"
                        min="1"
                        max="24"
                        required
                        value={policy.end_hour}
                        onChange={(e) => setPolicy({ ...policy, end_hour: Number(e.target.value) })}
                      />
                    </label>
                  </div>
                  <div className="wf-weekdays">
                    {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((day, index) => (
                      <label key={day}>
                        <input
                          type="checkbox"
                          aria-label={
                            [
                              'Понедельник',
                              'Вторник',
                              'Среда',
                              'Четверг',
                              'Пятница',
                              'Суббота',
                              'Воскресенье',
                            ][index]
                          }
                          checked={policy.weekdays.includes(index)}
                          onChange={(e) =>
                            setPolicy({
                              ...policy,
                              weekdays: e.target.checked
                                ? [...policy.weekdays, index].sort()
                                : policy.weekdays.filter((day) => day !== index),
                            })
                          }
                        />
                        <span>{day}</span>
                      </label>
                    ))}
                  </div>
                  <label>
                    Пауза между напоминаниями, дней
                    <input
                      required
                      type="number"
                      min="1"
                      max="90"
                      aria-label="Пауза между напоминаниями, дней"
                      value={policy.cooldown_days}
                      onChange={(e) =>
                        setPolicy({ ...policy, cooldown_days: Number(e.target.value) })
                      }
                    />
                    <small>Общая по контрагенту, включая разные счета и договоры.</small>
                  </label>
                  <label className="wf-check">
                    <input
                      type="checkbox"
                      checked={policy.auto_record_promises}
                      onChange={(e) =>
                        setPolicy({ ...policy, auto_record_promises: e.target.checked })
                      }
                    />
                    Записывать однозначные обещания оплаты
                  </label>
                  <label className="wf-check">
                    <input
                      type="checkbox"
                      checked={policy.auto_record_disputes}
                      onChange={(e) =>
                        setPolicy({ ...policy, auto_record_disputes: e.target.checked })
                      }
                    />
                    Фиксировать выявленные споры
                  </label>
                </fieldset>
                <div className="wf-boundary">
                  <ShieldCheck size={16} />
                  <p>
                    Скидки, рассрочки и юридическая эскалация требуют решения руководителя. Обещания
                    оплаты не меняют остаток долга.
                  </p>
                </div>
                {manager ? (
                  <button
                    className="button button-dark"
                    disabled={
                      busy ||
                      (policy.enabled &&
                        (!policy.smtp_configured ||
                          !policy.weekdays.length ||
                          policy.end_hour <= policy.start_hour))
                    }
                  >
                    <Check size={15} />
                    {busy ? 'Сохраняем…' : 'Сохранить правила'}
                  </button>
                ) : (
                  <p className="wf-muted">Изменять правила может руководитель организации.</p>
                )}
              </form>
            </section>
            <section className="wf-panel" data-tour="workflow-team">
              <div className="wf-panel-title">
                <Users size={21} />
                <div>
                  <h2>Ваша команда</h2>
                  <p>Общее пространство счетов, истории и решений</p>
                </div>
              </div>
              <span className="wf-role">Ваша роль: {manager ? 'руководитель' : 'бухгалтер'}</span>
              <div className="wf-members">
                {team?.members.map((member) => (
                  <div className="wf-member" key={member.id}>
                    <span className="wf-avatar">
                      {(member.name || member.email).slice(0, 1).toUpperCase()}
                    </span>
                    <div>
                      <strong>{member.name || member.email}</strong>
                      <small>{member.email}</small>
                    </div>
                    <span>{member.role === 'manager' ? 'Руководитель' : 'Бухгалтер'}</span>
                  </div>
                ))}
              </div>
              {manager && (
                <form className="wf-invite-form" onSubmit={invite}>
                  <h3>Пригласить бухгалтера</h3>
                  <p>
                    Бухгалтер работает с делами и платежами. Согласования и правила остаются у
                    руководителя.
                  </p>
                  <label>
                    Email
                    <input
                      type="email"
                      name="email"
                      required
                      maxLength={254}
                      placeholder="accountant@company.ru"
                    />
                  </label>
                  <button className="button button-white" disabled={busy}>
                    <Plus size={15} />
                    Создать приглашение
                  </button>
                </form>
              )}
              {inviteLink && (
                <div className="wf-invite-link">
                  <label>
                    Ссылка для приглашённого бухгалтера
                    <input readOnly value={inviteLink} onFocus={(e) => e.currentTarget.select()} />
                  </label>
                  <p>Передайте ссылку лично. Вход выполняется с указанным в приглашении email.</p>
                </div>
              )}
              {team?.invitations.some((invitation) => !invitation.accepted_at) && (
                <div className="wf-pending">
                  <h3>Приглашения ожидают ответа</h3>
                  {team.invitations
                    .filter((invitation) => !invitation.accepted_at)
                    .map((invitation) => (
                      <div key={invitation.id}>
                        <span>{invitation.email}</span>
                        <small>
                          {new Date(invitation.expires_at).getTime() < Date.now()
                            ? 'Истекло'
                            : `До ${dateText(invitation.expires_at)}`}
                        </small>
                      </div>
                    ))}
                </div>
              )}
              <div className="wf-team-note">
                <Clock3 size={17} />
                <p>Действия и решения сохраняются в истории дела.</p>
              </div>
            </section>
          </div>
        )
      )}
      <WorkflowMailbox notify={notify} onNavigate={onNavigate} />
    </div>
  );
}

type MailboxIssue = { id: string; status: string; reason: string; created_at: string };
type Mailbox = {
  configured: boolean;
  status: string;
  checked_at: string | null;
  reason: string | null;
  issues_count: number;
  issues: MailboxIssue[];
};
const mailboxReasons: Record<string, string> = {
  mailbox_sync_failed:
    'Не удалось проверить почтовый ящик. Проверьте доступ и настройки подключения.',
  mailbox_authentication: 'Почтовый сервер не подтвердил доступ. Проверьте данные подключения.',
  mailbox_folder: 'Не удалось открыть папку входящих писем.',
  ambiguous_sender: 'В письме неоднозначно указан отправитель. Проверьте исходное письмо.',
  invalid_sender: 'Не удалось определить корректный адрес отправителя.',
  sender_authentication_required: 'Подлинность отправителя не подтверждена почтовым сервером.',
  reply_not_correlated: 'Не удалось однозначно связать ответ с исходящим письмом и делом.',
  sender_mismatch: 'Адрес отправителя не совпадает с подтверждённым контактом дела.',
  plain_text_required: 'В письме нет доступного текстового содержимого. Прочитайте его вручную.',
  text_size_invalid: 'Текст письма не подходит для автоматического разбора. Проверьте его вручную.',
  message_size_unavailable: 'Не удалось определить размер письма до загрузки.',
  message_too_large: 'Письмо превышает допустимый размер. Просмотрите его в почтовом ящике.',
  message_body_unavailable: 'Почтовый сервер не передал содержимое письма.',
  processing_interrupted: 'Разбор письма был прерван. Проверьте, обработан ли ответ по делу.',
  invalid_message: 'Формат письма не удалось проверить. Нужен ручной разбор.',
  invalid_received_time: 'Не удалось подтвердить время получения письма.',
};
function mailboxReason(reason: string | null) {
  return reason
    ? mailboxReasons[reason] || 'Для этого письма или подключения требуется ручная проверка.'
    : '';
}
function mailboxTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Дата проверки недоступна'
    : new Intl.DateTimeFormat('ru-RU', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'Europe/Moscow',
      }).format(date);
}
function WorkflowMailbox({ notify, onNavigate }: { notify: Notify; onNavigate?: Navigate }) {
  const [mailbox, setMailbox] = useState<Mailbox | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [issueError, setIssueError] = useState<{ id: string; text: string } | null>(null);
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setMailbox(await api<Mailbox>('/workflow/mailbox'));
      setError('');
    } catch (e) {
      setError(failure(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  async function resolve(event: FormEvent<HTMLFormElement>, id: string) {
    event.preventDefault();
    const resolution = String(new FormData(event.currentTarget).get('resolution')).trim();
    setBusy(id);
    setIssueError(null);
    try {
      await post(`/workflow/mailbox/issues/${encodeURIComponent(id)}/resolve`, { resolution });
      await reload();
      notify('Результат разбора входящего письма сохранён');
    } catch (e) {
      setIssueError({ id, text: failure(e) });
    } finally {
      setBusy(null);
    }
  }
  const checkedTime = mailbox?.checked_at ? new Date(mailbox.checked_at).getTime() : NaN;
  const stale = !Number.isFinite(checkedTime) || clock - checkedTime > 5 * 60_000;
  const verified = !error && mailbox?.configured && mailbox.status === 'ok' && !stale;
  const statusTitle = error
    ? 'Состояние почты не удалось обновить'
    : !mailbox?.configured
      ? 'Входящая почта не настроена'
      : mailbox.status === 'not_checked' || !mailbox.checked_at
        ? 'Настроено, проверка ещё не выполнена'
        : mailbox.status === 'error'
          ? 'Ошибка проверки входящей почты'
          : mailbox.status === 'backlog'
            ? 'Есть очередь необработанной почты'
            : mailbox.status === 'ok' && stale
              ? 'Проверка почты устарела'
              : verified
                ? 'Получение почты проверено'
                : 'Входящая почта требует проверки';
  return (
    <section className="wf-panel wf-mailbox-panel" aria-label="Входящая почта">
      <div className="wf-panel-title">
        <Mail size={21} />
        <div>
          <h2>Входящая почта</h2>
          <p>Подключение, последняя проверка и письма для ручного разбора</p>
        </div>
        <button
          className="icon-button"
          aria-label="Обновить статус почты"
          disabled={loading}
          onClick={() => void reload()}
        >
          <RefreshCw size={16} className={loading ? 'wf-spinning' : ''} />
        </button>
      </div>
      {error && (
        <div className="wf-error" role="alert">
          Не удалось загрузить состояние входящей почты. {error}
          <button onClick={() => void reload()}>Повторить загрузку почты</button>
        </div>
      )}
      {loading && !mailbox ? (
        <p className="wf-muted" role="status">
          Проверяем сохранённое состояние почты…
        </p>
      ) : (
        mailbox && (
          <>
            <div className={`wf-mailbox-status ${verified ? 'is-verified' : ''}`}>
              <span className="wf-mailbox-symbol">
                {verified ? <CircleCheck size={22} /> : <AlertCircle size={22} />}
              </span>
              <div>
                <h3>{statusTitle}</h3>
                <p>
                  {!mailbox.configured
                    ? 'Автоматическое получение ответов по почте недоступно. Настройте подключение и дождитесь успешной серверной проверки.'
                    : verified
                      ? 'Сервер успешно проверил ящик. Это состояние последней проверки; новые письма появятся после следующего чтения.'
                      : 'Настройка подключения сама по себе не подтверждает, что письма успешно получаются. Проверьте канал до продолжения автоматической работы.'}
                </p>
                {mailbox.reason && (
                  <p className="wf-mailbox-reason">{mailboxReason(mailbox.reason)}</p>
                )}
                <small>
                  {mailbox.checked_at
                    ? `Последняя проверка: ${mailboxTime(mailbox.checked_at)} · МСК`
                    : 'Успешная проверка ещё не зарегистрирована'}
                </small>
              </div>
            </div>
            <div className="wf-mailbox-issues-title">
              <h3>Входящих для разбора: {mailbox.issues_count}</h3>
              {onNavigate && (
                <button className="wf-text-button" onClick={() => onNavigate('connections')}>
                  Подключения и инструкция
                  <ArrowRight size={13} />
                </button>
              )}
            </div>
            {mailbox.issues?.length > 0 ? (
              <>
                <p className="wf-mailbox-note">
                  Проверьте исходное письмо в вашем почтовом ящике и внесите результат разбора. Эта
                  запись не изменяет суммы и не запускает повторную обработку письма.
                </p>
                <div className="wf-mailbox-issues">
                  {mailbox.issues.map((issue, index) => (
                    <article className="wf-mailbox-issue" key={issue.id}>
                      <div className="wf-mailbox-issue-heading">
                        <strong>Письмо для проверки · {index + 1}</strong>
                        <small>{mailboxTime(issue.created_at)} · МСК</small>
                      </div>
                      <p>{mailboxReason(issue.reason)}</p>
                      {issue.status === 'processing' && (
                        <span className="wf-mailbox-processing">Обработка не завершена</span>
                      )}
                      <form onSubmit={(event) => void resolve(event, issue.id)}>
                        <label>
                          Результат проверки
                          <input
                            name="resolution"
                            required
                            minLength={3}
                            maxLength={2000}
                            aria-label={`Результат проверки письма ${index + 1}`}
                            placeholder="Что проверено и какое действие принято"
                          />
                        </label>
                        {issueError?.id === issue.id && (
                          <p className="wf-error" role="alert">
                            {issueError.text}
                          </p>
                        )}
                        <button className="button button-white" disabled={!!busy}>
                          <Check size={14} />
                          {busy === issue.id ? 'Сохраняем…' : 'Зафиксировать разбор'}
                        </button>
                      </form>
                    </article>
                  ))}
                </div>
                {mailbox.issues_count > mailbox.issues.length && (
                  <p className="wf-mailbox-note">
                    Показаны последние {mailbox.issues.length} писем. После разбора список
                    обновится.
                  </p>
                )}
              </>
            ) : (
              <p className="wf-mailbox-note">
                {mailbox.configured
                  ? 'В текущем списке нет писем, ожидающих ручного разбора.'
                  : 'Список входящих появится после настройки и проверки канала.'}
              </p>
            )}
          </>
        )
      )}
    </section>
  );
}
