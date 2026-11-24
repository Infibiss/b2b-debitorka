import { useState, type FormEvent } from 'react';
import { post, money } from '../../api';
import { t } from '../../i18n';
import type { DebtorDetail, Notify } from './types';

export function caseQuery(debtor: DebtorDetail | null) {
  return debtor?.selected_case_id ? `?case_id=${encodeURIComponent(debtor.selected_case_id)}` : '';
}

export function CaseScope({
  debtor,
  onSelect,
  onCreated,
  notify,
  isManager,
  disabled = false,
}: {
  debtor: DebtorDetail;
  isManager: boolean;
  disabled?: boolean;
  onSelect: (id: string | null) => void;
  onCreated: () => void;
  notify: Notify;
}) {
  const [editing, setEditing] = useState(false);
  const [number, setNumber] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const cases = debtor.cases ?? [];
  const unassigned = new Set(
    cases.filter((item) => !item.contract_id).flatMap((item) => item.invoice_ids)
  );
  const invoices = debtor.invoices.filter((item) => unassigned.has(item.id));
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await post<{ case_id: string }>('/workflow/contracts', {
        counterparty_id: debtor.id,
        number: number.trim(),
        invoice_ids: selected,
      });
      setEditing(false);
      setSelected([]);
      setNumber('');
      onCreated();
      onSelect(result.case_id);
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  if (!cases.length) return null;
  return (
    <section className="rc-card rc-case-scope">
      <div className="rc-case-head">
        <label>
          {t('Договор или счёт')}
          <select
            aria-label={t('Договор или счёт')}
            disabled={disabled || busy}
            value={debtor.selected_case_id ?? ''}
            onChange={(event) => onSelect(event.target.value || null)}
          >
            {cases.length > 1 && <option value="">{t('Все договоры и счета')}</option>}
            {cases.map((item) => (
              <option key={item.case_id} value={item.case_id}>
                {item.contract_number
                  ? t('Договор {0}', [item.contract_number])
                  : t('Без договора · {0}', [
                      item.invoice_numbers?.join(', ') || item.invoice_ids.length,
                    ])}
              </option>
            ))}
          </select>
        </label>
        {invoices.length > 0 && (
          <button
            type="button"
            className="button button-outline"
            disabled={disabled || busy}
            onClick={() => setEditing(!editing)}
          >
            {editing ? t('Отмена') : t('Указать договор')}
          </button>
        )}
      </div>
      {debtor.legacy_review_required && (
        <div className="rc-note" role="status">
          <p>
            {t(
              'Раньше история велась общей суммой. Выберите договор или счёт, к которому относятся прежние действия и документы.'
            )}
          </p>
          {isManager && debtor.selected_case_id && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                setBusy(true);
                post(`/recovery/debtors/${debtor.id}/legacy-assignment${caseQuery(debtor)}`, {})
                  .then(() => onCreated())
                  .catch((error) => notify(error.message, true))
                  .finally(() => setBusy(false));
              }}
            >
              <label className="rc-check">
                <input
                  type="checkbox"
                  required
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                {t('Прежняя история относится к выбранному делу')}
              </label>
              <button className="button button-outline" disabled={!confirmed || busy}>
                {t('Связать прежнюю историю')}
              </button>
            </form>
          )}
        </div>
      )}
      {debtor.read_only && (
        <p className="rc-muted">
          {t('Выберите договор или счёт, чтобы продолжить работу по нему.')}
        </p>
      )}
      {cases.length > 1 && !editing && (
        <ul className="rc-case-list">
          {cases.map((item) => (
            <li key={item.case_id}>
              <button
                type="button"
                className="wf-text-button"
                disabled={disabled || busy}
                onClick={() => onSelect(item.case_id)}
              >
                {item.contract_number
                  ? t('Договор {0}', [item.contract_number])
                  : t('Без договора · {0}', [
                      item.invoice_numbers?.join(', ') || item.invoice_ids.length,
                    ])}
              </button>
              <span>{t(item.status_label ?? item.status ?? '')}</span>
              <strong>{money(item.balance)}</strong>
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <form className="rc-action-form" onSubmit={(event) => void create(event)}>
          <h3>{t('Объединить счета по договору')}</h3>
          <label>
            {t('Номер и дата договора')}
            <input
              required
              maxLength={200}
              value={number}
              onChange={(event) => setNumber(event.target.value)}
            />
          </label>
          <fieldset>
            <legend>{t('Счета по этому договору')}</legend>
            {invoices.map((item) => (
              <label className="rc-check" key={item.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(item.id)}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, item.id]
                        : current.filter((id) => id !== item.id)
                    )
                  }
                />
                {t('Счёт {0}', [item.number])} · {money(item.balance)}
              </label>
            ))}
          </fieldset>
          <button
            className="button button-dark"
            disabled={disabled || busy || !selected.length || !number.trim()}
          >
            {t('Сохранить договор')}
          </button>
        </form>
      )}
    </section>
  );
}
