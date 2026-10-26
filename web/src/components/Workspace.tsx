import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  LayoutDashboard,
  Files,
  Mail,
  Settings as SettingsIcon,
  ArrowUpRight,
  Plus,
  Search,
  Upload,
  Download,
  ArrowRight,
  Check,
  ShieldCheck,
  RefreshCw,
  ChevronRight,
  X,
  Wallet,
  AlertCircle,
  TrendingUp,
  Bot,
  Scale,
  ClipboardCheck,
  PlugZap,
} from 'lucide-react';
import { Brand } from './Brand';
import { WorkspaceProfile, WorkspaceAdvice } from './WorkspaceProfile';
import { Auth } from './Auth';
import { useInvitationToken } from './useInvitationToken';
import { WorkflowDesk, WorkflowManagement } from './WorkflowDesk';
import { WorkflowOnboarding } from './WorkflowOnboarding';
import { YandexDesk } from './YandexDesk';
import './workflow.css';
import { CreateInvoice, ImportInvoices, downloadTemplate } from './InvoiceForms';
import { DebtDrawer, statusNames, statusColors } from './DebtDrawer';
import { FinanceDesk } from './FinanceDesk';
import { AgentDesk } from './AgentDesk';
import LegalDesk from './LegalDesk';
import { PortfolioDesk } from './PortfolioDesk';
import { ConnectionsDesk } from './ConnectionsDesk';
import { IntelligenceDesk } from './IntelligenceDesk';
import {
  api,
  post,
  patch,
  setCsrf,
  money,
  dateText,
  type Session,
  type Invoice,
  type Overview,
  type Settings,
  ApiError,
} from '../api';
import './workspace.css';
type Tab =
  | 'workflow'
  | 'management'
  | 'yandex'
  | 'audit'
  | 'connections'
  | 'intelligence'
  | 'registry'
  | 'finance'
  | 'agent'
  | 'legal'
  | 'messages'
  | 'settings';
const navigation = [
  { id: 'workflow' as Tab, label: 'Работа', icon: LayoutDashboard },
  { id: 'audit' as Tab, label: 'Аудит', icon: ClipboardCheck },
  { id: 'connections' as Tab, label: 'Подключения', icon: PlugZap },
  { id: 'management' as Tab, label: 'Управление', icon: ShieldCheck },
];
const tools = [
  { id: 'registry' as Tab, label: 'Счета', icon: Files },
  { id: 'finance' as Tab, label: 'Оплаты и сверка', icon: Wallet },
  { id: 'messages' as Tab, label: 'Переписка', icon: Mail },
  { id: 'yandex' as Tab, label: 'Документы', icon: Bot },
  { id: 'intelligence' as Tab, label: 'Прогноз и условия', icon: TrendingUp },
  { id: 'legal' as Tab, label: 'Претензии и суд', icon: Scale },
  { id: 'agent' as Tab, label: 'Разбор ответов', icon: Bot },
  { id: 'settings' as Tab, label: 'Настройки', icon: SettingsIcon },
];
function parentSection(tab: Tab): 'workflow' | 'audit' | 'connections' | 'management' {
  if (tab === 'audit' || tab === 'connections' || tab === 'management') return tab;
  return tab === 'settings' ? 'management' : 'workflow';
}
export function Workspace() {
  const invitation = useInvitationToken();
  const [session, setSession] = useState<Session | null>(null),
    [checking, setChecking] = useState(true),
    [loadError, setLoadError] = useState(''),
    [tab, setTab] = useState<Tab>('workflow'),
    [tourReplay, setTourReplay] = useState(0),
    [generalTourReplay, setGeneralTourReplay] = useState(0),
    [invoices, setInvoices] = useState<Invoice[]>([]),
    [overview, setOverview] = useState<Overview | null>(null),
    [settings, setSettings] = useState<Settings | null>(null),
    [modal, setModal] = useState<'create' | 'import' | null>(null),
    [selected, setSelected] = useState<string | null>(null),
    [toast, setToast] = useState<{ text: string; error: boolean } | null>(null),
    [refreshing, setRefreshing] = useState(false);
  const notify = useCallback((text: string, error = false) => setToast({ text, error }), []);
  useEffect(() => {
    if (!toast) return;
    const timeout = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timeout);
  }, [toast]);
  const acceptSession = useCallback((s: Session) => {
    setCsrf(s.csrf_token);
    setSession(s);
  }, []);
  const checkSession = useCallback(async () => {
    setChecking(true);
    try {
      acceptSession(await api<Session>('/auth/me'));
      setLoadError('');
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setSession(null);
      else setLoadError((e as Error).message);
    } finally {
      setChecking(false);
    }
  }, [acceptSession]);
  useEffect(() => {
    void checkSession();
  }, [checkSession]);
  const refresh = useCallback(async () => {
    if (!session) return;
    setRefreshing(true);
    try {
      const [list, summary, config] = await Promise.all([
        api<{ items: Invoice[] }>('/invoices'),
        api<Overview>('/overview'),
        api<Settings>('/settings'),
      ]);
      setInvoices(list.items);
      setOverview(summary);
      setSettings(config);
      setLoadError('');
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setSession(null);
        setCsrf('');
      } else setLoadError((e as Error).message);
    } finally {
      setRefreshing(false);
    }
  }, [session]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  async function logout() {
    try {
      await post('/auth/logout');
      setSession(null);
      setCsrf('');
      setInvoices([]);
      setOverview(null);
      setSelected(null);
      setTab('workflow');
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  if (checking)
    return (
      <div className="loading">
        <div className="spinner" />
        Открываем рабочее пространство…
      </div>
    );
  if (!session || invitation)
    return loadError ? (
      <div className="loading">
        <p>{loadError}</p>
        <button className="button button-dark" onClick={() => void checkSession()}>
          Повторить
        </button>
      </div>
    ) : (
      <Auth onSession={acceptSession} />
    );
  const done = () => {
    setModal(null);
    void refresh();
    notify(modal === 'import' ? 'Реестр загружен' : 'Счёт добавлен');
  };
  return (
    <div className="workspace">
      <a className="skip-link" href="#workspace-main">
        К содержимому
      </a>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Brand />
        </div>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav className="workspace-nav" aria-label="Разделы кабинета">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              data-tour={`nav-${id}`}
              className={parentSection(tab) === id ? 'active' : ''}
              aria-current={parentSection(tab) === id ? 'page' : undefined}
            >
              <Icon size={17} />
              <span>{label}</span>
              {tab === id && <i />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <WorkspaceAdvice
            key={session.user.id}
            userId={session.user.id}
            onRules={() => setTab('management')}
          />
          <button
            className="workflow-help"
            onClick={() => setGeneralTourReplay((value) => value + 1)}
          >
            Обучение
          </button>
          <WorkspaceProfile
            name={session.user.name}
            company={settings?.company || session.user.company}
            role={session.user.role === 'accountant' ? 'Бухгалтер' : 'Руководитель'}
            onSettings={() => setTab('settings')}
            onLogout={() => void logout()}
          />
        </div>
      </aside>
      <div className="workspace-body">
        <header className="workspace-header workspace-command-header">
          <div>
            <span>РАБОЧЕЕ ПРОСТРАНСТВО</span>
            <ChevronRight size={12} />
            <strong>{[...navigation, ...tools].find((n) => n.id === tab)?.label}</strong>
          </div>
          <nav className="workspace-operations" aria-label="Операции с дебиторкой">
            {tools
              .filter((tool) => !['settings', 'agent'].includes(tool.id))
              .map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  className={tab === id || (id === 'messages' && tab === 'agent') ? 'active' : ''}
                  aria-current={tab === id ? 'page' : undefined}
                  onClick={() => setTab(id)}
                >
                  <Icon size={15} />
                  <span>{label}</span>
                </button>
              ))}
          </nav>
          <div className="workspace-header-actions">
            <button
              className="section-help"
              aria-label="Как работать в разделе"
              onClick={() => {
                setTab(parentSection(tab));
                setTourReplay((value) => value + 1);
              }}
            >
              Помощь по разделу
            </button>
            <span className="server-status">
              <i />
              {loadError ? 'Нет связи' : refreshing ? 'Обновляем…' : 'Данные сохранены'}
            </span>
            <button
              className={`icon-button ${refreshing ? 'refreshing' : ''}`}
              onClick={() => void refresh()}
              aria-label="Обновить данные"
              disabled={refreshing}
            >
              <RefreshCw size={15} />
            </button>
          </div>
        </header>
        <main id="workspace-main" className="workspace-main" data-tour="workspace">
          <WorkflowOnboarding
            userId={session.user.id}
            replayToken={tourReplay}
            generalReplayToken={generalTourReplay}
            onSectionChange={setTab}
            section={parentSection(tab)}
            contextKey={tab}
          />
          {parentSection(tab) === 'management' && (
            <div className="workspace-management-links">
              <button
                className="wf-text-button"
                onClick={() => setTab(tab === 'settings' ? 'management' : 'settings')}
              >
                {tab === 'settings' ? 'Правила и команда' : 'Реквизиты и почта'}
                <ArrowUpRight size={14} />
              </button>
            </div>
          )}
          {tab !== parentSection(tab) && (
            <button className="workspace-back" onClick={() => setTab(parentSection(tab))}>
              <ArrowRight size={14} />
              Вернуться в раздел «{navigation.find((item) => item.id === parentSection(tab))?.label}
              »
            </button>
          )}
          {loadError && (
            <div className="page-error" role="alert">
              <AlertCircle size={16} />
              {loadError}
              <button onClick={() => void refresh()}>Повторить</button>
            </div>
          )}
          {tab === 'workflow' ? (
            <WorkflowDesk
              invoices={invoices}
              totals={overview || undefined}
              onOpenInvoice={setSelected}
              onNavigate={(next) => setTab(next as Tab)}
              onImport={() => setModal('import')}
              onCreate={() => setModal('create')}
              notify={notify}
              refreshKey={refreshing ? 1 : 0}
            />
          ) : tab === 'management' ? (
            <WorkflowManagement notify={notify} onNavigate={(next) => setTab(next as Tab)} />
          ) : tab === 'yandex' ? (
            <YandexDesk invoices={invoices} notify={notify} />
          ) : tab === 'audit' ? (
            <PortfolioDesk
              invoices={invoices}
              onChanged={() => void refresh()}
              notify={notify}
              onOpenInvoice={setSelected}
              onNavigate={setTab}
            />
          ) : tab === 'connections' ? (
            <div data-tour="connections-content">
              <ConnectionsDesk
                invoices={invoices}
                onChanged={() => void refresh()}
                notify={notify}
                onNavigate={(next) => setTab(next)}
              />
            </div>
          ) : tab === 'intelligence' ? (
            <IntelligenceDesk
              invoices={invoices}
              onChanged={() => void refresh()}
              notify={notify}
            />
          ) : tab === 'registry' ? (
            <Registry
              invoices={invoices}
              onCreate={() => setModal('create')}
              onImport={() => setModal('import')}
              onOpen={setSelected}
            />
          ) : tab === 'finance' ? (
            <FinanceDesk invoices={invoices} onChanged={() => void refresh()} notify={notify} />
          ) : tab === 'agent' ? (
            <AgentDesk invoices={invoices} onChanged={() => void refresh()} notify={notify} />
          ) : tab === 'legal' ? (
            <LegalDesk invoices={invoices} onChanged={() => void refresh()} notify={notify} />
          ) : tab === 'messages' ? (
            <Correspondence
              invoices={invoices}
              onOpen={setSelected}
              smtp={settings?.smtp_configured || false}
              onReply={() => setTab('agent')}
            />
          ) : settings ? (
            <SettingsPanel
              settings={settings}
              onSave={async (data) => {
                await patch('/settings', data);
                await refresh();
                notify('Настройки сохранены');
              }}
            />
          ) : (
            <div className="loading">
              <div className="spinner" />
              Загружаем настройки…
            </div>
          )}
          <footer className="workspace-footer">
            <span>Mandato · Деньги возвращаются в дело.</span>
            <span>
              <ShieldCheck size={12} />
              Действия сохраняются в истории
            </span>
          </footer>
        </main>
      </div>
      {modal === 'create' && <CreateInvoice onClose={() => setModal(null)} onDone={done} />}{' '}
      {modal === 'import' && <ImportInvoices onClose={() => setModal(null)} onDone={done} />}{' '}
      {selected && (
        <DebtDrawer
          id={selected}
          onClose={() => setSelected(null)}
          onChange={() => void refresh()}
          notify={notify}
        />
      )}{' '}
      {toast && (
        <div
          className={`toast ${toast.error ? 'error-toast' : ''}`}
          role={toast.error ? 'alert' : 'status'}
        >
          {toast.error ? <AlertCircle size={16} /> : <Check size={16} />}
          <span>{toast.text}</span>
          <button
            className="toast-close"
            aria-label="Закрыть уведомление"
            onClick={() => setToast(null)}
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
function Registry({
  invoices,
  onCreate,
  onImport,
  onOpen,
}: {
  invoices: Invoice[];
  onCreate: () => void;
  onImport: () => void;
  onOpen: (id: string) => void;
}) {
  const [search, setSearch] = useState(''),
    [status, setStatus] = useState('all'),
    [priority, setPriority] = useState('all');
  const filtered = invoices.filter(
    (i) =>
      (status === 'all' || i.status === status) &&
      (priority === 'all' || i.priority === priority) &&
      `${i.company} ${i.number} ${i.inn}`.toLowerCase().includes(search.toLowerCase())
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="page-date">ДЕБИТОРСКАЯ ЗАДОЛЖЕННОСТЬ</span>
          <h1>Счета</h1>
          <p>Счета, остатки и сроки оплаты.</p>
        </div>
        <div className="heading-actions">
          <button className="button button-outline" onClick={onImport}>
            Импорт
            <Upload size={15} />
          </button>
          <button className="button button-dark" onClick={onCreate}>
            Добавить счёт
            <Plus size={15} />
          </button>
        </div>
      </div>
      <div className="registry-toolbar">
        <div className="search-input">
          <Search size={16} />
          <input
            aria-label="Поиск счетов"
            placeholder="Контрагент, номер или ИНН"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button aria-label="Очистить поиск" onClick={() => setSearch('')}>
              <X size={14} />
            </button>
          )}
        </div>
        <div className="filter-controls">
          <select
            aria-label="Статус счёта"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">Все статусы</option>
            {Object.entries(statusNames).map(([key, value]) => (
              <option key={key} value={key}>
                {value}
              </option>
            ))}
          </select>
          <select
            aria-label="Приоритет"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="all">Все приоритеты</option>
            <option value="high">Высокий</option>
            <option value="medium">Средний</option>
            <option value="low">Низкий</option>
          </select>
          <a
            className="icon-button"
            href="/api/export"
            aria-label="Экспорт CSV"
            title="Экспорт CSV"
          >
            <Download size={17} />
          </a>
        </div>
      </div>
      <section className="registry-panel">
        {filtered.length > 0 ? (
          <InvoiceTable invoices={filtered} onOpen={onOpen} />
        ) : invoices.length > 0 ? (
          <div className="empty-state">
            <span className="empty-icon">
              <Search size={24} />
            </span>
            <h3>По этим условиям счетов нет</h3>
            <p>Попробуйте другой запрос или сбросьте фильтры.</p>
            <button
              className="button button-outline"
              onClick={() => {
                setSearch('');
                setStatus('all');
                setPriority('all');
              }}
            >
              Сбросить фильтры
            </button>
          </div>
        ) : (
          <div className="empty-state">
            <span className="empty-icon">
              <Files size={27} />
            </span>
            <h3>Начните с первого счёта</h3>
            <p>
              Добавьте счёт вручную или загрузите CSV. Мы соберём остатки, сроки и следующие шаги в
              один реестр.
            </p>
            <button className="button button-dark" onClick={onImport}>
              Загрузить реестр
              <Upload size={16} />
            </button>
            <button className="template-empty" onClick={downloadTemplate}>
              Скачать шаблон CSV
              <Download size={13} />
            </button>
          </div>
        )}
      </section>
      <div className="registry-count">
        <span>
          Показано {filtered.length} из {invoices.length} счетов
        </span>
        <span>Остаток {money(filtered.reduce((a, b) => a + b.balance, 0))}</span>
      </div>
    </>
  );
}
export function InvoiceTable({
  invoices,
  onOpen,
}: {
  invoices: Invoice[];
  onOpen: (id: string) => void;
}) {
  return (
    <div className="table-scroll">
      <table className="invoice-table">
        <thead>
          <tr>
            <th>КОНТРАГЕНТ / СЧЁТ</th>
            <th>ОСТАТОК</th>
            <th>СРОК ОПЛАТЫ</th>
            <th>СТАТУС</th>
            <th>ПРИОРИТЕТ</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {invoices.map((i) => (
            <tr key={i.id} onClick={() => onOpen(i.id)}>
              <td>
                <span className="table-company">{i.company}</span>
                <button
                  className="invoice-number"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpen(i.id);
                  }}
                >
                  {i.number}
                </button>
              </td>
              <td>
                <strong>{money(i.balance)}</strong>
                {i.paid_amount > 0 && i.balance > 0 && <small>из {money(i.amount)}</small>}
              </td>
              <td>
                {dateText(i.due_on)}
                {i.days_overdue > 0 && i.balance > 0 && (
                  <small className="overdue">{i.days_overdue} дн. просрочки</small>
                )}
              </td>
              <td>
                <span className={`pill ${statusColors[i.status]}`}>{statusNames[i.status]}</span>
                {i.promise_date && i.balance > 0 && <small>до {dateText(i.promise_date)}</small>}
              </td>
              <td>
                <span className={`priority-indicator ${i.priority}`}>
                  <i />
                  {i.priority === 'high'
                    ? 'Высокий'
                    : i.priority === 'medium'
                      ? 'Средний'
                      : 'Низкий'}
                </span>
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Открыть счёт ${i.number}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpen(i.id);
                  }}
                >
                  <ArrowUpRight size={15} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Correspondence({
  invoices,
  onOpen,
  smtp,
  onReply,
}: {
  invoices: Invoice[];
  onOpen: (id: string) => void;
  smtp: boolean;
  onReply: () => void;
}) {
  const active = invoices.filter(
    (i) => i.balance > 0 && i.status !== 'paused' && i.status !== 'disputed'
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="page-date">ДЕЛОВАЯ ПЕРЕПИСКА</span>
          <h1>Переписка с покупателями</h1>
          <p>Откройте счёт, чтобы написать покупателю, или разберите полученный ответ.</p>
        </div>
        <button className="button button-dark" onClick={onReply}>
          Разобрать ответ
          <ArrowRight size={15} />
        </button>
      </div>
      <div className={`mail-connection ${smtp ? 'connected' : ''}`}>
        <Mail size={21} />
        <div>
          <strong>{smtp ? 'Почта подключена' : 'Почта не подключена'}</strong>
          <p>
            {smtp
              ? 'Письма можно отправлять из карточки счёта. Автоматические напоминания включаются в управлении.'
              : 'Вы можете готовить и скачивать письма. Для отправки обратитесь к администратору.'}
          </p>
        </div>
        <ShieldCheck size={20} />
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Кому написать</h2>
            <p>Открытые счета без споров и пауз</p>
          </div>
          <span className="count-badge">{active.length}</span>
        </div>
        {active.length ? (
          <div className="correspondence-list">
            {active.map((i) => (
              <button key={i.id} onClick={() => onOpen(i.id)}>
                <div className="company-avatar">
                  <Mail size={17} />
                </div>
                <span>
                  <strong>{i.company}</strong>
                  <small>
                    {i.number} · {i.email || 'Email не указан'}
                  </small>
                </span>
                <b>{money(i.balance)}</b>
                <span className="letter-action">
                  Открыть счёт
                  <ArrowUpRight size={15} />
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <span className="empty-icon">
              <Mail size={25} />
            </span>
            <h3>Письма начинаются со счёта</h3>
            <p>
              Добавьте задолженность в реестр. В карточке можно подготовить письмо, выбрать тон и
              согласовать отправку.
            </p>
          </div>
        )}
      </section>
    </>
  );
}
function SettingsPanel({
  settings,
  onSave,
}: {
  settings: Settings;
  onSave: (s: Partial<Settings>) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setBusy(true);
    const f = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await onSave({
        ...f,
        annual_rate: Number(f.annual_rate),
        cooldown_days: Number(f.cooldown_days),
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="page-date">ВАША КОМПАНИЯ</span>
          <h1>Работа по вашим правилам.</h1>
          <p>Реквизиты для писем и ограничения, которые учитывает Mandato.</p>
        </div>
      </div>
      <form className="settings-form" onSubmit={save}>
        <section className="settings-panel">
          <div className="settings-intro">
            <h2>Компания и письма</h2>
            <p>Эти данные используются при подготовке текста покупателю.</p>
          </div>
          <div className="form-grid">
            <label className="field full-width">
              Название компании
              <input required name="company" defaultValue={settings.company} maxLength={160} />
            </label>
            <label className="field">
              Имя отправителя
              <input
                required
                name="sender_name"
                defaultValue={settings.sender_name}
                maxLength={100}
              />
            </label>
            <label className="field">
              Email для ответа
              <input type="email" name="reply_to" defaultValue={settings.reply_to} />
            </label>
            <label className="field full-width">
              Реквизиты для оплаты
              <textarea
                rows={4}
                name="bank_details"
                defaultValue={settings.bank_details}
                maxLength={2000}
                placeholder="Расчётный счёт, банк, БИК"
              />
            </label>
          </div>
        </section>
        <section className="settings-panel">
          <div className="settings-intro">
            <h2>Правила работы</h2>
            <p>Ограничения действуют при подготовке и отправке писем.</p>
          </div>
          <div className="form-grid">
            <label className="field">
              Пауза между письмами, дней
              <input
                type="number"
                required
                min={1}
                max={30}
                name="cooldown_days"
                defaultValue={settings.cooldown_days}
              />
            </label>
            <label className="field">
              Ставка по кредиту, % годовых
              <input
                type="number"
                required
                min={0}
                max={100}
                step="0.1"
                name="annual_rate"
                defaultValue={settings.annual_rate}
              />
            </label>
            <p className="form-note full-width">
              Повторное напоминание не уйдёт раньше указанного срока. Оплаченные, спорные и
              поставленные на паузу счета исключаются из отправки.
            </p>
          </div>
        </section>
        <section className="settings-panel connection-settings">
          <div>
            <Mail size={20} />
            <span>
              <strong>Почта компании</strong>
              <small>
                {settings.smtp_configured
                  ? 'Подключена. Отправка доступна.'
                  : 'Не подключена. Подготовка и скачивание писем доступны.'}
              </small>
            </span>
            <span className={`pill ${settings.smtp_configured ? 'green' : 'gray'}`}>
              {settings.smtp_configured ? 'Подключена' : 'Не подключена'}
            </span>
          </div>
          <div>
            <ShieldCheck size={20} />
            <span>
              <strong>Подготовка текста</strong>
              <small>
                {settings.llm_configured
                  ? 'ИИ помогает с формулировками. Суммы подставляются из счёта.'
                  : 'Проверенные формулировки с реквизитами вашего счёта.'}
              </small>
            </span>
            <span className="pill green">Доступна</span>
          </div>
        </section>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="settings-save">
          <span>
            <ShieldCheck size={14} />
            Изменения применяются к новым письмам
          </span>
          <button type="submit" className="button button-dark" disabled={busy}>
            {busy ? 'Сохраняем…' : 'Сохранить настройки'}
            <Check size={17} />
          </button>
        </div>
      </form>
    </>
  );
}
