import { t } from '../i18n';
import { useRouteField } from '../navigation';
import { FileInput } from './FileInput';
import { MailSetup } from './MailSetup';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  ArrowDownToLine,
  Check,
  Copy,
  Database,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  X,
} from 'lucide-react';
import { api, post, money, dateText, today, ApiError } from '../api';
import { DeskHeading, DeskError, type DeskProps } from './OperationsUI';
import './mandato-services.css';
import './connections.css';
import { ConnectionAccess } from './ConnectionAccess';

type SourceChoice = 'one_c' | 'diadoc' | 'bank' | 'registry' | 'email';
const sourceChoices: { id: SourceChoice; name: string; description: string }[] = [
  { id: 'one_c', name: t('1С'), description: t('Счета и задолженность') },
  { id: 'diadoc', name: t('ЭДО'), description: t('Документы Диадока') },
  { id: 'bank', name: t('Банк'), description: t('Выписка и поступления') },
  { id: 'registry', name: t('Реестры'), description: t('Проверка контрагентов') },
  { id: 'email', name: t('Почта'), description: t('Отправка писем') },
];

type Provider = 'one_c' | 'diadoc' | 'tbank' | 'tbank_sandbox' | 'dadata' | 'bank_exchange';
type Coverage = {
  environment?: string;
  complete?: boolean;
  content_downloaded?: boolean;
  signature_verified?: boolean;
  invoice_import_supported?: boolean;
  data_kind?: string;
  next_cursor?: string | null;
  request_cursor?: string | null;
  from_on?: string;
  to_on?: string;
};
type Connection = {
  provider: Provider;
  configured: boolean;
  status: string;
  checked_at: string | null;
  coverage: Coverage;
};
type SourceItem = {
  row: number;
  company?: string;
  inn?: string;
  number?: string;
  issued_on?: string;
  amount?: number;
  paid_amount?: number;
  balance?: number;
  due_on?: string;
  title?: string;
  document_type?: string;
  payer_name?: string;
  payer_inn?: string;
  paid_on?: string;
  reference?: string;
  purpose?: string;
  direction?: string;
  approvable?: boolean;
  operation_date?: string;
};
type Approval = { imported: number; skipped: number };
type Preview = {
  id: string;
  provider?: Provider;
  status?: string;
  checked_at?: string;
  items: SourceItem[];
  errors?: { row: number; message: string }[];
  coverage?: Coverage;
  approval?: Approval | null;
  file?: boolean;
  environment?: string;
};
type RegistryCheck = {
  id: string;
  inn: string;
  status: string;
  checked_at: string;
  result: { name?: string; ogrn?: string; state?: string; provider_record_date?: string | null };
};
const names: Record<Provider, string> = {
  one_c: t('1С'),
  diadoc: t('Диадок'),
  tbank: t('Т-Банк'),
  tbank_sandbox: t('Т-Банк'),
  dadata: t('Сведения о должнике'),
  bank_exchange: t('Выписка из файла'),
};
const statuses: Record<string, string> = {
  unconfigured: t('Не подключено'),
  not_checked: t('Ожидает проверки'),
  available: t('Доступно'),
  completed: t('Данные получены'),
  partial: t('Получена часть выписки'),
  no_match: t('Совпадений нет'),
  stale: t('Нужно обновить'),
  unavailable: t('Источник недоступен'),
};
const registration: Record<string, string> = {
  ACTIVE: t('Действует'),
  LIQUIDATING: t('В процессе ликвидации'),
  LIQUIDATED: t('Деятельность прекращена'),
  BANKRUPT: t('Есть отметка о банкротстве'),
  REORGANIZING: t('В процессе реорганизации'),
  UNKNOWN: t('Статус не подтверждён'),
};
const periodStart = () => {
  const d = new Date(`${today()}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 7);
  return d.toISOString().slice(0, 10);
};
const periodEnd = () => {
  const d = new Date(`${today()}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
};

export function ConnectionsDesk({
  invoices,
  notify,
  onChanged,
}: DeskProps & {
  onNavigate?: (target: 'settings') => void;
}) {
  const [activeSource, setActiveSource] = useRouteField<SourceChoice>('source', 'one_c');
  const [itOpen, setItOpen] = useState(false);
  const [mailConfigured, setMailConfigured] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [connections, setConnections] = useState<Connection[]>([]),
    [runs, setRuns] = useState<Preview[]>([]),
    [checks, setChecks] = useState<RegistryCheck[]>([]);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(''),
    [preview, setPreview] = useState<Preview | null>(null),
    [selected, setSelected] = useState<number[]>([]),
    [reason, setReason] = useState('');
  const [duplicateDetected, setDuplicateDetected] = useState(false),
    [distinctConfirmed, setDistinctConfirmed] = useState(false),
    [distinctReason, setDistinctReason] = useState('');
  const [ledgerPreview, setLedgerPreview] = useState<LedgerPreview | null>(null);
  const [batchResult, setBatchResult] = useState<{
    requested_count: number;
    cached_count: number;
    checked_count: number;
  } | null>(null);
  const [cacheClock, setCacheClock] = useState(Date.now());
  const registryInns = [...new Set(invoices.map((invoice) => invoice.inn).filter(Boolean))];
  const now = Math.max(cacheClock, Date.now());
  const freshInns = new Set(
    checks
      .filter(
        (check) =>
          ['completed', 'no_match'].includes(check.status) &&
          now >= Date.parse(check.checked_at) &&
          now - Date.parse(check.checked_at) < 86_400_000
      )
      .map((check) => check.inn)
  );
  const pendingInns = registryInns.filter((inn) => !freshInns.has(inn));
  const batchInns = pendingInns.slice(0, 10);
  useEffect(() => {
    const expiries = checks
      .filter((check) => ['completed', 'no_match'].includes(check.status))
      .map((check) => Date.parse(check.checked_at) + 86_400_000)
      .filter((expiry) => expiry > Date.now());
    if (!expiries.length) return;
    const timer = setTimeout(
      () => setCacheClock(Date.now()),
      Math.max(0, Math.min(...expiries) - Date.now()) + 25
    );
    return () => clearTimeout(timer);
  }, [checks, cacheClock]);
  const [inn, setInn] = useState(''),
    [from, setFrom] = useState(periodStart),
    [to, setTo] = useState(periodEnd);
  const reload = useCallback(async () => {
    const [c, r, checks] = await Promise.all([
      api<{ items: Connection[] }>('/integrations'),
      api<{ items: Preview[] }>('/integrations/runs'),
      api<{ items: RegistryCheck[] }>('/integrations/registry/checks'),
      api<{ smtp_configured: boolean }>('/settings')
        .then((settings) => setMailConfigured(settings.smtp_configured === true))
        .catch(() => setMailConfigured(null)),
    ]);
    setConnections(c.items);
    setRuns(r.items);
    setChecks(checks.items);
  }, []);
  useEffect(() => {
    void reload()
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [reload]);
  async function perform(key: string, action: () => Promise<void>) {
    setBusy(key);
    setError('');
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
      notify((e as Error).message, true);
    } finally {
      setBusy('');
    }
  }
  function clearDuplicateDecision() {
    setDuplicateDetected(false);
    setDistinctConfirmed(false);
    setDistinctReason('');
  }
  function stage(value: Preview) {
    clearDuplicateDecision();
    setPreview(value);
    setSelected([]);
    setReason('');
    setLedgerPreview(null);
  }
  function changeSelection(rows: number[]) {
    clearDuplicateDecision();
    setSelected(rows);
    setLedgerPreview(null);
  }
  async function read(
    provider: Provider,
    cursor?: string,
    originalPeriod?: { from_on: string; to_on: string }
  ) {
    await perform(provider, async () => {
      const result = await post<Preview>(
        `/integrations/${provider}/read`,
        provider === 'tbank'
          ? {
              from_on: originalPeriod?.from_on ?? from,
              to_on: originalPeriod?.to_on ?? to,
              ...(cursor ? { cursor } : {}),
            }
          : {}
      );
      stage(result);
      await reload();
      if (result.status === 'completed')
        notify(t('Источник прочитан. Проверьте строки перед сохранением.'));
    });
  }
  async function filePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const file = data.get('statement') as File;
    await perform('file', async () => {
      if (!file?.size) throw new Error(t('Выберите файл выписки.'));
      if (file.size > 1_400_000)
        throw new Error(t('Для загрузки за один раз выберите файл до 1,4 МБ.'));
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(',')[1]);
        reader.onerror = () => reject(new Error(t('Не удалось прочитать файл.')));
        reader.readAsDataURL(file);
      });
      const value = await post<Preview>('/integrations/bank/preview', {
        content,
        own_account: String(data.get('own_account')),
        source_ref: String(data.get('source_ref')).trim(),
      });
      stage({ ...value, file: true, provider: 'bank_exchange' });
    });
  }
  const invoiceSupported =
    preview?.provider === 'one_c' &&
    preview.status === 'completed' &&
    preview.coverage?.invoice_import_supported === true;
  const sandbox =
    preview?.provider === 'tbank_sandbox' ||
    preview?.environment === 'sandbox' ||
    preview?.coverage?.environment === 'sandbox';
  const bankSource = !!preview && (preview.file || preview.provider === 'tbank');
  const badRows = new Set(preview?.errors?.map((e) => e.row));
  const canSelect = (row: SourceItem) =>
    !!preview &&
    !sandbox &&
    (!preview.approval || invoiceSupported) &&
    !badRows.has(0) &&
    !badRows.has(row.row) &&
    (preview.file || preview.provider === 'tbank'
      ? row.approvable === true &&
        (preview.file || ['completed', 'partial'].includes(preview.status ?? ''))
      : preview.status === 'completed');
  const selectable = preview?.items.filter(canSelect).map((r) => r.row) ?? [];
  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preview) return;
    await perform('approve', async () => {
      let result: Approval;
      try {
        result = await post<Approval>(
          preview.file
            ? `/integrations/bank/imports/${preview.id}/approve`
            : `/integrations/runs/${preview.id}/approve`,
          {
            selected_rows: selected,
            reason: reason.trim(),
            ...(bankSource && duplicateDetected && selected.length === 1
              ? { distinct_confirmed: distinctConfirmed, distinct_reason: distinctReason.trim() }
              : {}),
          }
        );
      } catch (error) {
        if (
          bankSource &&
          error instanceof ApiError &&
          error.status === 409 &&
          error.message.startsWith(t('Возможный дубль банковского поступления'))
        ) {
          setDuplicateDetected(true);
          setDistinctConfirmed(false);
          setDistinctReason('');
        }
        throw error;
      }
      setPreview({ ...preview, approval: result });
      changeSelection([]);
      onChanged();
      await reload();
      notify(t('Сохранено: {0}. Уже учтено: {1}.', [result.imported, result.skipped]));
    });
  }
  async function prepareInvoices() {
    if (!preview) return;
    setLedgerPreview(null);
    await perform('invoice-preview', async () => {
      const result = await post<LedgerPreview>(`/integrations/runs/${preview.id}/invoice-preview`, {
        selected_rows: selected,
      });
      setLedgerPreview(result);
    });
  }
  async function approveInvoices(reason: string) {
    if (!ledgerPreview) return;
    await perform('invoice-approve', async () => {
      const result = await post<{ created: number; updated: number; skipped: number }>(
        `/finance/imports/${ledgerPreview.id}/approve`,
        { reason }
      );
      setLedgerPreview({ ...ledgerPreview, result });
      onChanged();
      await reload();
      notify(
        t('Счета созданы: {0}. Обновлены: {1}. Без изменений: {2}.', [
          result.created,
          result.updated,
          result.skipped,
        ])
      );
    });
  }
  const sourceName = sourceChoices.find((source) => source.id === activeSource)!.name;
  const matchesSource = (provider?: Provider) =>
    activeSource === 'bank'
      ? provider === 'tbank' || provider === 'bank_exchange'
      : provider === activeSource;
  const sourceRuns = runs.filter((run) => matchesSource(run.provider));
  const previewVisible = !!preview && matchesSource(preview.provider);
  const itSource =
    activeSource === 'bank' ? 'tbank' : activeSource === 'registry' ? 'dadata' : activeSource;
  function sourceStatus(source: SourceChoice) {
    if (source === 'email')
      return mailConfigured === null
        ? loading
          ? t('Проверяем…')
          : t('Статус недоступен')
        : mailConfigured
          ? t('Отправка настроена')
          : t('Не подключено');
    if (source === 'bank') return t('Импорт из файла доступен');
    const provider = source === 'registry' ? 'dadata' : source;
    const connection = connections.find((item) => item.provider === provider);
    if (!connection) return loading ? t('Проверяем…') : t('Статус недоступен');
    return connection.configured
      ? (statuses[connection.status] ?? t('Статус не подтверждён'))
      : t('Не подключено');
  }
  function connectionCard(c: Connection) {
    return (
      <section className="ms-card" key={c.provider}>
        <div className="ms-card-heading">
          <Database size={20} />
          <h2>{names[c.provider]}</h2>
          <span className={`ms-status ms-status-${c.status}`}>
            {statuses[c.status] ?? t('Ожидает проверки')}
          </span>
        </div>
        <p>
          {c.provider === 'one_c'
            ? t('Загрузите данные и выберите строки для сверки с реестром.')
            : c.provider === 'diadoc'
              ? t(
                  'Реквизиты документов ЭДО. Содержимое и электронные подписи здесь не проверяются.'
                )
              : t(
                  'Поступления из выписки. После подтверждения их нужно распределить по счетам в «Финансах».'
                )}
        </p>
        {!c.configured && (
          <p className="ms-note">{t('Настройте доступ по инструкции для IT-специалиста ниже.')}</p>
        )}
        {c.checked_at && (
          <small>
            {t('Последнее чтение:')} {dateText(c.checked_at)}
          </small>
        )}
        {c.provider === 'tbank' && (
          <div className="ms-fields">
            <label className="field">
              {t('Начало периода')}
              <input
                type="date"
                min="2023-06-01"
                max={today()}
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label className="field">
              {t('Окончание, не включая')}
              <input
                type="date"
                min={from}
                max={periodEnd()}
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </label>
            <p className="ms-note">{t('До 31 дня за одно чтение.')}</p>
          </div>
        )}
        <button
          className="button button-dark"
          disabled={
            !!busy || !c.configured || (c.provider === 'tbank' && (!from || !to || to <= from))
          }
          onClick={() => void read(c.provider)}
        >
          <ArrowDownToLine size={16} />
          {busy === c.provider ? t('Читаем…') : t('Прочитать данные')}
        </button>
      </section>
    );
  }
  return (
    <div className="mandato-services connections-desk">
      <DeskHeading
        eyebrow={t('ИСТОЧНИКИ ДАННЫХ')}
        title={t('Подключения')}
        action={
          <button
            className="button button-outline"
            disabled={!!busy}
            onClick={() => void perform('refresh', reload)}
          >
            <RefreshCw size={16} /> {t('Обновить статусы')}
          </button>
        }
      >
        {t('Выберите источник, чтобы загрузить данные или настроить доступ.')}
      </DeskHeading>
      <DeskError>{error}</DeskError>
      <div className="connections-catalogue" role="group" aria-label={t('Источники')}>
        {sourceChoices.map((source) => (
          <button
            key={source.id}
            type="button"
            aria-label={source.name}
            aria-describedby={`connection-${source.id}-description connection-${source.id}-status`}
            aria-pressed={activeSource === source.id}
            disabled={!!busy}
            onClick={() => {
              setActiveSource(source.id);
              setItOpen(false);
              setError('');
            }}
          >
            <strong>{source.name}</strong>
            <span id={`connection-${source.id}-description`}>{source.description}</span>
            <small id={`connection-${source.id}-status`}>{sourceStatus(source.id)}</small>
          </button>
        ))}
      </div>
      <section className="connections-detail" aria-label={t('Источник: {0}', [sourceName])}>
        {(activeSource === 'one_c' || activeSource === 'diadoc') && (
          <>
            <div className="ms-connections">
              {connections.filter((c) => c.provider === activeSource).map(connectionCard)}
            </div>

            {!loading && !connections.some((item) => item.provider === activeSource) && (
              <p className="ms-note">{t('Статус источника недоступен. Обновите статусы.')}</p>
            )}
          </>
        )}
        {activeSource === 'bank' && (
          <>
            <section className="ms-card">
              <h2>
                <Upload size={20} /> {t('Выписка из файла')}
              </h2>
              <p>
                {t(
                  'Файл 1CClientBankExchange из банка, до 1,4 МБ. На подтверждение доступны входящие платежи на ваш счёт.'
                )}
              </p>
              <form className="ms-form" onSubmit={filePreview}>
                <label className="field">
                  {t('Собственный расчётный счёт')}
                  <input
                    name="own_account"
                    required
                    pattern="[0-9]{20}"
                    inputMode="numeric"
                    maxLength={20}
                    placeholder={t('20 цифр')}
                  />
                </label>
                <label className="field">
                  {t('Название источника')}
                  <input
                    name="source_ref"
                    required
                    maxLength={200}
                    placeholder={t('Банковская выписка за октябрь')}
                  />
                </label>
                <label className="field">
                  {t('Файл банковской выписки')}
                  <FileInput name="statement" required accept=".txt,text/plain" />
                </label>
                <button className="button button-outline" disabled={!!busy}>
                  <Upload size={16} />
                  {busy === 'file' ? t('Проверяем…') : t('Проверить выписку')}
                </button>
              </form>
            </section>

            <details className="connections-disclosure">
              <summary>{t('Прямое подключение Т-Банка')}</summary>
              <div className="ms-connections">
                {connections.filter((c) => c.provider === 'tbank').map(connectionCard)}
              </div>

              {!loading && !connections.some((item) => item.provider === 'tbank') && (
                <p className="ms-note">{t('Статус Т-Банка недоступен. Обновите статусы.')}</p>
              )}
            </details>
          </>
        )}
        {activeSource === 'registry' && (
          <section className="ms-card">
            <h2>
              <Search size={20} /> {t('Сведения о должнике')}
            </h2>
            <p>{t('Проверка ЕГРЮЛ/ЕГРИП по ИНН через DaData.')}</p>
            <div className="connections-manual">
              <span>{t('Проверить вручную:')}</span>
              <a href="https://kad.arbitr.ru/" target="_blank" rel="noopener noreferrer">
                {t('Картотека арбитражных дел')}
              </a>
              <a href="https://fssp.gov.ru/iss/ip" target="_blank" rel="noopener noreferrer">
                {t('ФССП')}
              </a>
              <a href="https://bankrot.fedresurs.ru/" target="_blank" rel="noopener noreferrer">
                {t('ЕФРСБ')}
              </a>
            </div>
            <form
              className="ms-form"
              onSubmit={(e) => {
                e.preventDefault();
                void perform('registry', async () => {
                  await post('/integrations/registry/check', { inn });
                  await reload();
                  onChanged();
                });
              }}
            >
              <label className="field">
                {t('Контрагент из реестра')}
                <select
                  value={inn && invoices.some((i) => i.inn === inn) ? inn : ''}
                  onChange={(e) => setInn(e.target.value)}
                >
                  <option value="">{t('Указать ИНН вручную')}</option>
                  {[...new Map(invoices.filter((i) => i.inn).map((i) => [i.inn, i])).values()].map(
                    (i) => (
                      <option key={i.inn} value={i.inn}>
                        {i.company} · {i.inn}
                      </option>
                    )
                  )}
                </select>
              </label>
              <label className="field">
                {t('Точный ИНН')}
                <input
                  required
                  inputMode="numeric"
                  pattern="[0-9]{10}|[0-9]{12}"
                  maxLength={12}
                  value={inn}
                  onChange={(e) => setInn(e.target.value)}
                />
              </label>
              <button
                className="button button-outline"
                disabled={!!busy || !connections.find((c) => c.provider === 'dadata')?.configured}
              >
                <Search size={16} />
                {busy === 'registry' ? t('Проверяем…') : t('Проверить должника')}
              </button>
              {connections.find((c) => c.provider === 'dadata')?.configured === false && (
                <p className="ms-note">
                  {t(
                    'Проверка пока не подключена. Отсутствие проверки не подтверждает отсутствие рисков.'
                  )}
                </p>
              )}
            </form>
            <div className="ms-form">
              <button
                type="button"
                className="button button-outline"
                disabled={
                  !!busy ||
                  batchInns.length === 0 ||
                  !connections.find((connection) => connection.provider === 'dadata')?.configured
                }
                onClick={() =>
                  void perform('registry-batch', async () => {
                    setBatchResult(null);
                    const result = await post<{
                      requested_count: number;
                      cached_count: number;
                      checked_count: number;
                    }>('/integrations/registry/check-batch', { inns: batchInns });
                    setBatchResult(result);
                    await reload();
                    onChanged();
                  })
                }
              >
                {registryInns.length > 0 && pendingInns.length === 0
                  ? t('Свежие результаты по всем ИНН')
                  : t('Проверить должников: {0}', [batchInns.length])}
              </button>
              <p className="ms-note">
                {registryInns.length === 0
                  ? t('В реестре пока нет ИНН для пакетной проверки.')
                  : pendingInns.length === 0
                    ? t('Все {0} ИНН проверены за последние 24 часа.', [registryInns.length])
                    : t(
                        'Ожидают проверки: {0} из {1}. За один раз — до 10 ИНН. Результаты обновляются через 24 часа.',
                        [pendingInns.length, registryInns.length]
                      )}
              </p>
              {batchResult && (
                <p className="ms-note">
                  {t('Результаты по')} {batchResult.requested_count} {t('ИНН: без кеша')}{' '}
                  {batchResult.checked_count}
                  {t(', из свежего кеша')} {batchResult.cached_count}.
                </p>
              )}
            </div>
            <div className="ms-list">
              {checks.map((check) => (
                <article key={check.id} className="ms-list-item">
                  <div>
                    <strong>{check.result.name || t('ИНН {0}', [check.inn])}</strong>
                    <small>
                      {check.inn} {t('· Запрошено')} {accessDate(check.checked_at)} {t('МСК')}
                    </small>
                  </div>
                  <span className={`ms-status ms-status-${check.status}`}>
                    {statuses[check.status] ?? t('Статус не подтверждён')}
                  </span>
                  {check.status === 'completed' && (
                    <p>
                      {registration[check.result.state ?? 'UNKNOWN'] ?? t('Статус не подтверждён')}
                      {check.result.ogrn && t(' · ОГРН {0}', [check.result.ogrn])}
                    </p>
                  )}
                  {check.status === 'stale' && (
                    <p>{t('Сведения устарели. Перед решением выполните новую проверку.')}</p>
                  )}
                  <small>
                    {check.result.provider_record_date
                      ? t('Дата последнего изменения записи у провайдера: {0}', [
                          new Date(check.result.provider_record_date).toLocaleDateString('ru-RU', {
                            timeZone: 'Europe/Moscow',
                          }),
                        ])
                      : t('Дата последнего изменения записи у провайдера не указана.')}
                  </small>
                  <ul className="ms-registry-coverage">
                    <li>
                      {t('ЕГРЮЛ/ЕГРИП:')}{' '}
                      {['completed', 'stale'].includes(check.status)
                        ? t('снимок провайдера')
                        : t('совпадение не подтверждено')}
                    </li>
                    <li>{t('Банкротство: не проверено')}</li>
                    <li>{t('Судебные дела: не проверено')}</li>
                    <li>{t('ФССП: не проверено')}</li>
                  </ul>
                </article>
              ))}
            </div>
          </section>
        )}
        {activeSource === 'email' && <MailSetup />}
        {itSource !== 'email' && (
          <details
            key={activeSource}
            className="connections-disclosure"
            open={itOpen}
            onToggle={(event) => setItOpen(event.currentTarget.open)}
          >
            <summary>{t('Для IT-специалиста')}</summary>
            {itOpen && <ConnectionAccess selectedSource={itSource} statuses={connections} />}
          </details>
        )}
        {(previewVisible || sourceRuns.length > 0) && (
          <section className="ms-card ms-preview">
            <div className="ms-card-heading">
              <h2>{t('Проверка прочитанных данных')}</h2>
              {sourceRuns.length > 0 && (
                <label className="field">
                  {t('История чтений')}
                  <select
                    aria-label={t('Открыть чтение источника')}
                    value={previewVisible && preview && !preview.file ? preview.id : ''}
                    disabled={!!busy}
                    onChange={(e) => {
                      const id = e.target.value;
                      if (id)
                        void perform('history', async () =>
                          stage(await api<Preview>(`/integrations/runs/${id}`))
                        );
                    }}
                  >
                    <option value="">{t('Выберите источник')}</option>
                    {sourceRuns.map((run) => (
                      <option key={run.id} value={run.id}>
                        {run.provider ? names[run.provider] : t('Источник')} ·{' '}
                        {run.checked_at ? dateText(run.checked_at) : ''} ·{' '}
                        {statuses[run.status ?? ''] ?? t('Ожидает проверки')}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
            {!previewVisible || !preview ? (
              <p>
                {t(
                  'Прочитайте подключённый источник или загрузите выписку. Здесь появятся строки для сверки.'
                )}
              </p>
            ) : (
              <>
                <p>
                  {preview.provider && names[preview.provider]}
                  {preview.status && ` · ${statuses[preview.status] ?? t('Статус не подтверждён')}`}
                </p>
                {!sandbox && preview.coverage?.complete === false && (
                  <p className="ms-warning">
                    {t(
                      'Источник вернул часть списка. Каждая страница проверяется и подтверждается отдельно; полнота всего периода пока не подтверждена.'
                    )}
                  </p>
                )}
                {preview.status && !['completed', 'partial'].includes(preview.status) && (
                  <p className="ms-warning">
                    {preview.status === 'no_match'
                      ? t(
                          'Источник не вернул записей. Это не подтверждает отсутствие задолженности или рисков.'
                        )
                      : preview.status === 'stale'
                        ? t('Данные устарели. Прочитайте источник ещё раз перед подтверждением.')
                        : t(
                            'Данные не получены. Проверьте состояние подключения и повторите чтение.'
                          )}
                  </p>
                )}
                {preview.provider === 'one_c' && !invoiceSupported && (
                  <p className="ms-note">
                    {t(
                      'В этом чтении доступны только сведения источника. Для счетов нужны отдельные документы с номером, датой, сроком, суммой и подтверждённым состоянием расчётов.'
                    )}
                  </p>
                )}
                {preview.coverage?.request_cursor && (
                  <p className="ms-note">
                    {t(
                      'Это страница продолжения. Предыдущие страницы доступны в истории чтений; их строки не объединяются и не подтверждаются автоматически.'
                    )}
                  </p>
                )}
                {preview.provider === 'tbank' &&
                  preview.coverage?.next_cursor &&
                  preview.coverage.from_on &&
                  preview.coverage.to_on && (
                    <button
                      className="button button-outline"
                      disabled={!!busy}
                      onClick={() =>
                        void read('tbank', preview.coverage!.next_cursor!, {
                          from_on: preview.coverage!.from_on!,
                          to_on: preview.coverage!.to_on!,
                        })
                      }
                    >
                      {t('Следующая страница выписки')}
                    </button>
                  )}
                {!!preview.errors?.length && (
                  <ul className="ms-errors">
                    {preview.errors.map((e, i) => (
                      <li key={i}>
                        {e.row ? t('Строка {0}: ', [e.row]) : ''}
                        {e.message}
                      </li>
                    ))}
                  </ul>
                )}
                {preview.items.length > 0 && (
                  <form onSubmit={approve}>
                    <label className="ms-check">
                      <input
                        type="checkbox"
                        checked={selectable.length > 0 && selected.length === selectable.length}
                        disabled={!!busy || selectable.length === 0}
                        onChange={(e) => changeSelection(e.target.checked ? selectable : [])}
                      />{' '}
                      {t('Выбрать все доступные строки')}
                    </label>
                    <div className="ms-table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{t('Выбор')}</th>
                            <th>{t('Документ / контрагент')}</th>
                            <th>{t('Дата')}</th>
                            <th>{t('Сумма')}</th>
                            <th>{t('Проверка')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {preview.items.map((item) => (
                            <tr key={item.row}>
                              <td>
                                <input
                                  aria-label={t('Подтвердить строку {0}', [item.row])}
                                  type="checkbox"
                                  checked={selected.includes(item.row)}
                                  disabled={!!busy || !canSelect(item)}
                                  onChange={(e) =>
                                    changeSelection(
                                      e.target.checked
                                        ? [...selected, item.row]
                                        : selected.filter((row) => row !== item.row)
                                    )
                                  }
                                />
                              </td>
                              <td>
                                <strong>
                                  {item.company ||
                                    item.payer_name ||
                                    item.title ||
                                    item.document_type ||
                                    t('Документ')}
                                </strong>
                                <small>
                                  {item.reference || item.number}
                                  {(item.inn || item.payer_inn) &&
                                    t(' · ИНН {0}', [item.inn || item.payer_inn])}
                                </small>
                                {item.purpose && <small>{item.purpose}</small>}
                                {item.due_on && (
                                  <small>
                                    {t('Срок оплаты:')} {dateText(item.due_on)}
                                  </small>
                                )}
                                {item.paid_amount != null && (
                                  <small>
                                    {t('Оплачено по источнику:')} {money(item.paid_amount)}
                                  </small>
                                )}
                                {item.balance != null && (
                                  <small>
                                    {t('Остаток по источнику:')} {money(item.balance)}
                                  </small>
                                )}
                              </td>
                              <td>
                                {item.paid_on || item.issued_on || item.operation_date
                                  ? dateText(item.paid_on || item.issued_on || item.operation_date!)
                                  : '—'}
                              </td>
                              <td>{item.amount == null ? '—' : money(item.amount)}</td>
                              <td>
                                {badRows.has(item.row)
                                  ? t('Нужна сверка')
                                  : item.direction === 'outgoing'
                                    ? t('Исходящий платёж')
                                    : item.direction === 'own_transfer'
                                      ? t('Собственный перевод')
                                      : item.approvable === false
                                        ? t('Недоступно для учёта')
                                        : t('К проверке')}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {sandbox ? null : preview.approval ? (
                      <p className="ms-success">
                        <Check size={16} /> {t('Подтверждено:')} {preview.approval.imported}
                        {t('. Уже учтено:')} {preview.approval.skipped}.
                      </p>
                    ) : (
                      <div className="ms-form ms-approval">
                        <p className="ms-note">
                          {preview.file || preview.provider === 'tbank'
                            ? t(
                                'Подтверждение добавит банковские поступления без распределения. Остатки счетов изменятся после распределения в «Финансах».'
                              )
                            : t(
                                'Подтверждение сохранит сведения с источником. Оно не создаёт счета, не подписывает и не отправляет документы.'
                              )}
                        </p>
                        {duplicateDetected && (
                          <fieldset className="ms-fieldset">
                            <legend>{t('Возможное повторное поступление')}</legend>
                            <p className="ms-note">
                              {t(
                                'Сверьте оригиналы. Подтверждение отдельного поступления допускается только для одного выбранного документа с другим номером. Одинаковый номер не разрешает повторный учёт.'
                              )}
                            </p>
                            {selected.length !== 1 && (
                              <p className="ms-warning">
                                {t('Выберите один документ и выполните подтверждение заново.')}
                              </p>
                            )}
                            <label className="ms-check">
                              <input
                                type="checkbox"
                                disabled={selected.length !== 1}
                                checked={distinctConfirmed}
                                onChange={(event) => setDistinctConfirmed(event.target.checked)}
                              />
                              {t('Подтверждаю отдельное поступление с другим номером документа')}
                            </label>
                            <label className="field">
                              {t('Почему это отдельное поступление')}
                              <textarea
                                required
                                minLength={10}
                                maxLength={3000}
                                value={distinctReason}
                                onChange={(event) => setDistinctReason(event.target.value)}
                              />
                            </label>
                          </fieldset>
                        )}
                        <label className="field">
                          {t('Основание подтверждения')}
                          <textarea
                            required
                            maxLength={3000}
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                          />
                        </label>
                        <button
                          className="button button-dark"
                          disabled={
                            !!busy ||
                            !selected.length ||
                            !reason.trim() ||
                            (duplicateDetected &&
                              (!distinctConfirmed ||
                                distinctReason.trim().length < 10 ||
                                selected.length !== 1))
                          }
                        >
                          <Check size={16} />
                          {busy === 'approve'
                            ? t('Сохраняем…')
                            : t('Подтвердить строки: {0}', [selected.length])}
                        </button>
                      </div>
                    )}
                  </form>
                )}
                {invoiceSupported && (
                  <div className="ms-form">
                    <p className="ms-note">
                      {t(
                        'В источнике есть отдельные документы задолженности. Перед изменением реестра выполните отдельную сверку выбранных строк. Сохранение сведений выше не изменяет счета.'
                      )}
                    </p>
                    <button
                      type="button"
                      className="button button-outline"
                      disabled={!!busy || !selected.length}
                      onClick={() => void prepareInvoices()}
                    >
                      {t('Сверить выбранные документы с реестром')}
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        )}
        {ledgerPreview && previewVisible && activeSource === 'one_c' && (
          <LedgerImportReview
            key={ledgerPreview.id}
            preview={ledgerPreview}
            busy={!!busy}
            onApprove={approveInvoices}
          />
        )}
      </section>
      <details className="connections-disclosure connections-partner">
        <summary>{t('Доступ партнёра к сводке')}</summary>
        <PartnerAccess notify={notify} />
      </details>
    </div>
  );
}

type PartnerGrant = {
  id: string;
  partner_name: string;
  purpose: string;
  scope: string;
  expires_at: string;
  revoked_at: string | null;
  created_at: string;
};
const accessDate = (value: string) =>
  new Date(value).toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow',
    dateStyle: 'short',
    timeStyle: 'short',
  });
function PartnerAccess({ notify }: { notify: DeskProps['notify'] }) {
  const [clock, setClock] = useState(Date.now());
  const [grants, setGrants] = useState<PartnerGrant[]>([]),
    [issued, setIssued] = useState<(PartnerGrant & { token: string }) | null>(null);
  const [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const reload = useCallback(
    async () => setGrants((await api<{ items: PartnerGrant[] }>('/partner/grants')).items),
    []
  );
  useEffect(() => {
    const upcoming = grants
      .filter((grant) => !grant.revoked_at)
      .map((grant) => Date.parse(grant.expires_at))
      .filter((time) => time > clock);
    if (!upcoming.length) return;
    const timer = setTimeout(
      () => setClock(Date.now()),
      Math.max(0, Math.min(...upcoming) - Date.now()) + 25
    );
    return () => clearTimeout(timer);
  }, [grants, clock]);
  useEffect(() => {
    void reload().catch((e) => setError((e as Error).message));
  }, [reload]);
  async function issue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget,
      values = new FormData(form);
    setBusy(true);
    setError('');
    try {
      const value = await post<PartnerGrant & { token: string }>('/partner/grants', {
        partner_name: String(values.get('partner_name')).trim(),
        purpose: String(values.get('purpose')).trim(),
        expires_in_minutes: Number(values.get('expires_in_minutes')),
        confirmed,
      });
      setIssued(value);
      setConfirmed(false);
      form.reset();
      await reload();
      notify(t('Доступ к сводным показателям создан. Сохраните ключ перед закрытием.'));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(grant: PartnerGrant) {
    setBusy(true);
    setError('');
    try {
      await post(`/partner/grants/${grant.id}/revoke`);
      if (issued?.id === grant.id) setIssued(null);
      await reload();
      notify(t('Партнёрский доступ отозван.'));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.token);
      notify(t('Ключ скопирован. Передайте его указанному получателю по защищённому каналу.'));
    } catch {
      setError(t('Не удалось скопировать ключ. Выделите его и скопируйте вручную.'));
    }
  }
  return (
    <section className="ms-card">
      <h2>
        <ShieldCheck size={20} /> {t('Доступ партнёра к сводке')}
      </h2>
      <p>
        {t(
          'Разрешите указанному получателю читать только общие суммы портфеля и состояние аудита. Имена должников, документы и реквизиты счетов в сводку не входят. Доступ ограничен сроком и может быть отозван.'
        )}
      </p>
      <DeskError>{error}</DeskError>
      <form className="ms-form" onSubmit={issue}>
        <div className="ms-fields">
          <label className="field">
            {t('Получатель доступа')}
            <input
              name="partner_name"
              required
              minLength={2}
              maxLength={200}
              placeholder={t('Наименование организации-получателя')}
            />
          </label>
          <label className="field">
            {t('Срок доступа, минут')}
            <input
              name="expires_in_minutes"
              type="number"
              required
              min={1}
              max={1440}
              defaultValue={60}
            />
          </label>
        </div>
        <label className="field">
          {t('Цель передачи сводки')}
          <textarea name="purpose" required minLength={10} maxLength={1000} />
        </label>
        <label className="ms-check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />{' '}
          {t(
            'Разрешаю указанному получателю читать агрегированный отчёт для этой цели и на указанный срок'
          )}
        </label>
        <button className="button button-outline" disabled={busy || !confirmed || !!issued}>
          <ShieldCheck size={16} />
          {t('Создать доступ к сводке')}
        </button>
      </form>
      {issued && (
        <div className="ms-partner-token">
          <h3>
            {t('Ключ для')} {issued.partner_name}
          </h3>
          <p>
            {t('Действует до')} {accessDate(issued.expires_at)}{' '}
            {t(
              'МСК. Ключ показывается один раз. Сохраните его перед закрытием и передайте только указанному получателю.'
            )}
          </p>
          <label className="field">
            {t('Ключ партнёрского доступа')}
            <input readOnly value={issued.token} autoComplete="off" spellCheck={false} />
          </label>
          <div className="ms-actions">
            <button className="button button-outline" type="button" onClick={() => void copy()}>
              <Copy size={16} />
              {t('Скопировать ключ')}
            </button>
            <button className="button button-outline" type="button" onClick={() => setIssued(null)}>
              <X size={16} />
              {t('Скрыть ключ')}
            </button>
          </div>
        </div>
      )}
      <div className="ms-list">
        {grants.map((grant) => {
          const active = !grant.revoked_at && Date.parse(grant.expires_at) > clock;
          return (
            <article key={grant.id} className="ms-list-item">
              <div>
                <strong>{grant.partner_name}</strong>
                <small>
                  {t('До')} {accessDate(grant.expires_at)} {t('МСК')}
                </small>
              </div>
              <span className="ms-status">
                {grant.revoked_at ? t('Отозван') : active ? t('Действует') : t('Срок истёк')}
              </span>
              <p>{grant.purpose}</p>
              {active && (
                <button
                  className="button button-outline"
                  disabled={busy}
                  onClick={() => void revoke(grant)}
                >
                  {t('Отозвать доступ')}
                </button>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

type LedgerFacts = {
  company?: string;
  inn?: string;
  email?: string;
  number?: string;
  issued_on?: string;
  due_on?: string;
  amount?: number;
  paid_amount?: number;
  opening_paid_amount?: number;
};
type LedgerPreview = {
  id: string;
  errors: { row: number; message: string }[];
  changes: {
    action: 'create' | 'update' | 'skip' | 'conflict';
    before?: LedgerFacts;
    after: LedgerFacts;
    reason?: string;
  }[];
  result?: { created: number; updated: number; skipped: number };
};
const changeNames = {
  create: t('Новый счёт'),
  update: t('Изменение счёта'),
  skip: t('Без изменений'),
  conflict: t('Конфликт — требуется сверка'),
};
function LedgerFactsView({ facts }: { facts?: LedgerFacts }) {
  if (!facts) return <span>{t('Счёта в реестре нет')}</span>;
  return (
    <dl className="ms-ledger-facts">
      <div>
        <dt>{t('Контрагент')}</dt>
        <dd>
          {facts.company || '—'}
          {facts.inn && ` · ${facts.inn}`}
        </dd>
      </div>
      {facts.email && (
        <div>
          <dt>{t('Почта')}</dt>
          <dd>{facts.email}</dd>
        </div>
      )}
      <div>
        <dt>{t('Номер и дата')}</dt>
        <dd>
          {facts.number} · {facts.issued_on ? dateText(facts.issued_on) : '—'}
        </dd>
      </div>
      <div>
        <dt>{t('Срок оплаты')}</dt>
        <dd>{facts.due_on ? dateText(facts.due_on) : '—'}</dd>
      </div>
      <div>
        <dt>{t('Полная сумма')}</dt>
        <dd>{facts.amount == null ? t('Не указана') : money(facts.amount)}</dd>
      </div>
      <div>
        <dt>{t('Оплачено')}</dt>
        <dd>{facts.paid_amount == null ? t('Не указано') : money(facts.paid_amount)}</dd>
      </div>
      {facts.opening_paid_amount != null && (
        <div>
          <dt>{t('Начальная оплата')}</dt>
          <dd>{money(facts.opening_paid_amount)}</dd>
        </div>
      )}
    </dl>
  );
}
function LedgerImportReview({
  preview,
  busy,
  onApprove,
}: {
  preview: LedgerPreview;
  busy: boolean;
  onApprove: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState(''),
    [confirmed, setConfirmed] = useState(false);
  const blocked =
    preview.errors.length > 0 || preview.changes.some((change) => change.action === 'conflict');
  return (
    <section className="ms-card ms-ledger-preview">
      <h2>{t('Сверка документов с реестром')}</h2>
      <p>
        {t(
          'Проверьте новые счета и каждое изменение. Начальные оплаты из источника не становятся банковскими поступлениями.'
        )}
      </p>
      {preview.errors.length > 0 && (
        <ul className="ms-errors">
          {preview.errors.map((error, index) => (
            <li key={index}>
              {t('Строка')} {error.row}: {error.message}
            </li>
          ))}
        </ul>
      )}
      <div className="ms-list">
        {preview.changes.map((change, index) => (
          <article key={index} className="ms-ledger-change">
            <h3>{changeNames[change.action]}</h3>
            {change.reason && <p className="ms-warning">{change.reason}</p>}
            <div className="ms-columns">
              <div>
                <h4>{t('Сейчас в реестре')}</h4>
                <LedgerFactsView facts={change.before} />
              </div>
              <div>
                <h4>{t('После подтверждения')}</h4>
                <LedgerFactsView facts={change.after} />
              </div>
            </div>
          </article>
        ))}
      </div>
      {preview.result ? (
        <p className="ms-success">
          {t('Создано:')} {preview.result.created}
          {t('. Обновлено:')} {preview.result.updated}
          {t('. Без изменений:')} {preview.result.skipped}.
        </p>
      ) : (
        <form
          className="ms-form"
          onSubmit={(event) => {
            event.preventDefault();
            void onApprove(reason.trim());
          }}
        >
          {blocked && (
            <p className="ms-warning">
              {t(
                'Подтверждение недоступно до устранения ошибок и конфликтов. Исправьте источник и выполните новую сверку.'
              )}
            </p>
          )}
          <label className="field">
            {t('Основание изменения реестра')}
            <textarea
              required
              maxLength={1000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <label className="ms-check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />{' '}
            {t('Проверены новые счета, изменения сумм, сроков и начальных оплат')}
          </label>
          <button
            className="button button-dark"
            disabled={busy || blocked || !preview.changes.length || !reason.trim() || !confirmed}
          >
            <Check size={16} />
            {t('Подтвердить изменения реестра')}
          </button>
        </form>
      )}
    </section>
  );
}
