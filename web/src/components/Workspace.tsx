import { t } from '../i18n';
import { ContextHelp } from './ContextHelp';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  LayoutDashboard,
  Files,
  Mail,
  Settings as SettingsIcon,
  Check,
  RefreshCw,
  X,
  Wallet,
  AlertCircle,
  TrendingUp,
  Scale,
  ClipboardCheck,
} from 'lucide-react';
import { Brand } from './Brand';
import { WorkspaceProfile, WorkspaceAdvice } from './WorkspaceProfile';
import { Auth } from './Auth';
import { useInvitationToken } from './useInvitationToken';
import { InboxStatus, TeamSettings } from './TeamSettings';
import { CreateInvoice, ImportInvoices } from './InvoiceForms';
import { DebtDrawer } from './DebtDrawer';
import { FinanceDesk } from './FinanceDesk';
import { AgentDesk } from './AgentDesk';
import { ConnectionsDesk } from './ConnectionsDesk';
import {
  api,
  post,
  patch,
  setCsrf,
  type Session,
  type Invoice,
  type Settings,
  ApiError,
} from '../api';
import './workspace.css';
import { navigate, useRouteField, WorkContext } from '../navigation';
import { clearFormDrafts, hasFormDrafts, useFormDraft } from './useFormDraft';
import { MailSetup } from './MailSetup';
import WorkspaceDataSettings from './WorkspaceDataSettings';
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
  | 'agent';
type SettingsTab = 'organization' | 'automation' | 'connections' | 'team' | 'mail';
const navigation = [
  { id: 'home' as Tab, label: t('Главная'), icon: LayoutDashboard },
  { id: 'debtors' as Tab, label: t('Должники'), icon: Scale },
  { id: 'agent' as Tab, label: t('Ответы должников'), icon: Mail },
  { id: 'finance' as Tab, label: t('Оплаты'), icon: Wallet },
  { id: 'financing' as Tab, label: t('Финансирование'), icon: TrendingUp },
  { id: 'templates' as Tab, label: t('Шаблоны'), icon: Files },
  { id: 'reports' as Tab, label: t('Отчёты'), icon: ClipboardCheck },
  { id: 'settings' as Tab, label: t('Настройки'), icon: SettingsIcon },
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
  const tab = navigation.some((item) => item.id === routeTab) ? routeTab : 'home';
  const [debtorId, setDebtorId] = useRouteField<string | null>('debtor', null);
  const [stage] = useRouteField<Stage>('stage', 'pretrial');
  const [settingsTab] = useRouteField<SettingsTab>('settingsTab', 'organization');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selected, setSelected] = useRouteField<string | null>('invoice', null);
  const [contextInvoice] = useRouteField<string>('context', '');
  const [contextCase] = useRouteField<string>('case', '');
  const [helpOpen, setHelpOpen] = useState(false);
  const [intent] = useRouteField<string>('intent', '');
  const [session, setSession] = useState<Session | null>(null),
    [checking, setChecking] = useState(true),
    [loadError, setLoadError] = useState(''),
    [invoices, setInvoices] = useState<Invoice[]>([]),
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
      const [list, config] = await Promise.all([
        api<{ items: Invoice[] }>('/invoices'),
        api<Settings>('/settings'),
      ]);
      setInvoices(list.items);
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
                onOpenInvoice={setSelected}
                onReply={(id) => navigate({ debtor: null, section: 'agent', context: id })}
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
                  <TeamSettings notify={notify} />
                )}
              </div>
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
            ) : settings ? (
              <div className="rc-page">
                <SettingsNav current="mail" />
                <SettingsPanel
                  settings={settings}
                  notify={notify}
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
function SettingsPanel({
  settings,
  onSave,
  notify,
}: {
  settings: Settings;
  onSave: (s: Partial<Settings>) => Promise<void>;
  notify: (text: string, error?: boolean) => void;
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
              {t('Почта для ответа')}
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
      <InboxStatus notify={notify} />
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
