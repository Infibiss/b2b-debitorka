import { useEffect, useState } from 'react';
import { api, post, today, dateText } from '../api';
import { navigate, useRouteField, useWorkContext } from '../navigation';
import {
  DeskHeading,
  OperationForm,
  InvoiceSelect,
  DeskError,
  value,
  type DeskProps,
} from './OperationsUI';
import { YandexDesk } from './YandexDesk';

type Document = {
  id: string;
  invoice_id: string;
  reference: string;
  kind: string;
  occurred_on: string;
  download_url?: string;
  source: string;
  case_id?: string;
};
const kinds: Record<string, string> = {
  contract: 'Договор',
  performance: 'УПД, накладная или акт',
  payment_terms: 'Условия оплаты',
  reconciliation: 'Акт сверки',
  correspondence: 'Переписка',
  other: 'Другой документ',
};
export function DocumentsDesk({ invoices, onChanged, notify }: DeskProps) {
  const { invoiceId } = useWorkContext();
  const [mode, setMode] = useRouteField<string>('documentsTab', 'archive');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    api<{ items: Document[] }>(
      `/portfolio/documents${invoiceId ? `?invoice_id=${encodeURIComponent(invoiceId)}` : ''}`
    )
      .then((r) => {
        if (alive) {
          setDocuments(r.items);
          setError('');
        }
      })
      .catch((e) => {
        if (alive) setError((e as Error).message);
      });
    return () => {
      alive = false;
    };
  }, [invoiceId, version]);
  return (
    <>
      <DeskHeading eyebrow="ДОКУМЕНТЫ КОМПАНИИ" title="Документы">
        Договоры, первичка, доказательства и подготовленные юридические документы в одном архиве.
      </DeskHeading>
      <div className="ops-tabs">
        <button onClick={() => setMode('archive')} aria-pressed={mode === 'archive'}>
          Архив и загрузка
        </button>
        <button onClick={() => setMode('recognition')} aria-pressed={mode === 'recognition'}>
          Распознавание
        </button>
      </div>
      {mode === 'recognition' ? (
        <YandexDesk
          mode="ocr"
          key={invoiceId}
          invoiceId={invoiceId || undefined}
          invoices={invoices}
          notify={notify}
        />
      ) : (
        <>
          <DeskError>{error}</DeskError>
          <section className="ops-card">
            <h2>Добавить договор или документ</h2>
            <p>
              Выберите счёт, укажите реквизиты и при необходимости приложите файл. Документ появится
              также в деле и аудите.
            </p>
            <OperationForm
              resetOnSave
              key={invoiceId}
              draftKey={`document:${invoiceId || 'new'}`}
              label="Добавить документ"
              submit={async (data) => {
                const file = data.get('attachment');
                let content = '';
                if (file instanceof File && file.size) {
                  if (file.size > 1_000_000)
                    throw new Error(
                      'Файл должен быть до 1 МБ. Большой документ зарегистрируйте по реквизитам или ссылке на архив.'
                    );
                  const bytes = new Uint8Array(await file.arrayBuffer());
                  let binary = '';
                  for (let i = 0; i < bytes.length; i += 8192)
                    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
                  content = btoa(binary);
                }
                await post(`/portfolio/invoices/${value(data, 'invoice_id')}/evidence`, {
                  kind: value(data, 'kind'),
                  reference: value(data, 'reference'),
                  occurred_on: value(data, 'occurred_on'),
                  note: value(data, 'note'),
                  filename: file instanceof File ? file.name : '',
                  content_base64: content,
                });
              }}
              onDone={() => {
                setVersion((v) => v + 1);
                onChanged();
                notify('Документ добавлен в архив и дело');
              }}
            >
              <InvoiceSelect invoices={invoices} />
              <label className="field">
                Вид документа
                <select name="kind">
                  {Object.entries(kinds).map(([key, title]) => (
                    <option key={key} value={key}>
                      {title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Дата документа
                <input
                  name="occurred_on"
                  type="date"
                  required
                  max={today()}
                  defaultValue={today()}
                />
              </label>
              <label className="field full-width">
                Номер, название или ссылка на архив
                <input name="reference" required minLength={3} maxLength={1000} />
              </label>
              <label className="field full-width">
                Комментарий
                <textarea name="note" maxLength={3000} />
              </label>
              <label className="field full-width">
                Файл · PDF, PNG, JPEG до 1 МБ
                <input type="file" name="attachment" accept=".pdf,.png,.jpg,.jpeg" />
              </label>
            </OperationForm>
          </section>
          <section className="ops-card">
            <h2>{invoiceId ? 'Документы выбранной задолженности' : 'Все документы'}</h2>
            {!documents.length && <p>Документов пока нет. Добавьте первый договор выше.</p>}
            {documents.map((doc) => (
              <article className="portfolio-document" key={`${doc.source}:${doc.id}`}>
                <div>
                  <strong>{doc.reference || kinds[doc.kind] || doc.kind}</strong>
                  <p>
                    {invoices.find((i) => i.id === doc.invoice_id)?.company} ·{' '}
                    {invoices.find((i) => i.id === doc.invoice_id)?.number} ·{' '}
                    {dateText(doc.occurred_on)}
                  </p>
                  <small>{doc.source}</small>
                  <div>
                    {doc.download_url && <a href={doc.download_url}>Скачать файл</a>}{' '}
                    {doc.case_id && (
                      <button
                        className="wf-text-button"
                        onClick={() =>
                          navigate({
                            section: 'legal',
                            legal: doc.case_id!,
                            context: doc.invoice_id,
                            legalTab:
                              doc.source === 'Доказательство' ? 'Доказательства' : 'Документы',
                          })
                        }
                      >
                        Открыть в юридическом деле
                      </button>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </section>
        </>
      )}
    </>
  );
}
