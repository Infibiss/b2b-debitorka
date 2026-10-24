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
  LogOut,
  ArrowRight,
  Clock3,
  Check,
  ShieldCheck,
  RefreshCw,
  ChevronRight,
  X,
  FileText,
  Wallet,
  AlertCircle,
  CircleCheck,
  TrendingUp,
  Bot,
  Scale,
} from 'lucide-react';
import { Brand } from './Brand';
import { Auth } from './Auth';
import { CreateInvoice, ImportInvoices, downloadTemplate } from './InvoiceForms';
import { DebtDrawer, statusNames, statusColors } from './DebtDrawer';
import { FinanceDesk } from './FinanceDesk';
import { AgentDesk } from './AgentDesk';
import LegalDesk from './LegalDesk';
import {
  api,
  post,
  patch,
  setCsrf,
  money,
  dateText,
  today,
  type Session,
  type Invoice,
  type Overview,
  type Settings,
  ApiError,
} from '../api';
import './workspace.css';
type Tab = 'overview' | 'registry' | 'finance' | 'agent' | 'legal' | 'messages' | 'settings';
const navigation = [
  { id: 'overview' as Tab, label: 'Обзор', icon: LayoutDashboard },
  { id: 'registry' as Tab, label: 'Реестр', icon: Files },
  { id: 'finance' as Tab, label: 'Финансы', icon: Wallet },
  { id: 'agent' as Tab, label: 'Агент', icon: Bot },
  { id: 'legal' as Tab, label: 'Дела', icon: Scale },
  { id: 'messages' as Tab, label: 'Письма', icon: Mail },
  { id: 'settings' as Tab, label: 'Настройки', icon: SettingsIcon },
];
export function Workspace() {
  const [session, setSession] = useState<Session | null>(null),
    [checking, setChecking] = useState(true),
    [loadError, setLoadError] = useState(''),
    [tab, setTab] = useState<Tab>('overview'),
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
      setTab('overview');
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
  if (!session)
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
  const overdue = invoices.filter((i) => i.days_overdue > 0 && i.balance > 0),
    high = invoices.filter((i) => i.priority === 'high' && i.balance > 0);
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
        <div className="company-switch">
          <span>
            {session.user.company
              .replace(/ООО\s*[«"]?/, '')
              .slice(0, 1)
              .toUpperCase()}
          </span>
          <div>
            <strong>{settings?.company || session.user.company}</strong>
            <small>Управление дебиторкой</small>
          </div>
        </div>
        <nav className="workspace-nav" aria-label="Разделы кабинета">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={tab === id ? 'active' : ''}
              aria-current={tab === id ? 'page' : undefined}
            >
              <Icon size={17} />
              <span>{label}</span>
              {id === 'registry' && invoices.length > 0 && <small>{invoices.length}</small>}
              {tab === id && <i />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-help">
            <ShieldCheck size={20} />
            <strong>Всё под вашим контролем</strong>
            <p>
              Письма уходят только
              <br />
              после согласования.
            </p>
            <button onClick={() => setTab('settings')}>
              Правила работы
              <ArrowUpRight size={13} />
            </button>
          </div>
          <div className="user-block">
            <div className="user-avatar">{session.user.name.slice(0, 1).toUpperCase()}</div>
            <span>
              <strong>{session.user.name}</strong>
              <small>Администратор</small>
            </span>
            <button
              className="icon-button"
              title="Выйти"
              aria-label="Выйти"
              onClick={() => void logout()}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="workspace-header">
          <div>
            <span>РАБОЧЕЕ ПРОСТРАНСТВО</span>
            <ChevronRight size={12} />
            <strong>{navigation.find((n) => n.id === tab)?.label}</strong>
          </div>
          <div>
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
        <main id="workspace-main" className="workspace-main">
          {loadError && (
            <div className="page-error" role="alert">
              <AlertCircle size={16} />
              {loadError}
              <button onClick={() => void refresh()}>Повторить</button>
            </div>
          )}
          {tab === 'overview' ? (
            <>
              <div className="page-heading">
                <div>
                  <span className="page-date">
                    {new Date().toLocaleDateString('ru-RU', {
                      weekday: 'long',
                      day: 'numeric',
                      month: 'long',
                      timeZone: 'Europe/Moscow',
                    })}
                  </span>
                  <h1>Деньги в движении.</h1>
                  <p>
                    {invoices.length > 0
                      ? 'Ваш портфель, договорённости и следующие шаги.'
                      : 'Начните с первого счёта — остальное соберётся в понятный процесс.'}
                  </p>
                </div>
                <button className="button button-dark" onClick={() => setModal('create')}>
                  Добавить счёт
                  <Plus size={16} />
                </button>
              </div>
              <div className="metric-grid">
                <Metric
                  label="ОСТАЛОСЬ К ОПЛАТЕ"
                  value={overview?.total_outstanding || 0}
                  note={`${invoices.filter((i) => i.balance > 0).length} открытых счетов`}
                  icon={<Wallet size={17} />}
                  featured
                />
                <Metric
                  label="ПРОСРОЧЕНО"
                  value={overview?.overdue_amount || 0}
                  note={`${overdue.length} счетов · ${money(Math.round(((overview?.overdue_amount || 0) * (settings?.annual_rate || 0)) / 100 / 365))} в день ожидания`}
                  icon={<Clock3 size={17} />}
                />
                <Metric
                  label="ОБЕЩАНО К ОПЛАТЕ"
                  value={overview?.promised_amount || 0}
                  note="По зафиксированным договорённостям"
                  icon={<Check size={17} />}
                />
                <Metric
                  label="ПОСТУПИЛО"
                  value={overview?.collected_amount || 0}
                  note="По зарегистрированным платежам"
                  icon={<TrendingUp size={17} />}
                />
              </div>
              {invoices.length === 0 ? (
                <div className="onboarding-card">
                  <div>
                    <span className="onboarding-kicker">ПЕРВЫЙ ШАГ — САМЫЙ ПРОСТОЙ</span>
                    <h2>
                      Ваша дебиторка.
                      <br />В одном пространстве.
                    </h2>
                    <p>
                      Загрузите реестр из учётной системы
                      <br />
                      или добавьте первый счёт вручную.
                    </p>
                    <div>
                      <button className="button button-dark" onClick={() => setModal('import')}>
                        Загрузить реестр
                        <Upload size={16} />
                      </button>
                      <button className="text-link" onClick={downloadTemplate}>
                        Шаблон CSV
                        <Download size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="onboarding-visual" aria-hidden="true">
                    <div className="mini-document">
                      <FileText size={27} />
                      <i />
                      <i />
                      <i />
                      <span>
                        <Check size={14} />
                        Всё на своих местах
                      </span>
                    </div>
                    <span className="visual-orbit" />
                  </div>
                </div>
              ) : (
                <div className="overview-panels">
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h2>Внимание сегодня</h2>
                        <p>Счета, с которых стоит начать</p>
                      </div>
                      <span className="count-badge">{high.length}</span>
                    </div>
                    {high.length > 0 ? (
                      <div className="attention-list">
                        {high.slice(0, 5).map((inv) => (
                          <button key={inv.id} onClick={() => setSelected(inv.id)}>
                            <div className="company-avatar">
                              {inv.company.replace(/ООО\s*[«"]?/, '').slice(0, 1)}
                            </div>
                            <span>
                              <strong>{inv.company}</strong>
                              <small>
                                {inv.promise_date && inv.promise_date < today()
                                  ? 'Нарушено обещание'
                                  : `Просрочка ${inv.days_overdue} дн.`}
                              </small>
                            </span>
                            <b>{money(inv.balance)}</b>
                            <ArrowUpRight size={15} />
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="attention-clear">
                        <CircleCheck size={30} />
                        <h3>Срочных задач нет</h3>
                        <p>Продолжайте работу со счетами в реестре.</p>
                      </div>
                    )}
                    <button className="panel-footer-link" onClick={() => setTab('registry')}>
                      Открыть весь реестр
                      <ArrowRight size={15} />
                    </button>
                  </section>
                  <section className="panel aging-panel">
                    <div className="panel-heading">
                      <div>
                        <h2>Сроки задолженности</h2>
                        <p>Где сейчас находятся ваши деньги</p>
                      </div>
                      <span className="pill gray">По остаткам</span>
                    </div>
                    <div className="aging-bars">
                      {overview?.aging.map((a, i) => (
                        <div className="aging-row" key={a.label}>
                          <span>{a.label}</span>
                          <div>
                            <i
                              style={{
                                width: `${Math.max(a.amount > 0 ? 2 : 0, overview.total_outstanding ? (a.amount / overview.total_outstanding) * 100 : 0)}%`,
                                background: ['#a8b99a', '#8aa576', '#64874f', '#d5c992', '#c99b7c'][
                                  i % 5
                                ],
                              }}
                            />
                          </div>
                          <strong>{money(a.amount, true)}</strong>
                        </div>
                      ))}
                    </div>
                    <div className="aging-note">
                      <i />
                      Чем раньше контакт, тем больше пространства для договорённости.
                    </div>
                  </section>
                </div>
              )}
              <section className="recent-section">
                <div className="panel-heading">
                  <div>
                    <h2>Последние счета</h2>
                    <p>Весь контекст — в карточке счёта</p>
                  </div>
                  <button className="text-link" onClick={() => setTab('registry')}>
                    Все счета
                    <ArrowUpRight size={15} />
                  </button>
                </div>
                {invoices.length > 0 ? (
                  <InvoiceTable invoices={invoices.slice(0, 5)} onOpen={setSelected} />
                ) : (
                  <div className="recent-empty">
                    <Files size={20} />
                    <p>Здесь будут ваши счета и их текущий статус.</p>
                    <span>Добавьте первый, чтобы начать работу.</span>
                  </div>
                )}
              </section>
            </>
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
            <span>AgentPay · Деньги возвращаются в дело.</span>
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
function Metric({
  label,
  value,
  note,
  icon,
  featured = false,
}: {
  label: string;
  value: number;
  note: string;
  icon: React.ReactNode;
  featured?: boolean;
}) {
  return (
    <div className={`metric ${featured ? 'metric-featured' : ''}`}>
      <div>
        <span>{label}</span>
        {icon}
      </div>
      <strong>{money(value, true)}</strong>
      <p>{note}</p>
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
          <h1>Каждый счёт — на виду.</h1>
          <p>Контекст, договорённости и следующий шаг по каждому покупателю.</p>
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
}: {
  invoices: Invoice[];
  onOpen: (id: string) => void;
  smtp: boolean;
}) {
  const active = invoices.filter(
    (i) => i.balance > 0 && i.status !== 'paused' && i.status !== 'disputed'
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="page-date">ДЕЛОВАЯ ПЕРЕПИСКА</span>
          <h1>Нужные слова. В нужный момент.</h1>
          <p>Подготовьте письмо из карточки счёта и согласуйте текст перед отправкой.</p>
        </div>
      </div>
      <div className={`mail-connection ${smtp ? 'connected' : ''}`}>
        <Mail size={21} />
        <div>
          <strong>{smtp ? 'Почта подключена' : 'Почта не подключена'}</strong>
          <p>
            {smtp
              ? 'Согласованные письма можно отправлять из кабинета.'
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
          <p>Реквизиты для писем и ограничения, которые учитывает AgentPay.</p>
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
              Стоимость денег, % годовых
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
