import { t } from '../i18n';
import { useRef, useState, type FormEvent } from 'react';
import { Upload, Download, Check, AlertCircle, FileSpreadsheet, ArrowRight } from 'lucide-react';
import { Dialog } from './Dialog';
import { post, today, toKopeks, money, type Invoice } from '../api';
export function CreateInvoice({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.currentTarget));
    setError('');
    setBusy(true);
    try {
      await post('/invoices', { ...data, amount: toKopeks(String(data.amount)) });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={t('Новый счёт')} onClose={onClose}>
      <p className="dialog-intro">
        {t('Добавьте неоплаченный счёт. Дальнейшая работа будет храниться в его карточке.')}
      </p>
      <form onSubmit={submit} className="form-grid">
        <label className="field full-width">
          {t('Контрагент')}
          <input required name="company" placeholder={t('ООО «Северстрой»')} maxLength={160} />
        </label>
        <label className="field">
          {t('ИНН')}
          <input
            name="inn"
            inputMode="numeric"
            pattern="[0-9]{10}|[0-9]{12}|^$"
            placeholder={t('10 или 12 цифр')}
            maxLength={12}
          />
        </label>
        <label className="field">
          {t('Email покупателя')}
          <input type="email" name="email" placeholder="buh@company.ru" />
        </label>
        <label className="field">
          {t('Номер счёта')}
          <input required name="number" placeholder={t('СЧ-417')} maxLength={80} />
        </label>
        <label className="field">
          {t('Сумма')}
          <input
            required
            name="amount"
            inputMode="decimal"
            type="text"
            placeholder="480000,00"
            pattern="[0-9]+([,.][0-9]{1,2})?"
          />
        </label>
        <label className="field">
          {t('Дата счёта')}
          <input required type="date" name="issued_on" defaultValue={today()} />
        </label>
        <label className="field">
          {t('Оплатить до')}
          <input required type="date" name="due_on" defaultValue={today()} />
        </label>
        {error && (
          <p className="form-error full-width" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions full-width">
          <button className="button button-outline" type="button" onClick={onClose}>
            {t('Отмена')}
          </button>
          <button className="button button-dark" disabled={busy} type="submit">
            {busy ? t('Сохраняем…') : t('Добавить счёт')}
            <Check size={16} />
          </button>
        </div>
      </form>
    </Dialog>
  );
}
const template = t(
  'контрагент;инн;email;номер;дата;срок;сумма\nООО «Покупатель»;7701234567;buh@example.ru;СЧ-001;01.10.2026;15.10.2026;150000,00\n'
);
export function downloadTemplate() {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['\ufeff' + template], { type: 'text/csv;charset=utf-8' }));
  a.download = 'mandato-template.csv';
  a.click();
  URL.revokeObjectURL(a.href);
}
export function ImportInvoices({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null),
    [content, setContent] = useState(''),
    [name, setName] = useState(''),
    [preview, setPreview] = useState<{
      items: Partial<Invoice>[];
      errors: { row: number; message: string }[];
      duplicate_count: number;
    } | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function readFile(file?: File) {
    if (!file) return;
    setError('');
    setPreview(null);
    setContent('');
    if (file.size > 2 * 1024 * 1024) {
      setError(t('Файл больше 2 МБ. Разделите реестр на несколько файлов.'));
      return;
    }
    setName(file.name);
    setBusy(true);
    try {
      const text = await file.text();
      const result = await post<NonNullable<typeof preview>>('/invoices/import/preview', {
        content: text,
      });
      setContent(text);
      setPreview(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    setBusy(true);
    setError('');
    try {
      const result = await post<{ imported: number; skipped: number }>('/invoices/import', {
        content,
      });
      onDone();
      if (result.imported === 0) setError(t('Все счета уже существуют.'));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={t('Импорт реестра')} onClose={onClose} wide>
      <p className="dialog-intro">
        {t(
          'Загрузите CSV из учётной системы. Мы проверим даты, суммы и повторяющиеся счета до сохранения.'
        )}
      </p>
      <button className="template-download" onClick={downloadTemplate}>
        <Download size={15} />
        {t('Скачать шаблон CSV')}
        <ArrowRight size={14} />
      </button>
      <label className={`upload-zone ${busy ? 'is-busy' : ''}`}>
        <Upload size={29} />
        <strong>
          {busy ? t('Проверяем реестр…') : name || t('Выберите файл или перетащите сюда')}
        </strong>
        <span>{t('CSV · UTF-8 · до 2 МБ')}</span>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => void readFile(e.target.files?.[0])}
        />
      </label>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {preview && (
        <div className="import-preview">
          <div className="import-summary">
            <span>
              <FileSpreadsheet size={15} />
              {preview.items.length} {t('счетов в файле')}
            </span>
            {preview.duplicate_count > 0 && (
              <span className="duplicate-note">
                {preview.duplicate_count} {t('повторов — пропустим')}
              </span>
            )}
          </div>
          {preview.errors.length > 0 ? (
            <div className="import-errors" role="alert">
              <strong>
                <AlertCircle size={15} />
                {t('Есть ошибки в реестре')}
              </strong>
              {preview.errors.slice(0, 8).map((e, i) => (
                <p key={i}>
                  {t('Строка')} {e.row}: {e.message}
                </p>
              ))}
            </div>
          ) : (
            <div className="import-list">
              {preview.items.slice(0, 5).map((item, i) => (
                <div key={i}>
                  <span>
                    {item.company}
                    <small>{item.number}</small>
                  </span>
                  <b>{money(item.amount || 0)}</b>
                </div>
              ))}
              {preview.items.length > 5 && (
                <p>
                  {t('И ещё')} {preview.items.length - 5} {t('счетов')}
                </p>
              )}
            </div>
          )}
        </div>
      )}
      <div className="dialog-actions">
        <button className="button button-outline" onClick={onClose}>
          {t('Отмена')}
        </button>
        <button
          disabled={!preview || preview.errors.length > 0 || preview.items.length === 0 || busy}
          className="button button-dark"
          onClick={() => void submit()}
        >
          {t('Импортировать')}
          <Check size={16} />
        </button>
      </div>
    </Dialog>
  );
}
