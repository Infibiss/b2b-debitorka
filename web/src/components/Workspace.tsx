import { t } from '../i18n';
import { CaseConversation } from './CaseConversation';
import { ContextHelp } from './ContextHelp';
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
  X,
  Wallet,
  AlertCircle,
  TrendingUp,
  Bot,
  Scale,
  ClipboardCheck,
} from 'lucide-react';
import { Brand } from './Brand';
import { WorkspaceProfile, WorkspaceAdvice } from './WorkspaceProfile';
import { Auth } from './Auth';
import { useInvitationToken } from './useInvitationToken';
import { WorkflowDesk, WorkflowManagement } from './WorkflowDesk';
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
import { navigate, useRouteField, WorkContext } from '../navigation';
import { clearFormDrafts, hasFormDrafts, useFormDraft } from './useFormDraft';
import { DocumentsDesk } from './DocumentsDesk';
import { MailSetup } from './MailSetup';
import WorkspaceDataSettings from './WorkspaceDataSettings';
import { YandexDesk } from './YandexDesk';
import { LanguageSwitch } from './LanguageSwitch';
import { RecoveryHome } from './recovery/RecoveryHome';
import { DebtorsDesk } from './recovery/DebtorsDesk';
import { DebtorCard } from './recovery/DebtorCard';
import {
  AutomationForm,
  FinancingDesk,
  OrganizationForm,
  ReportsDesk,
  TemplatesDesk,
} from './recovery/RecoverySettings';
import type { Meta, Stage } from './recovery/types';
import './recovery/recovery.css';
type Tab =
  | 'home'
  | 'debtors'
  | 'finance'
  | 'financing'
  | 'templates'
  | 'reports'
  | 'settings'
  | 'workflow'
  | 'management'
  | 'yandex'
  | 'audit'
  | 'connections'
  | 'intelligence'
  | 'registry'
  | 'agent'
  | 'legal'
  | 'messages';
type SettingsTab = 'organization' | 'automation' | 'connections' | 'team' | 'mail';
const navigation = [
  { id: 'home' as Tab, label: t('Главная'), icon: LayoutDashboard },
  { id: 'debtors' as Tab, label: t('Должники'), icon: Scale },
  { id: 'finance' as Tab, label: t('Оплаты'), icon: Wallet },
  { id: 'financing' as Tab, label: t('Финансирование'), icon: TrendingUp },
  { id: 'templates' as Tab, label: t('Шаблоны'), icon: Files },
  { id: 'reports' as Tab, label: t('Отчёты'), icon: ClipboardCheck },
  { id: 'settings' as Tab, label: t('Настройки'), icon: SettingsIcon },
];
/** Detailed tools, reachable from the sidebar without crowding daily work. */
const tools = [
  { id: 'workflow' as Tab, label: t('Работа'), icon: LayoutDashboard },
  { id: 'audit' as Tab, label: t('Аудит'), icon: ClipboardCheck },
  { id: 'registry' as Tab, label: t('Счета'), icon: Files },
  { id: 'messages' as Tab, label: t('Переписка'), icon: Mail },
  { id: 'yandex' as Tab, label: t('Документы'), icon: Bot },
  { id: 'intelligence' as Tab, label: t('Прогноз и условия'), icon: TrendingUp },
  { id: 'legal' as Tab, label: t('Претензии и суд'), icon: Scale },
  { id: 'agent' as Tab, label: t('Разбор ответов'), icon: Bot },
];
const settingsTabs: [SettingsTab, string][] = [
  ['organization', t('Компания')],
  ['automation', t('Автоматизация')],
  ['connections', t('Подключения')],
  ['team', t('Команда')],
  ['mail', t('Почта')],
];
export function Workspace() {
  const invitation = useInvitationToken();
  const [routeTab, setTab] = useRouteField<Tab>('section', 'home');
  const tab = [...navigation, ...tools, { id: 'management' }, { id: 'connections' }].some(
    (item) => item.id === routeTab
  )
    ? routeTab
    : 'home';
  const [debtorId, setDebtorId] = useRouteField<string | null>('debtor', null);
  const [stage] = useRouteField<Stage>('stage', 'pretrial');
  const [settingsTab] = useRouteField<SettingsTab>('settingsTab', 'organization');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selected, setSelected] = useRouteField<string | null>('invoice', null);
  const [contextInvoice] = useRouteField<string>('context', '');
  const [contextCase] = useRouteField<string>('case', '');
  const [contextIds, setContextIds] = useState<string[]>([]);
  const [returnCase, setReturnCase] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);
  const [intent] = useRouteField<string>('intent', '');
  const [session, setSession] = useState<Session | null>(null),
    [checking, setChecking] = useState(true),
    [loadError, setLoadError] = useState(''),
    [invoices, setInvoices] = useState<Invoice[]>([]),
    [overview, setOverview] = useState<Overview | null>(null),
    [settings, setSettings] = useState<Settings | null>(null),
    [modal, setModal] = useState<'create' | 'import' | null>(null),
    [toast, setToast] = useState<{ text: string; error: boolean } | null>(null),
    [refreshing, setRefreshing] = useState(false);
  useEffect(() => {
    if (!session || !intent) return;
    if (intent === 'import') setModal('import');
    if (intent === 'service') {
      setHelpOpen(true);
    }
    navigate({ intent: null }, true);
  }, [session, intent]);
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
      setMeta(await api<Meta>('/recovery/meta'));
      setRefreshKey((value) => value + 1);
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
  useEffect(() => {
    let alive = true;
    setContextIds([]);
    setReturnCase('');
    if (session && contextInvoice)
      void api<{ items: { id: string; invoice_ids: string[] }[] }>('/workflow/cases')
        .then((result) => {
          const item = result.items.find((c) => c.invoice_ids.includes(contextInvoice));
          if (alive && item) {
            setContextIds(item.invoice_ids);
            setReturnCase(item.id);
          }
        })
        .catch(() => {});
    return () => {
      alive = false;
    };
  }, [session, contextCase, contextInvoice]);
  async function logout() {
    if (
      hasFormDrafts() &&
      !window.confirm(t('В этой вкладке есть черновики. При выходе они будут удалены. Выйти?'))
    )
      return;
    try {
      await post('/auth/logout');
      clearFormDrafts();
      setSession(null);
      setCsrf('');
      setInvoices([]);
      setOverview(null);
      navigate({
        section: null,
        mode: 'login',
        invoice: null,
        case: null,
        caseTab: null,
        context: null,
        legal: null,
        legalTab: null,
        financeTab: null,
        source: null,
        documentsTab: null,
        auditInvoice: null,
        factsStep: null,
        party: null,
        returnTo: null,
        agentProposal: null,
        proposal: null,
        sourceAgent: null,
        workSearch: null,
        workQueue: null,
        workView: null,
      });
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  if (checking)
    return (
      <div className="loading">
        <div className="spinner" />
        {t('Открываем рабочее пространство…')}
      </div>
    );
  if (!session || invitation || new URLSearchParams(location.hash.slice(1)).has('reset'))
    return loadError ? (
      <div className="loading">
        <p>{loadError}</p>
        <button className="button button-dark" onClick={() => void checkSession()}>
          {t('Повторить')}
        </button>
      </div>
    ) : (
      <Auth onSession={acceptSession} />
    );
  const done = () => {
    setModal(null);
    void refresh();
    notify(modal === 'import' ? t('Реестр загружен') : t('Счёт добавлен'));
  };
  function goTo(target: string) {
    const [section, detail] = target.split(':');
    if (section === 'debtors' && detail === 'import') {
      navigate({ section: 'debtors', stage: null, debtor: null });
      setModal('import');
    } else if (section === 'debtors') navigate({ section, stage: detail || null, debtor: null });
    else navigate({ section, settingsTab: detail || null, debtor: null });
  }
  return (
    <WorkContext.Provider
      value={{ userId: session.user.id, invoiceId: contextInvoice, caseId: contextCase }}
    >
      <div className="workspace">
        <a className="skip-link" href="#workspace-main">
          {t('К содержимому')}
        </a>
        <aside className="sidebar">
          <div className="sidebar-brand">
            <Brand />
          </div>
          <nav className="workspace-nav" aria-label={t('Разделы кабинета')}>
            {navigation.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => {
                  navigate({ section: id, debtor: null });
                }}
                data-tour={`nav-${id}`}
                className={tab === id ? 'active' : ''}
                aria-current={tab === id ? 'page' : undefined}
              >
                <Icon size={17} />
                <span>{label}</span>
                {tab === id && <i />}
              </button>
            ))}
          </nav>
          <details className="workspace-more">
            <summary>{t('Инструменты')}</summary>
            <nav className="workspace-nav" aria-label={t('Инструменты')}>
              {tools.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={tab === id ? 'active' : ''}
                  aria-current={tab === id ? 'page' : undefined}
                >
                  <Icon size={17} />
                  <span>{label}</span>
                </button>
              ))}
            </nav>
          </details>
          <div className="sidebar-bottom">
            <WorkspaceAdvice
              key={session.user.id}
              userId={session.user.id}
              onRules={() => goTo('settings:automation')}
            />
            <WorkspaceProfile
              name={session.user.name}
              company={settings?.company || session.user.company}
              role={session.user.role === 'accountant' ? t('Бухгалтер') : t('Руководитель')}
              onSettings={() => setTab('settings')}
              onLogout={() => void logout()}
            />
          </div>
        </aside>
        <div className="workspace-body">
          <header className="workspace-header workspace-command-header">
            <div className="workspace-header-actions">
              <LanguageSwitch />
              <span className="server-status">
                <i />
                {loadError ? t('Нет связи') : refreshing ? t('Обновляем…') : t('Данные обновлены')}
              </span>
              <button
                className={`icon-button ${refreshing ? 'refreshing' : ''}`}
                onClick={() => void refresh()}
                aria-label={t('Обновить данные')}
                disabled={refreshing}
              >
                <RefreshCw size={15} />
              </button>
            </div>
          </header>
          <main id="workspace-main" className="workspace-main" data-tour="workspace">
            {tab !== 'workflow' &&
              tab !== 'legal' &&
              contextInvoice &&
              invoices.some((i) => i.id === contextInvoice) && (
                <div className="work-context-bar">
                  {tab !== 'messages' && (
                    <label>
                      {t('Работаем со счётом')}
                      <select
                        aria-label={t('Текущая задолженность')}
                        value={contextInvoice}
                        onChange={(e) =>
                          navigate({
                            context: e.target.value,
                            case: returnCase || contextCase || null,
                          })
                        }
                      >
                        {invoices
                          .filter((i) => !contextIds.length || contextIds.includes(i.id))
                          .map((i) => (
                            <option key={i.id} value={i.id}>
                              {i.company} · {i.number}
                            </option>
                          ))}
                      </select>
                    </label>
                  )}
                  <button
                    className="wf-text-button"
                    onClick={() =>
                      navigate({
                        section: 'workflow',
                        case: returnCase || contextCase || `invoice:${contextInvoice}`,
                      })
                    }
                  >
                    {t('Вернуться к делу')}
                  </button>
                  <button
                    className="wf-text-button"
                    onClick={() => navigate({ context: null, case: null })}
                  >
                    {t('Все задолженности')}
                  </button>
                </div>
              )}
            {loadError && (
              <div className="page-error" role="alert">
                <AlertCircle size={16} />
                {loadError}
                <button onClick={() => void refresh()}>{t('Повторить')}</button>
              </div>
            )}
            {debtorId && meta ? (
              <DebtorCard
                key={debtorId}
                id={debtorId}
                meta={meta}
                isManager={session.user.role !== 'accountant'}
                onBack={() => setDebtorId(null)}
                onChanged={() => void refresh()}
                onEvidence={(id) => navigate({ debtor: null, section: 'audit', auditInvoice: id })}
                notify={notify}
              />
            ) : tab === 'home' ? (
              <RecoveryHome
                onOpenDebtor={setDebtorId}
                onGo={goTo}
                onImport={() => setModal('import')}
                refreshKey={refreshKey}
                notify={notify}
              />
            ) : tab === 'debtors' ? (
              <DebtorsDesk
                initialStage={stage}
                onOpen={setDebtorId}
                onImport={() => setModal('import')}
                onCreate={() => setModal('create')}
                refreshKey={refreshKey}
                notify={notify}
              />
            ) : tab === 'financing' ? (
              <FinancingDesk notify={notify} isManager={session.user.role !== 'accountant'} />
            ) : tab === 'templates' && meta ? (
              <TemplatesDesk meta={meta} notify={notify} />
            ) : tab === 'reports' ? (
              <ReportsDesk notify={notify} />
            ) : tab === 'settings' && settingsTab !== 'mail' ? (
              <div className="rc-page">
                <header className="rc-head">
                  <div>
                    <h1>{t('Настройки')}</h1>
                  </div>
                </header>
                <SettingsNav current={settingsTab} />
                {settingsTab === 'organization' ? (
                  <OrganizationForm notify={notify} onSaved={() => void refresh()} />
                ) : settingsTab === 'automation' ? (
                  <AutomationForm notify={notify} onSaved={() => void refresh()} />
                ) : settingsTab === 'connections' ? (
                  <ConnectionsDesk
                    invoices={invoices}
                    onChanged={() => void refresh()}
                    notify={notify}
                    onNavigate={(next) => setTab(next)}
                  />
                ) : (
                  <WorkflowManagement notify={notify} onNavigate={(next) => setTab(next as Tab)} />
                )}
              </div>
            ) : tab === 'workflow' ? (
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
              <DocumentsDesk invoices={invoices} notify={notify} onChanged={() => void refresh()} />
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
                key={contextInvoice}
                invoices={invoices}
                onChanged={() => void refresh()}
                notify={notify}
              />
            ) : tab === 'registry' ? (
              <Registry
                invoices={
                  contextIds.length ? invoices.filter((i) => contextIds.includes(i.id)) : invoices
                }
                onCreate={() => setModal('create')}
                onImport={() => setModal('import')}
                onOpen={setSelected}
              />
            ) : tab === 'finance' ? (
              <FinanceDesk
                key={contextInvoice}
                invoices={invoices}
                onChanged={() => void refresh()}
                notify={notify}
              />
            ) : tab === 'agent' ? (
              <AgentDesk
                key={contextInvoice}
                invoices={invoices}
                onChanged={() => void refresh()}
                notify={notify}
              />
            ) : tab === 'legal' ? (
              <LegalDesk invoices={invoices} onChanged={() => void refresh()} notify={notify} />
            ) : tab === 'messages' ? (
              <Correspondence
                invoices={
                  contextInvoice ? invoices.filter((i) => i.id === contextInvoice) : invoices
                }
                onOpen={setSelected}
                smtp={settings?.smtp_configured || false}
                onReply={() => setTab('agent')}
                notify={notify}
              />
            ) : settings ? (
              <div className="rc-page">
                <SettingsNav current="mail" />
                <SettingsPanel
                  settings={settings}
                  onSave={async (data) => {
                    await patch('/settings', data);
                    await refresh();
                    notify(t('Настройки сохранены'));
                  }}
                />
              </div>
            ) : (
              <div className="loading">
                <div className="spinner" />
                {t('Загружаем настройки…')}
              </div>
            )}
          </main>
        </div>
        {helpOpen && <ContextHelp onClose={() => setHelpOpen(false)} />}
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
              aria-label={t('Закрыть уведомление')}
              onClick={() => setToast(null)}
            >
              <X size={14} />
            </button>
          </div>
        )}
      </div>
    </WorkContext.Provider>
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
          <h1>{t('Счета')}</h1>
          <p>{t('Счета, остатки и сроки оплаты.')}</p>
        </div>
        <div className="heading-actions">
          <button className="button button-outline" onClick={onImport}>
            {t('Импорт')}
            <Upload size={15} />
          </button>
          <button className="button button-dark" onClick={onCreate}>
            {t('Добавить счёт')}
            <Plus size={15} />
          </button>
        </div>
      </div>
      <div className="registry-toolbar">
        <div className="search-input">
          <Search size={16} />
          <input
            aria-label={t('Поиск счетов')}
            placeholder={t('Контрагент, номер или ИНН')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button aria-label={t('Очистить поиск')} onClick={() => setSearch('')}>
              <X size={14} />
            </button>
          )}
        </div>
        <div className="filter-controls">
          <select
            aria-label={t('Статус счёта')}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">{t('Все статусы')}</option>
            {Object.entries(statusNames).map(([key, value]) => (
              <option key={key} value={key}>
                {value}
              </option>
            ))}
          </select>
          <select
            aria-label={t('Приоритет')}
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="all">{t('Все приоритеты')}</option>
            <option value="high">{t('Высокий')}</option>
            <option value="medium">{t('Средний')}</option>
            <option value="low">{t('Низкий')}</option>
          </select>
          <a
            className="icon-button"
            href="/api/export"
            aria-label={t('Экспорт CSV')}
            title={t('Экспорт CSV')}
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
            <h3>{t('По этим условиям счетов нет')}</h3>
            <p>{t('Попробуйте другой запрос или сбросьте фильтры.')}</p>
            <button
              className="button button-outline"
              onClick={() => {
                setSearch('');
                setStatus('all');
                setPriority('all');
              }}
            >
              {t('Сбросить фильтры')}
            </button>
          </div>
        ) : (
          <div className="empty-state">
            <span className="empty-icon">
              <Files size={27} />
            </span>
            <h3>{t('Начните с первого счёта')}</h3>
            <p>
              {t(
                'Добавьте счёт вручную или загрузите CSV. Мы соберём остатки, сроки и следующие шаги в один реестр.'
              )}
            </p>
            <button className="button button-dark" onClick={onImport}>
              {t('Загрузить реестр')}
              <Upload size={16} />
            </button>
            <button className="template-empty" onClick={downloadTemplate}>
              {t('Скачать шаблон CSV')}
              <Download size={13} />
            </button>
          </div>
        )}
      </section>
      <div className="registry-count">
        <span>
          {t('Показано')} {filtered.length} {t('из')} {invoices.length} {t('счетов')}
        </span>
        <span>
          {t('Остаток')} {money(filtered.reduce((a, b) => a + b.balance, 0))}
        </span>
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
            <th>{t('Контрагент / счёт')}</th>
            <th>{t('Остаток')}</th>
            <th>{t('Срок оплаты')}</th>
            <th>{t('Статус')}</th>
            <th>{t('Приоритет')}</th>
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
                {i.paid_amount > 0 && i.balance > 0 && (
                  <small>
                    {t('из')} {money(i.amount)}
                  </small>
                )}
              </td>
              <td>
                {dateText(i.due_on)}
                {i.days_overdue > 0 && i.balance > 0 && (
                  <small className="overdue">
                    {i.days_overdue} {t('дн. просрочки')}
                  </small>
                )}
              </td>
              <td>
                <span className={`pill ${statusColors[i.status]}`}>{statusNames[i.status]}</span>
                {i.promise_date && i.balance > 0 && (
                  <small>
                    {t('до')} {dateText(i.promise_date)}
                  </small>
                )}
              </td>
              <td>
                <span className={`priority-indicator ${i.priority}`}>
                  <i />
                  {i.priority === 'high'
                    ? t('Высокий')
                    : i.priority === 'medium'
                      ? t('Средний')
                      : t('Низкий')}
                </span>
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={t('Открыть счёт {0}', [i.number])}
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
  notify,
}: {
  invoices: Invoice[];
  onOpen: (id: string) => void;
  smtp: boolean;
  onReply: () => void;
  notify: (text: string, error?: boolean) => void;
}) {
  const [mode, setMode] = useRouteField<'history' | 'calls'>('messagesTab', 'history');
  const active = invoices.filter(
    (i) => i.balance > 0 && i.status !== 'paused' && i.status !== 'disputed'
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{mode === 'calls' ? t('Звонки покупателям') : t('Переписка с покупателями')}</h1>
          <p>
            {mode === 'calls'
              ? t('Свяжитесь с представителем контрагента по выбранному счёту.')
              : t('Откройте счёт, чтобы написать покупателю, или разберите полученный ответ.')}
          </p>
        </div>
        {mode !== 'calls' && (
          <button className="button button-dark" onClick={onReply}>
            {t('Разобрать ответ')}
            <ArrowRight size={15} />
          </button>
        )}
      </div>
      <div className="ops-tabs" aria-label={t('Общение с контрагентами')}>
        <button type="button" aria-pressed={mode !== 'calls'} onClick={() => setMode('history')}>
          {t('История и письма')}
        </button>
        <button type="button" aria-pressed={mode === 'calls'} onClick={() => setMode('calls')}>
          {t('Звонки')}
        </button>
      </div>
      {mode === 'calls' ? (
        <YandexDesk mode="voice" invoices={invoices} notify={notify} embedded />
      ) : (
        <>
          <div className={`mail-connection ${smtp ? 'connected' : 'is-warning'}`}>
            <Mail size={21} />
            <div>
              <strong>{smtp ? t('Почта подключена') : t('Почта не подключена')}</strong>
              <p>
                {smtp
                  ? t(
                      'Письма можно отправлять из карточки счёта. Автоматические напоминания включаются в управлении.'
                    )
                  : t(
                      'Вы можете готовить и скачивать письма. Для отправки обратитесь к администратору.'
                    )}
              </p>
            </div>
            {smtp ? <ShieldCheck size={20} /> : <AlertCircle size={20} />}
            {!smtp && (
              <button
                className="button button-outline"
                onClick={() => navigate({ section: 'settings' })}
              >
                {t('Подключить почту')}
              </button>
            )}
          </div>
          <CaseConversation invoices={invoices} onOpen={onOpen} />
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>{t('Кому написать')}</h2>
                <p>{t('Открытые счета без споров и пауз')}</p>
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
                        {i.number} · {i.email || t('Email не указан')}
                      </small>
                    </span>
                    <b>{money(i.balance)}</b>
                    <span className="letter-action">
                      {t('Открыть счёт')}
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
                <h3>{t('Письма начинаются со счёта')}</h3>
                <p>
                  {t(
                    'Добавьте задолженность в реестр. В карточке можно подготовить письмо, выбрать тон и согласовать отправку.'
                  )}
                </p>
              </div>
            )}
          </section>
        </>
      )}
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
  const draft = useFormDraft('settings');
  const [mailLoaded, setMailLoaded] = useState(false);
  const onMailLoaded = useCallback(() => setMailLoaded(true), []);
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
      draft.clear();
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
          <h1>{t('Настройки')}</h1>
          <p>{t('Реквизиты, почта и данные организации.')}</p>
        </div>
      </div>
      <form ref={draft.ref} className="settings-form" onSubmit={save}>
        {draft.status && (
          <p className="draft-status" role="status">
            {draft.status}
          </p>
        )}
        <section className="settings-panel">
          <div className="settings-intro">
            <h2>{t('Компания и письма')}</h2>
            <p>{t('Эти данные используются при подготовке текста покупателю.')}</p>
          </div>
          <div className="form-grid">
            <label className="field full-width">
              {t('Название компании')}
              <input required name="company" defaultValue={settings.company} maxLength={160} />
            </label>
            <label className="field">
              {t('Имя отправителя')}
              <input
                required
                name="sender_name"
                defaultValue={settings.sender_name}
                maxLength={100}
              />
            </label>
            <label className="field">
              {t('Email для ответа')}
              <input type="email" name="reply_to" defaultValue={settings.reply_to} />
            </label>
            <label className="field full-width">
              {t('Реквизиты для оплаты')}
              <textarea
                rows={4}
                name="bank_details"
                defaultValue={settings.bank_details}
                maxLength={2000}
                placeholder={t('Расчётный счёт, банк, БИК')}
              />
            </label>
          </div>
        </section>
        <section className="settings-panel">
          <div className="settings-intro">
            <h2>{t('Правила работы')}</h2>
            <p>{t('Ограничения действуют при подготовке и отправке писем.')}</p>
          </div>
          <div className="form-grid">
            <label className="field">
              {t('Пауза между письмами, дней')}
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
              {t('Ставка по кредиту, % годовых')}
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
              {t(
                'Повторное напоминание не уйдёт раньше указанного срока. Оплаченные, спорные и поставленные на паузу счета исключаются из отправки.'
              )}
            </p>
          </div>
        </section>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="settings-save">
          <button type="submit" className="button button-dark" disabled={busy}>
            {busy ? t('Сохраняем…') : t('Сохранить настройки')}
            <Check size={17} />
          </button>
        </div>
      </form>
      <MailSetup onLoaded={onMailLoaded} />
      <WorkspaceDataSettings layoutReady={mailLoaded} />
    </>
  );
}

function SettingsNav({ current }: { current: SettingsTab }) {
  return (
    <nav className="rc-tabs rc-settings-tabs" aria-label={t('Разделы настроек')}>
      {settingsTabs.map(([key, label]) => (
        <button
          key={key}
          className={current === key ? 'active' : ''}
          aria-current={current === key ? 'page' : undefined}
          onClick={() => navigate({ section: 'settings', settingsTab: key })}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
