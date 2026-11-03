import { useEffect, useRef, useState } from 'react';
import { FileInput } from './FileInput';
import { ArrowRight, FileSpreadsheet } from 'lucide-react';
import { api, post, money, dateText, today } from '../api';
import { DeskError, EmptyCard, OperationForm, value } from './OperationsUI';

type Column = { key: string; label: string };
type SourceItem = {
  row: number;
  company: string;
  inn: string;
  source_balance: number;
  ledger_current_balance: number;
  discrepancy: number;
  requires_review: boolean;
};
type Preview = {
  id: string;
  columns: Column[];
  items: SourceItem[];
  errors: { row: number; message: string }[];
};
type Saved = SourceItem & {
  id: string;
  source_ref: string;
  as_of: string;
  source_type: string;
  reason: string;
};
const fields = [
  ['company', 'Контрагент'],
  ['inn', 'ИНН'],
  ['opening_debit', 'Начальное сальдо, дебет'],
  ['opening_credit', 'Начальное сальдо, кредит'],
  ['debit_turnover', 'Оборот, дебет'],
  ['credit_turnover', 'Оборот, кредит'],
  ['ending_debit', 'Конечное сальдо, дебет'],
  ['ending_credit', 'Конечное сальдо, кредит'],
] as const;
const guesses: Record<string, RegExp> = {
  company: /^(контрагент|покупатель|наименование)$/i,
  inn: /^инн$/i,
  opening_debit: /начал.*дебет/i,
  opening_credit: /начал.*кредит/i,
  debit_turnover: /оборот.*дебет/i,
  credit_turnover: /оборот.*кредит/i,
  ending_debit: /конеч.*дебет|^остаток$|^задолженность$/i,
  ending_credit: /конеч.*кредит/i,
};

export function AccountingDesk({ onSaved }: { onSaved: () => void }) {
  const fileRequest = useRef(0);
  const [sourceType, setSourceType] = useState('osv62'),
    [sourceRef, setSourceRef] = useState(''),
    [asOf, setAsOf] = useState(today());
  const [format, setFormat] = useState<'csv' | 'xlsx'>('csv'),
    [content, setContent] = useState(''),
    [fileName, setFileName] = useState(''),
    [header, setHeader] = useState(1),
    [sheet, setSheet] = useState('');
  const [columns, setColumns] = useState<Column[]>([]),
    [mapping, setMapping] = useState<Record<string, string>>({}),
    [preview, setPreview] = useState<Preview | null>(null),
    [selected, setSelected] = useState<number[]>([]);
  const [history, setHistory] = useState<Saved[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function reload() {
    try {
      setHistory((await api<{ items: Saved[] }>('/accounting/reconciliations')).items);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  function reset() {
    setColumns([]);
    setMapping({});
    setPreview(null);
    setSelected([]);
  }
  async function check(mapped: boolean) {
    setBusy(true);
    setError('');
    setPreview(null);
    try {
      const result = await post<Preview>('/accounting/preview', {
        source_type: sourceType,
        source_ref: sourceRef,
        as_of: asOf,
        format,
        content,
        header_row: header,
        ...(sheet ? { sheet } : {}),
        mapping: mapped ? Object.fromEntries(Object.entries(mapping).filter(([, v]) => v)) : {},
      });
      setColumns(result.columns);
      if (!mapped && result.columns.length) {
        const next: Record<string, string> = {};
        for (const [field] of fields) {
          const found = result.columns.find((c) => guesses[field].test(c.label));
          if (found) next[field] = found.key;
        }
        setMapping(next);
      } else {
        setPreview(result);
        const invalid = new Set(result.errors.map((e) => e.row));
        setSelected(result.items.filter((i) => !invalid.has(i.row)).map((i) => i.row));
      }
      if (!result.columns.length && result.errors.length)
        setError(result.errors.map((e) => e.message).join('. '));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="ops-card">
        <div className="ops-card-heading">
          <div>
            <h2>ОСВ 62 и акты сверки</h2>
            <p>
              Сопоставьте остатки по покупателям с реестром и сохраните расхождения для разбора.
            </p>
          </div>
          <FileSpreadsheet size={24} />
        </div>
        <fieldset disabled={busy} className="ops-input-group">
          <div className="form-grid ops-form">
            <label className="field">
              Источник
              <select
                value={sourceType}
                onChange={(e) => {
                  setSourceType(e.target.value);
                  setPreview(null);
                }}
              >
                <option value="osv62">Оборотно-сальдовая ведомость 62</option>
                <option value="reconciliation_act">Акт сверки</option>
              </select>
            </label>
            <label className="field">
              Дата остатков
              <input
                type="date"
                value={asOf}
                max={today()}
                onChange={(e) => {
                  setAsOf(e.target.value);
                  setPreview(null);
                }}
                required
              />
            </label>
            <label className="field full-width">
              Номер или название источника
              <input
                value={sourceRef}
                maxLength={300}
                onChange={(e) => {
                  setSourceRef(e.target.value);
                  setPreview(null);
                }}
                placeholder="ОСВ 62 за октябрь, выгрузка от бухгалтерии"
                required
              />
            </label>
            <label className="field full-width">
              Файл из учётной системы
              <FileInput
                accept=".csv,.txt,.xlsx"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  reset();
                  setError('');
                  if (file.size > 1_000_000) {
                    setError('Файл больше 1 МБ. Разделите выгрузку по покупателям.');
                    return;
                  }
                  const request = ++fileRequest.current;
                  setContent('');
                  const bytes = new Uint8Array(await file.arrayBuffer());
                  if (request !== fileRequest.current) return;
                  setFileName(file.name);
                  if (file.name.toLowerCase().endsWith('.xlsx')) {
                    let binary = '';
                    for (let i = 0; i < bytes.length; i += 32768)
                      binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
                    setContent(btoa(binary));
                    setFormat('xlsx');
                  } else {
                    let text = '';
                    try {
                      text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
                    } catch {
                      text = new TextDecoder('windows-1251').decode(bytes);
                    }
                    setContent(text);
                    setFormat('csv');
                  }
                }}
              />
            </label>
            <label className="field">
              Строка с названиями столбцов
              <input
                type="number"
                min="1"
                max="1000"
                value={header}
                onChange={(e) => {
                  setHeader(Number(e.target.value));
                  reset();
                }}
              />
            </label>
            {format === 'xlsx' && (
              <label className="field">
                Название листа
                <input
                  value={sheet}
                  onChange={(e) => {
                    setSheet(e.target.value);
                    reset();
                  }}
                  placeholder="Первый лист"
                  maxLength={100}
                />
              </label>
            )}
            {format === 'csv' && (
              <label className="field full-width">
                Данные источника
                <textarea
                  rows={5}
                  className="ops-csv"
                  value={content}
                  onChange={(e) => {
                    fileRequest.current++;
                    setContent(e.target.value);
                    reset();
                  }}
                  placeholder="Контрагент;ИНН;Конечное сальдо дебет;Конечное сальдо кредит"
                />
              </label>
            )}
          </div>
          {fileName && <p className="ops-muted">{fileName}</p>}
          <button
            className="button button-outline"
            disabled={busy || !content.trim() || !sourceRef.trim() || !asOf}
            onClick={() => void check(false)}
          >
            Прочитать столбцы
            <ArrowRight size={15} />
          </button>
          {!!columns.length && (
            <div className="ops-preview">
              <h3>Сопоставление столбцов</h3>
              <div className="ops-mapping">
                {fields.map(([field, label]) => (
                  <label className="field" key={field}>
                    {label}
                    <select
                      value={mapping[field] || ''}
                      onChange={(e) => {
                        setMapping((m) => ({ ...m, [field]: e.target.value }));
                        setPreview(null);
                      }}
                    >
                      <option value="">Не используется</option>
                      {columns.map((c) => (
                        <option key={c.key} value={c.key}>
                          {c.label || 'Без названия'} · {c.key.replace('column_', '')}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <button
                className="button button-dark"
                disabled={
                  busy || !mapping.company || (!mapping.ending_debit && !mapping.ending_credit)
                }
                onClick={() => void check(true)}
              >
                {busy ? 'Сравниваем…' : 'Сравнить остатки'}
                <ArrowRight size={15} />
              </button>
            </div>
          )}
          <DeskError>{error}</DeskError>
          {preview && (
            <div className="ops-preview">
              <div className="ops-context">
                <p>
                  Остатки источника на {dateText(asOf)} сравниваются с текущим реестром. Сверка
                  сохраняет основание и расхождения.
                </p>
              </div>
              {preview.errors.map((e, i) => (
                <p className="form-error" key={i}>
                  {e.row ? `Строка ${e.row}: ` : ''}
                  {e.message}
                </p>
              ))}
              <div className="table-scroll">
                <table className="invoice-table ops-table">
                  <thead>
                    <tr>
                      <th scope="col">ВЫБОР</th>
                      <th scope="col">ПОКУПАТЕЛЬ</th>
                      <th scope="col">ПО ИСТОЧНИКУ</th>
                      <th scope="col">СЕЙЧАС В РЕЕСТРЕ</th>
                      <th scope="col">РАСХОЖДЕНИЕ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.items.map((item) => (
                      <tr key={item.row}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Включить строку ${item.row}`}
                            disabled={preview.errors.some((e) => e.row === item.row)}
                            checked={selected.includes(item.row)}
                            onChange={(e) =>
                              setSelected((rows) =>
                                e.target.checked
                                  ? [...rows, item.row]
                                  : rows.filter((r) => r !== item.row)
                              )
                            }
                          />
                        </td>
                        <td>
                          {item.company}
                          <small>{item.inn}</small>
                        </td>
                        <td>{money(item.source_balance)}</td>
                        <td>{money(item.ledger_current_balance)}</td>
                        <td>
                          <span className={item.discrepancy ? 'ops-discrepancy' : ''}>
                            {money(item.discrepancy)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {selected.length > 0 && !preview.errors.some((e) => e.row === 0) && (
                <OperationForm
                  label="Сохранить сверку"
                  onDone={() => {
                    setPreview(null);
                    void reload();
                    onSaved();
                  }}
                  submit={async (data) => {
                    setBusy(true);
                    try {
                      return await post(`/accounting/imports/${preview.id}/approve`, {
                        reason: value(data, 'reason'),
                        selected_rows: selected,
                      });
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <label className="field full-width">
                    Основание согласования
                    <input name="reason" required maxLength={3000} />
                  </label>
                  <label className="consent full-width">
                    <input type="checkbox" required />
                    <span>Проверил выбранные строки и исключил промежуточные итоги</span>
                  </label>
                </OperationForm>
              )}
            </div>
          )}
        </fieldset>
      </section>
      <section className="ops-card">
        <div className="ops-card-heading">
          <div>
            <h2>Сохранённые сверки</h2>
            <p>Источник, дата и результат сравнения остаются в истории.</p>
          </div>
        </div>
        {history.length ? (
          <div className="table-scroll">
            <table className="invoice-table ops-table">
              <thead>
                <tr>
                  <th scope="col">ИСТОЧНИК</th>
                  <th scope="col">ПОКУПАТЕЛЬ</th>
                  <th scope="col">ОСТАТОК ИСТОЧНИКА</th>
                  <th scope="col">РАСХОЖДЕНИЕ НА МОМЕНТ СВЕРКИ</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td>
                      {h.source_ref}
                      <small>
                        {dateText(h.as_of)} · {h.reason}
                      </small>
                    </td>
                    <td>{h.company}</td>
                    <td>{money(h.source_balance)}</td>
                    <td>{money(h.discrepancy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyCard title="Сверка начинается с источника">
            Загрузите ведомость или акт и выберите строки покупателей для сравнения.
          </EmptyCard>
        )}
      </section>
    </>
  );
}
