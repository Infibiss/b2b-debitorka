import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { FileCheck2, Upload } from 'lucide-react';
import { api, post, type Invoice } from '../api';
import { DeskError, DeskHeading } from './OperationsUI';
import { VoiceCallPanel } from './VoiceCallPanel';
import './yandex.css';

type ServiceStatus = {
  configured: boolean;
  status: string;
  message: string;
  required_roles: string[];
};
type Status = { ocr: ServiceStatus; voice: ServiceStatus };
type DocumentResult = {
  id: string;
  filename: string;
  invoice_id: string | null;
  status: string;
  error_code: string;
  text: string;
  page_count: number;
  source_hash: string;
  acceptance: { text: string; fields: Record<string, string>; reason: string } | null;
};
export type YandexDeskProps = {
  invoices: Invoice[];
  notify: (text: string, error?: boolean) => void;
  invoiceId?: string;
  mode?: 'all' | 'ocr' | 'voice';
  embedded?: boolean;
};
const labels: Record<string, string> = {
  unconfigured: 'Нужно подключение',
  not_checked: 'Права ещё не проверены',
  completed: 'Последний запрос выполнен',
  processing: 'Запрос выполняется',
  unavailable: 'Последний запрос не выполнен',
  permission_required: 'Нужны права Яндекса',
};
const errors: Record<string, string> = {
  permission: 'Нет доступа к сервису. Обратитесь к администратору Mandato.',
  authentication: 'Подключение к Яндексу не работает. Обратитесь к администратору Mandato.',
  rate_limit: 'Достигнут лимит сервиса. Попробуйте позже или обратитесь к администратору Mandato.',
  timeout: 'Яндекс не ответил вовремя. Результат запроса не подтверждён.',
  speech_not_recognized: 'Речь не распознана. Запишите новую короткую реплику или введите текст.',
  invalid_response: 'Ответ Яндекса не прошёл проверку. Результат не подтверждён.',
};
function message(code: string) {
  return errors[code] || 'Не удалось завершить обработку. Попробуйте позже.';
}
function base64(bytes: Uint8Array) {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}
export function YandexDesk({
  invoices,
  notify,
  invoiceId,
  mode = 'all',
  embedded = false,
}: YandexDeskProps) {
  const [status, setStatus] = useState<Status | null>(null),
    [documents, setDocuments] = useState<DocumentResult[]>([]);
  const [selectedInvoice, setSelectedInvoice] = useState(invoiceId || ''),
    [document, setDocument] = useState<DocumentResult | null>(null);
  const [text, setText] = useState(''),
    [number, setNumber] = useState(''),
    [reason, setReason] = useState('');
  const [error, setError] = useState(''),
    [busy, setBusy] = useState('');
  const mounted = useRef(true);
  const reload = useCallback(async () => {
    if (mode === 'voice') return;
    const [nextStatus, nextDocuments] = await Promise.all([
      api<Status>('/yandex/status'),
      api<{ items: DocumentResult[] }>('/yandex/documents'),
    ]);
    if (mounted.current) {
      setStatus(nextStatus);
      setDocuments(nextDocuments.items);
    }
  }, [mode]);
  useEffect(() => {
    mounted.current = true;
    void reload().catch((e: Error) => {
      if (mounted.current) setError(e.message);
    });
    return () => {
      mounted.current = false;
    };
  }, [reload]);
  useEffect(() => {
    setSelectedInvoice(invoiceId || '');
  }, [invoiceId]);
  function review(item: DocumentResult) {
    setDocument(item);
    setText(item.acceptance?.text ?? item.text);
    setNumber(item.acceptance?.fields.number ?? '');
    setReason(item.acceptance?.reason ?? '');
  }
  async function upload(file?: File) {
    if (!file) return;
    setError('');
    if (
      file.size > 1000000 ||
      !['application/pdf', 'image/png', 'image/jpeg'].includes(file.type)
    ) {
      setError('Выберите PDF, PNG или JPEG до 1 МБ. В PDF допускается до пяти страниц.');
      return;
    }
    setBusy('document');
    try {
      const result = await post<DocumentResult>('/yandex/documents', {
        content: base64(new Uint8Array(await file.arrayBuffer())),
        mime_type: file.type,
        filename: file.name,
        invoice_id: selectedInvoice || null,
      });
      review(result);
      await reload();
      if (result.status === 'completed') notify('Текст распознан. Сверьте его с оригиналом.');
      else
        setError(
          result.status === 'processing'
            ? 'Распознавание выполняется. Откройте документ позже.'
            : message(result.error_code)
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  async function accept(event: FormEvent) {
    event.preventDefault();
    if (!document) return;
    setBusy('accept');
    setError('');
    try {
      const result = await post<DocumentResult>(`/yandex/documents/${document.id}/accept`, {
        text,
        fields: number.trim() ? { number: number.trim() } : {},
        reason,
      });
      review(result);
      await reload();
      notify('Проверенная версия сохранена в документах дела.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  function changeInvoice(value: string) {
    setSelectedInvoice(value);
    setError('');
  }
  return (
    <div className={`yx-desk yx-mode-${mode}`}>
      {!embedded && (
        <DeskHeading
          eyebrow=""
          title={
            mode === 'ocr'
              ? 'Распознавание документов'
              : mode === 'voice'
                ? 'Голосовой агент'
                : 'Документы и звонки'
          }
        >
          {mode === 'ocr'
            ? 'Извлеките текст из скана и проверьте результат перед использованием.'
            : 'Подготовьте звонок представителю контрагента и проверьте подключение телефонии.'}
        </DeskHeading>
      )}
      <DeskError>{error}</DeskError>
      <label className="field yx-invoice">
        {mode === 'ocr' ? 'Счёт для документа' : 'Счёт для звонка'}
        <select
          aria-label={mode === 'ocr' ? 'Счёт для документа' : 'Счёт для звонка'}
          value={selectedInvoice}
          onChange={(e) => changeInvoice(e.target.value)}
          disabled={!!busy}
        >
          <option value="">{mode === 'ocr' ? 'Без привязки к счёту' : 'Выберите счёт'}</option>
          {invoices.map((invoice) => (
            <option key={invoice.id} value={invoice.id}>
              {invoice.company} · № {invoice.number}
            </option>
          ))}
        </select>
      </label>
      <div className="yx-columns">
        {mode !== 'voice' && (
          <section className="yx-card" aria-labelledby="yx-documents-title">
            <div className="yx-title">
              <FileCheck2 size={22} />
              <h2 id="yx-documents-title">Загрузить скан</h2>
            </div>
            <Connection status={status?.ocr} />
            <p>
              Загрузите договор, акт или счёт. Поддерживаются PDF до пяти страниц, PNG и JPEG до 1
              МБ.
            </p>
            <label
              className={`button button-outline yx-upload ${!status?.ocr.configured || busy ? 'yx-disabled' : ''}`}
            >
              <Upload size={16} />
              {busy === 'document' ? 'Распознаём…' : 'Выбрать документ'}
              <input
                aria-label="Загрузить документ для распознавания"
                type="file"
                accept="application/pdf,image/png,image/jpeg"
                disabled={!status?.ocr.configured || !!busy}
                onChange={(event) => {
                  void upload(event.target.files?.[0]);
                  event.target.value = '';
                }}
              />
            </label>
            <details className="yx-note">
              <summary>Лимит распознавания</summary>
              <p>
                10 страниц в день на сотрудника и 20 на компанию. Неудачные запросы тоже
                учитываются.
              </p>
            </details>
            <ul className="yx-documents">
              {documents
                .filter((item) => !selectedInvoice || item.invoice_id === selectedInvoice)
                .map((item) => (
                  <li key={item.id}>
                    <button className="yx-document-link" onClick={() => review(item)}>
                      {item.filename}
                      <small>
                        {item.acceptance
                          ? 'Проверен человеком'
                          : labels[item.status] || item.status}{' '}
                        · {item.page_count} стр.
                      </small>
                    </button>
                  </li>
                ))}
            </ul>
          </section>
        )}
        {mode !== 'ocr' && <VoiceCallPanel key={selectedInvoice} invoiceId={selectedInvoice} />}
      </div>
      {document && (
        <section className="yx-card yx-review" aria-labelledby="yx-review-title">
          <div className="yx-title">
            <h2 id="yx-review-title">Проверка: {document.filename}</h2>
            <a
              className="button button-outline"
              href={`/api/yandex/documents/${document.id}/original`}
              download
            >
              Скачать оригинал
            </a>
          </div>
          <p className="yx-note">
            {document.page_count} стр. Сверьте текст и реквизиты с оригиналом.
          </p>
          {document.status !== 'completed' && (
            <p className="yx-warning">
              {document.status === 'processing'
                ? 'Распознавание ещё не завершено. Откройте документ позже.'
                : message(document.error_code)}
            </p>
          )}
          <form onSubmit={(event) => void accept(event)}>
            <label className="field">
              Распознанный текст — исправьте ошибки
              <textarea
                className="yx-ocr-text"
                value={text}
                maxLength={30000}
                readOnly={!!document.acceptance}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <div className="yx-review-fields">
              <label className="field">
                Проверенный номер документа
                <input
                  value={number}
                  maxLength={1000}
                  readOnly={!!document.acceptance}
                  onChange={(e) => setNumber(e.target.value)}
                />
              </label>
              <label className="field">
                Что проверено по оригиналу
                <input
                  required
                  value={reason}
                  maxLength={1000}
                  readOnly={!!document.acceptance}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
            </div>
            {document.acceptance ? (
              <p role="status">Проверенная версия сохранена.</p>
            ) : (
              <button
                className="button button-dark"
                disabled={!!busy || document.status !== 'completed' || !reason.trim()}
              >
                Сохранить проверенную версию
              </button>
            )}
          </form>
        </section>
      )}
    </div>
  );
}
function Connection({ status }: { status?: ServiceStatus }) {
  if (!status)
    return (
      <p className="yx-connection yx-connection-neutral" role="status">
        Проверяем настройки подключения…
      </p>
    );
  return (
    <div
      className={`yx-connection ${status.status === 'completed' ? 'yx-connection-success' : status.status === 'unavailable' ? 'yx-connection-error' : ['unconfigured', 'permission_required', 'not_checked'].includes(status.status) ? 'yx-connection-missing' : 'yx-connection-neutral'}`}
      role="status"
    >
      <strong>{labels[status.status] || status.status}</strong>
      <span>
        {status.status === 'unconfigured'
          ? 'Для работы нужно подключить сервис. Обратитесь к администратору Mandato.'
          : status.status === 'not_checked'
            ? 'Подключение будет проверено при первом запросе.'
            : status.status === 'permission_required'
              ? 'Нужно проверить доступ к сервису. Обратитесь к администратору Mandato.'
              : status.status === 'processing'
                ? 'Обработка запроса ещё не завершена.'
                : status.status === 'unavailable'
                  ? 'Обработка не завершена. Попробуйте позже.'
                  : status.status === 'completed'
                    ? 'Последний запрос обработан успешно.'
                    : status.message}
      </span>
      {['unconfigured', 'permission_required'].includes(status.status) &&
        status.required_roles.length > 0 && (
          <details>
            <summary>Настройки для администратора</summary>
            <small>Роли в Yandex Cloud: {status.required_roles.join(', ')}</small>
          </details>
        )}
    </div>
  );
}
