import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  ArrowRight,
  ClipboardCheck,
  Download,
  FilePlus2,
  FileSpreadsheet,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  X,
} from 'lucide-react';
import { api, post, money, dateText, today, type Invoice } from '../api';
import { AccountingDesk } from './AccountingDesk';
import { ImportInvoices } from './InvoiceForms';
import './operations.css';
import './portfolio.css';

type Finding = {
  code: string;
  severity: string;
  title: string;
  detail: string;
  next_step: string;
  evidence: { source: string; reference: string; as_of?: string; amount?: number }[];
};
type Deadline = { id: string; review_on: string; basis: string; kind: string };
type Item = {
  invoice_id: string;
  counterparty_id: string;
  company: string;
  inn: string;
  number: string;
  due_on: string;
  balance: number;
  severity: string;
  days_overdue: number;
  findings: Finding[];
  documents: string[];
  deadlines: Deadline[];
  economics: {
    claim_duty: number;
    court_order_duty: number | null;
  };
  registry: {
    status: string;
    checked_at: string | null;
    fresh: boolean;
    registration_status: string;
  };
  next_action: { code: string; title: string; detail: string };
};
type Audit = {
  id: string;
  latest?: string | null;
  created_at: string;
  as_of: string;
  stale?: boolean;
  items: Item[];
  findings: Finding[];
  totals: {
    invoice_count: number;
    counterparty_count: number;
    outstanding: number;
    overdue: number;
    unallocated_cash: number;
    urgent_count: number;
    discrepancies: number;
    missing_documents: number;
    unchecked_debtors: number;
  };
};
type History = { id: string; created_at: string; totals: Audit['totals'] };
type Evidence = {
  id: string;
  kind: string;
  reference: string;
  occurred_on: string;
  note: string;
  filename: string;
  sha256: string;
  download_url: string | null;
};
const evidenceNames: Record<string, string> = {
  contract: 'Договор',
  performance: 'Исполнение: УПД, накладная или акт',
  payment_terms: 'Условия и срок оплаты',
  reconciliation: 'Акт сверки',
  correspondence: 'Переписка',
  other: 'Другой документ',
};
const severityNames: Record<string, string> = {
  urgent: 'Срочно',
  attention: 'Требует внимания',
  review: 'Нужно проверить',
  clear: 'Без замечаний',
};

export function PortfolioDesk({
  invoices,
  onChanged,
  notify,
  onOpenInvoice,
  onNavigate,
}: {
  invoices: Invoice[];
  onChanged: () => void;
  notify: (text: string, error?: boolean) => void;
  onOpenInvoice: (id: string) => void;
  onNavigate: (tab: 'registry' | 'finance' | 'legal' | 'agent' | 'connections') => void;
}) {
  const [report, setReport] = useState<Audit | null>(null),
    [history, setHistory] = useState<History[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(''),
    [severity, setSeverity] = useState(''),
    [selected, setSelected] = useState<string | null>(null),
    [documents, setDocuments] = useState<Evidence[]>([]),
    [intake, setIntake] = useState<'registry' | 'accounting' | null>(null),
    [historical, setHistorical] = useState(false);
  const reload = useCallback(async () => {
    try {
      const [latest, saved] = await Promise.all([
        api<Audit & { latest: string | null }>('/portfolio'),
        api<{ items: History[] }>('/portfolio/runs'),
      ]);
      setReport(latest.latest ? latest : null);
      setHistory(saved.items);
      setHistorical(false);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload, invoices]);
  useEffect(() => {
    let current = true;
    setDocuments([]);
    if (selected)
      void api<{ items: Evidence[] }>(`/portfolio/invoices/${selected}/evidence`)
        .then((r) => {
          if (current) setDocuments(r.items);
        })
        .catch((e) => {
          if (current) setError((e as Error).message);
        });
    return () => {
      current = false;
    };
  }, [selected, report?.id]);
  async function run() {
    setBusy(true);
    setError('');
    try {
      const result = await post<Audit>('/portfolio/runs');
      setReport(result);
      setHistorical(false);
      setHistory((await api<{ items: History[] }>('/portfolio/runs')).items);
      notify('Аудит обновлён');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function openHistory(id: string) {
    if (!id) return;
    setBusy(true);
    try {
      setReport(await api<Audit>(`/portfolio/runs/${id}`));
      setHistorical(true);
      setSelected(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const item = report?.items.find((x) => x.invoice_id === selected);
  async function addEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!item) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const attachment = values.get('attachment');
    const file = attachment instanceof File && attachment.size > 0 ? attachment : null;
    const data = Object.fromEntries(values);
    setBusy(true);
    setError('');
    try {
      let content = '';
      if (file) {
        if (file.size > 1_000_000)
          throw new Error(
            'Выберите PDF или изображение до 1 МБ. Большой документ можно зарегистрировать по реквизитам.'
          );
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = '';
        for (let i = 0; i < bytes.length; i += 8192)
          binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        content = btoa(binary);
      }
      await post(`/portfolio/invoices/${item.invoice_id}/evidence`, {
        kind: data.kind,
        reference: data.reference,
        occurred_on: data.occurred_on,
        note: data.note || '',
        filename: file?.name || '',
        content_base64: content,
      });
      form.reset();
      await run();
      onChanged();
      notify('Документ зарегистрирован');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function addDeadline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!item) return;
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    setBusy(true);
    try {
      await post(`/portfolio/invoices/${item.invoice_id}/deadlines`, data);
      form.reset();
      await run();
      notify('Контрольная дата сохранена');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function resolve(deadline: Deadline, reason: string) {
    setBusy(true);
    try {
      await post(`/portfolio/deadlines/${deadline.id}/resolve`, { reason });
      await run();
      notify('Результат проверки сохранён');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function checkDebtor(inn: string) {
    setBusy(true);
    setError('');
    try {
      const result = await post<{ status: string; message: string }>(
        '/integrations/registry/check',
        { inn }
      );
      await run();
      notify(result.message, result.status !== 'completed');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const visible = (report?.items || []).filter(
    (x) =>
      (!severity || x.severity === severity) &&
      `${x.company} ${x.inn} ${x.number}`.toLowerCase().includes(query.toLowerCase())
  );
  return (
    <section className="portfolio-desk" data-tour="audit-content">
      <div className="page-heading ops-heading">
        <div>
          <span className="page-date">ПОРТФЕЛЬ ПОД КОНТРОЛЕМ</span>
          <h1>Аудит дебиторки.</h1>
          <p>Сверьте суммы, проверьте документы и выберите следующий шаг по каждому долгу.</p>
        </div>
        <div className="portfolio-actions" data-tour="audit-actions">
          <button
            className="button button-outline"
            disabled={busy}
            onClick={() => setIntake(intake ? null : 'registry')}
          >
            <Upload size={16} />
            Загрузить портфель
          </button>
          <button className="button button-dark" disabled={busy} onClick={() => void run()}>
            <RefreshCw size={16} />
            {busy ? 'Проверяем…' : report ? 'Обновить аудит' : 'Собрать аудит'}
          </button>
        </div>
      </div>
      {error && (
        <div className="page-error" role="alert">
          {error}
          <button onClick={() => setError('')}>Закрыть</button>
        </div>
      )}
      {intake && (
        <div className="ops-card">
          <div className="ops-card-heading">
            <div>
              <h2>Загрузка портфеля</h2>
              <p>Расшифровка по счетам и остатки из учёта дополняют друг друга.</p>
            </div>
            <button
              className="icon-button"
              aria-label="Закрыть загрузку"
              onClick={() => setIntake(null)}
            >
              <X size={18} />
            </button>
          </div>
          <div className="portfolio-intake-choices">
            <button className="button button-outline" onClick={() => setIntake('registry')}>
              <FileSpreadsheet size={16} />
              Реестр счетов
            </button>
            <button className="button button-outline" onClick={() => setIntake('accounting')}>
              <ClipboardCheck size={16} />
              ОСВ и акты сверки
            </button>
            <button className="button button-outline" onClick={() => onNavigate('connections')}>
              Из подключённой системы
              <ArrowRight size={16} />
            </button>
          </div>
          {intake === 'accounting' && (
            <AccountingDesk
              onSaved={() => {
                onChanged();
                void run();
              }}
            />
          )}
        </div>
      )}
      {intake === 'registry' && (
        <ImportInvoices
          onClose={() => setIntake(null)}
          onDone={() => {
            setIntake(null);
            onChanged();
            void run();
          }}
        />
      )}
      {loading ? (
        <div className="ops-card">
          <p role="status">Собираем данные портфеля…</p>
        </div>
      ) : !report ? (
        <div className="portfolio-empty">
          <ClipboardCheck size={34} />
          <h2>{invoices.length ? 'Ваш портфель готов к проверке' : 'Начните с портфеля'}</h2>
          <p>
            {invoices.length
              ? 'Аудит соберёт остатки, первичные документы и контрольные даты в один план.'
              : 'Загрузите счета и выгрузку из учёта. Система покажет расхождения и документы, которые нужно найти.'}
          </p>
          <button className="button button-dark" onClick={() => void run()} disabled={busy}>
            Проверить портфель
            <ArrowRight size={16} />
          </button>
        </div>
      ) : (
        <>
          {(report.stale || historical) && (
            <div className="portfolio-notice" role="status">
              <RefreshCw size={18} />
              <div>
                <strong>
                  {historical ? 'Сохранённый аудит' : 'Портфель изменился после проверки'}
                </strong>
                <p>
                  {historical
                    ? 'Результат отражает состояние на момент сохранения. Для текущего плана обновите аудит.'
                    : 'Оплаты, документы или сведения об организации обновились. Пересоберите план перед следующим действием.'}
                </p>
              </div>
              <button className="button button-outline" disabled={busy} onClick={() => void run()}>
                Проверить сейчас
              </button>
            </div>
          )}
          <div className="portfolio-metrics">
            <article>
              <span>ОСТАЛОСЬ К ОПЛАТЕ</span>
              <strong>{money(report.totals.outstanding)}</strong>
              <small>
                {report.totals.invoice_count} счетов · {report.totals.counterparty_count}{' '}
                контрагентов
              </small>
            </article>
            <article>
              <span>ПРОСРОЧЕНО</span>
              <strong>{money(report.totals.overdue)}</strong>
              <small>{report.totals.urgent_count} счетов требуют срочной проверки</small>
            </article>
            <article>
              <span>НУЖНО СВЕРИТЬ</span>
              <strong>{report.totals.discrepancies}</strong>
              <small>расхождений с учётными остатками</small>
            </article>
            <article>
              <span>НУЖНЫ ДОКУМЕНТЫ</span>
              <strong>{report.totals.missing_documents}</strong>
              <small>счетов с неполным комплектом</small>
            </article>
          </div>
          {report.findings.length > 0 && (
            <div className="portfolio-global">
              {report.findings.map((f, i) => (
                <article key={`${f.code}-${i}`}>
                  <strong>{f.title}</strong>
                  <p>{f.detail}</p>
                  <small>{f.next_step}</small>
                  <div className="portfolio-evidence">
                    {f.evidence.map((e, j) => (
                      <span key={j}>
                        {e.reference}
                        {e.amount !== undefined ? ` · ${money(e.amount)}` : ''}
                      </span>
                    ))}
                  </div>
                  {f.code === 'unallocated_cash' && (
                    <button className="text-button" onClick={() => onNavigate('finance')}>
                      Разобрать поступления
                      <ArrowRight size={14} />
                    </button>
                  )}
                </article>
              ))}
            </div>
          )}
          <div className="portfolio-toolbar" data-tour="audit-findings">
            <label className="portfolio-search">
              <Search size={16} />
              <input
                aria-label="Поиск по аудиту"
                placeholder="Контрагент, ИНН или счёт"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <select
              aria-label="Важность замечаний"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="">Все замечания</option>
              {Object.entries(severityNames).map(([key, name]) => (
                <option key={key} value={key}>
                  {name}
                </option>
              ))}
            </select>
            <a className="button button-outline" href={`/api/portfolio/runs/${report.id}/export`}>
              <Download size={15} />
              Скачать отчёт
            </a>
          </div>
          <div className="portfolio-list">
            {visible.map((row) => (
              <button
                className={`portfolio-row ${selected === row.invoice_id ? 'selected' : ''}`}
                key={row.invoice_id}
                disabled={busy}
                onClick={() => setSelected(row.invoice_id)}
              >
                <span className={`portfolio-dot ${row.severity}`} />
                <span className="portfolio-buyer">
                  <strong>{row.company}</strong>
                  <small>
                    № {row.number} · {row.inn ? `ИНН ${row.inn}` : 'ИНН не указан'}
                  </small>
                </span>
                <span className="portfolio-row-money">
                  <strong>{money(row.balance)}</strong>
                  <small>
                    {row.days_overdue
                      ? `${row.days_overdue} дней просрочки`
                      : `Срок ${dateText(row.due_on)}`}
                  </small>
                </span>
                <span className="portfolio-next">
                  <strong>{row.next_action.title}</strong>
                  <small>{severityNames[row.severity]}</small>
                </span>
                <ArrowRight size={16} />
              </button>
            ))}
            {visible.length === 0 && (
              <p className="portfolio-empty-result">По выбранным условиям счетов нет.</p>
            )}
          </div>
          {item && (
            <div className="portfolio-detail" key={`${report.id}:${item.invoice_id}`}>
              <div className="ops-card-heading">
                <div>
                  <span className="page-date">СЧЁТ № {item.number}</span>
                  <h2>{item.company}</h2>
                  <p>{item.next_action.detail}</p>
                </div>
                <button
                  className="icon-button"
                  aria-label="Закрыть подробности аудита"
                  disabled={busy}
                  onClick={() => setSelected(null)}
                >
                  <X size={18} />
                </button>
              </div>
              <div className="portfolio-actions" data-tour="audit-actions">
                <button
                  className="button button-outline"
                  onClick={() => onOpenInvoice(item.invoice_id)}
                >
                  Карточка счёта
                  <ArrowRight size={14} />
                </button>
                <button
                  className="button button-outline"
                  disabled={busy || !item.inn}
                  onClick={() => void checkDebtor(item.inn)}
                >
                  <ShieldCheck size={15} />
                  Обновить проверку ИНН
                </button>
                {item.next_action.code === 'lawyer_review' && (
                  <button className="button button-dark" onClick={() => onNavigate('legal')}>
                    Перейти к делу
                    <ArrowRight size={14} />
                  </button>
                )}
              </div>
              <div className="ops-context">
                <strong>
                  Регистрация должника:{' '}
                  {item.registry.status === 'completed' && item.registry.fresh
                    ? {
                        ACTIVE: 'действует',
                        LIQUIDATING: 'ликвидируется',
                        LIQUIDATED: 'деятельность прекращена',
                        BANKRUPT: 'банкротство в сведениях о регистрации',
                        REORGANIZING: 'реорганизация',
                      }[item.registry.registration_status] || 'статус требует уточнения'
                    : 'нужна актуальная проверка'}
                </strong>
                <p>
                  {item.registry.checked_at
                    ? `Запрос ${new Date(item.registry.checked_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })}. `
                    : ''}
                  Сведения ЕГРЮЛ/ЕГРИП — по данным источника. Судебные дела, исполнительные
                  производства и полный реестр банкротств проверяются отдельно.
                </p>
                <button className="button button-outline" onClick={() => onNavigate('connections')}>
                  Посмотреть источники
                </button>
              </div>
              {item.balance > 0 && item.economics && (
                <details className="ops-context">
                  <summary>Судебные расходы от текущего основного долга</summary>
                  <p>
                    Пошлина по иску: {money(item.economics.claim_duty)}.
                    {item.economics.court_order_duty !== null
                      ? ` По судебному приказу: ${money(item.economics.court_order_duty)}.`
                      : ''}{' '}
                    Проценты, расходы представителя и льготы здесь не учтены. Допустимость процедуры
                    проверяет юрист.
                  </p>
                </details>
              )}
              <div className="portfolio-findings">
                {item.findings.map((f) => (
                  <article key={f.code} className={`portfolio-finding ${f.severity}`}>
                    <span>{severityNames[f.severity]}</span>
                    <h3>{f.title}</h3>
                    <p>{f.detail}</p>
                    <strong>{f.next_step}</strong>
                    <div className="portfolio-evidence">
                      {f.evidence.map((e, j) => (
                        <small key={j}>
                          {e.reference}
                          {e.as_of ? ` · ${dateText(e.as_of)}` : ''}
                        </small>
                      ))}
                    </div>
                  </article>
                ))}
                {!item.findings.length && <p>По доступным данным замечаний нет.</p>}
              </div>
              <div className="portfolio-detail-columns">
                <section>
                  <h3>Подтверждающие документы</h3>
                  <p className="ops-muted">
                    Зарегистрируйте реквизиты документа или приложите файл из своего архива.
                  </p>
                  {documents.map((doc) => (
                    <div className="portfolio-document" key={doc.id}>
                      <FilePlus2 size={17} />
                      <div>
                        <strong>{evidenceNames[doc.kind]}</strong>
                        <p>
                          {doc.reference} · {dateText(doc.occurred_on)}
                        </p>
                        {doc.download_url && <a href={doc.download_url}>Скачать документ</a>}
                      </div>
                    </div>
                  ))}
                  <form className="ops-form" onSubmit={(e) => void addEvidence(e)}>
                    <fieldset disabled={busy}>
                      <label className="field">
                        Вид документа
                        <select name="kind">
                          {Object.entries(evidenceNames).map(([key, title]) => (
                            <option key={key} value={key}>
                              {title}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        Номер, название или ссылка на архив
                        <input required name="reference" minLength={3} maxLength={1000} />
                      </label>
                      <label className="field">
                        Дата документа
                        <input
                          required
                          type="date"
                          name="occurred_on"
                          max={today()}
                          defaultValue={today()}
                        />
                      </label>
                      <label className="field">
                        Комментарий к документу
                        <textarea name="note" maxLength={3000} />
                      </label>
                      <label className="field">
                        Файл документа
                        <input type="file" accept=".pdf,.png,.jpg,.jpeg" name="attachment" />
                        <small>PDF, PNG или JPEG до 1 МБ</small>
                      </label>
                      <button className="button button-dark" type="submit">
                        Сохранить документ
                        <ClipboardCheck size={15} />
                      </button>
                    </fieldset>
                  </form>
                </section>
                <section>
                  <h3>Контрольные даты</h3>
                  {item.deadlines.map((deadline) => (
                    <div className="portfolio-deadline" key={deadline.id}>
                      <strong>{dateText(deadline.review_on)}</strong>
                      <p>{deadline.basis}</p>
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          void resolve(
                            deadline,
                            String(new FormData(e.currentTarget).get('reason'))
                          );
                        }}
                      >
                        <label className="field">
                          Результат проверки
                          <input name="reason" minLength={10} required maxLength={2000} />
                        </label>
                        <button className="button button-outline" disabled={busy} type="submit">
                          Завершить проверку
                        </button>
                      </form>
                    </div>
                  ))}
                  <form className="ops-form" onSubmit={(e) => void addDeadline(e)}>
                    <fieldset disabled={busy}>
                      <label className="field">
                        Что проверить
                        <select name="kind">
                          <option value="limitation_review">Исковая давность</option>
                          <option value="claim_review">Претензионный этап</option>
                          <option value="court_review">Судебное дело</option>
                          <option value="other">Другая проверка</option>
                        </select>
                      </label>
                      <label className="field">
                        Дата проверки
                        <input required type="date" name="review_on" />
                      </label>
                      <label className="field">
                        Основание и поручение
                        <textarea required minLength={10} maxLength={2000} name="basis" />
                      </label>
                      <button className="button button-outline" type="submit">
                        Назначить проверку
                        <ArrowRight size={15} />
                      </button>
                    </fieldset>
                  </form>
                </section>
              </div>
            </div>
          )}
          <footer className="portfolio-footer">
            <span>
              Проверено{' '}
              {new Date(report.created_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })}
            </span>
            <label>
              История аудитов
              <select
                aria-label="История аудитов"
                value={report.id}
                disabled={busy}
                onChange={(e) => void openHistory(e.target.value)}
              >
                {history.map((h) => (
                  <option value={h.id} key={h.id}>
                    {new Date(h.created_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })}
                  </option>
                ))}
              </select>
            </label>
          </footer>
        </>
      )}
    </section>
  );
}
