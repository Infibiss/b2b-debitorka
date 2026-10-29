import { useState, type FormEvent, type ReactNode } from 'react';
import { AlertCircle, ArrowRight, LoaderCircle } from 'lucide-react';
import type { Invoice } from '../api';
import { money } from '../api';
import './operations.css';
import { useWorkContext } from '../navigation';
import { useFormDraft } from './useFormDraft';

export type DeskProps = {
  invoices: Invoice[];
  onChanged: () => void;
  notify: (text: string, error?: boolean) => void;
};
export function DeskHeading({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading ops-heading">
      <div>
        <span className="page-date">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{children}</p>
      </div>
      {action}
    </div>
  );
}
export function OperationForm({
  submit,
  onDone,
  label = 'Сохранить',
  draftKey = '',
  revision,
  resetOnSave = false,
  allowIncomplete = false,
  children,
}: {
  submit: (data: FormData) => Promise<unknown>;
  onDone: () => void;
  label?: string;
  draftKey?: string;
  revision?: string;
  resetOnSave?: boolean;
  allowIncomplete?: boolean;
  children: ReactNode;
}) {
  const draft = useFormDraft(draftKey, revision);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setError('');
    setBusy(true);
    try {
      await submit(values);
      draft.clear();
      if (resetOnSave) form.reset();
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      ref={draft.ref}
      className="form-grid ops-form"
      onSubmit={save}
      noValidate={allowIncomplete}
    >
      {draft.status && (
        <p className="draft-status full-width" role="status">
          {draft.status}
        </p>
      )}
      {children}
      {error && (
        <p role="alert" className="form-error full-width">
          <AlertCircle size={15} />
          {error}
        </p>
      )}
      <div className="dialog-actions full-width">
        {draft.status && (
          <button
            className="button button-ghost"
            type="button"
            disabled={busy}
            onClick={draft.discard}
          >
            Отменить изменения
          </button>
        )}
        <button className="button button-dark" disabled={busy} type="submit">
          {busy ? (
            <>
              <LoaderCircle className="spin" size={16} />
              Сохраняем…
            </>
          ) : (
            <>
              {label}
              <ArrowRight size={15} />
            </>
          )}
        </button>
      </div>
    </form>
  );
}
export function InvoiceSelect({
  invoices,
  name = 'invoice_id',
  value,
  onChange,
}: {
  invoices: Invoice[];
  name?: string;
  value?: string;
  onChange?: (value: string) => void;
}) {
  const { invoiceId } = useWorkContext();
  return (
    <label className="field full-width">
      Счёт
      <select
        required
        name={name}
        value={value}
        defaultValue={
          value === undefined
            ? invoices.some((i) => i.id === invoiceId)
              ? invoiceId
              : ''
            : undefined
        }
        onChange={(e) => onChange?.(e.target.value)}
      >
        <option value="" disabled>
          Выберите счёт
        </option>
        {invoices.map((i) => (
          <option key={i.id} value={i.id}>
            {i.company} · {i.number} · {money(i.balance)}
          </option>
        ))}
      </select>
    </label>
  );
}
export const value = (data: FormData, name: string) => String(data.get(name) ?? '').trim();
export function rubles(raw: string) {
  const clean = raw.replace(/\s/g, '').replace(',', '.');
  if (!/^\d+(?:\.\d{1,2})?$/.test(clean))
    throw new Error('Укажите сумму в рублях, не более двух знаков после запятой.');
  const [whole, fraction = ''] = clean.split('.');
  const result = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  if (result > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error('Сумма слишком велика.');
  return Number(result);
}
export function DeskError({ children }: { children: string }) {
  return children ? (
    <p className="page-error" role="alert">
      <AlertCircle size={16} />
      {children}
    </p>
  ) : null;
}
export function EmptyCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="ops-empty">
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
