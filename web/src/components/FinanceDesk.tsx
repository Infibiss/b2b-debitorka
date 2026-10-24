import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, Upload, ShieldCheck, ArrowUpRight, Wallet, RotateCcw } from 'lucide-react';
import { api, post, patch, money, dateText, today, type Invoice } from '../api';
import { Dialog } from './Dialog';
import { AccountingDesk } from './AccountingDesk';
import {
  DeskHeading,
  DeskError,
  EmptyCard,
  OperationForm,
  InvoiceSelect,
  rubles,
  value,
  type DeskProps,
} from './OperationsUI';

type Counterparty = {
  id: string;
  name: string;
  inn: string;
  hold: boolean;
  hold_reason: string;
  contact_allowed: boolean;
  agent_promises_allowed: boolean;
  max_promise_days: number;
  max_installments: number;
  mandate_expires_on: string | null;
};
type BankPayment = {
  id: string;
  external_id: string;
  amount: number;
  paid_on: string;
  payer_inn: string;
  payer_name: string;
  reference: string;
  evidence: string;
  available_amount: number;
  allocated_amount: number;
  returned_amount: number;
};
type LedgerPayment = {
  id: string;
  amount: number;
  paid_on: string;
  reference: string;
  reversed_amount?: number;
  source?: string;
  display_reference?: string;
  bank_payment_id?: string | null;
};
type Ledger = {
  invoice: Invoice;
  payments: LedgerPayment[];
  adjustments: {
    id: string;
    kind: string;
    amount: number;
    signed_amount: number;
    reason: string;
  }[];
  promises: {
    id: string;
    amount: number;
    due_on: string;
    status?: string;
    installments: { id: string; due_on: string; amount: number; fulfilled_amount: number }[];
  }[];
};
type Change = {
  action: 'create' | 'update' | 'skip' | 'conflict';
  invoice_id?: string;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  reason?: string;
};
type Preview = { id: string; changes: Change[]; errors: { row: number; message: string }[] };
type Modal =
  | { type: 'bank' }
  | { type: 'allocate'; payment: BankPayment }
  | { type: 'mandate'; party: Counterparty }
  | { type: 'adjust' | 'promise'; invoice: Invoice }
  | { type: 'reverse'; payment: LedgerPayment };

export function FinanceDesk({ invoices, onChanged, notify }: DeskProps) {
  const [tab, setTab] = useState<'bank' | 'import' | 'accounting' | 'parties' | 'ledger'>('bank');
  const [parties, setParties] = useState<Counterparty[]>([]),
    [payments, setPayments] = useState<BankPayment[]>([]),
    [error, setError] = useState('');
  const [modal, setModal] = useState<Modal | null>(null),
    [selected, setSelected] = useState(''),
    [ledger, setLedger] = useState<Ledger | null>(null);
  const ledgerRequest = useRef(0);
  const reload = useCallback(async () => {
    try {
      const [p, b] = await Promise.all([
        api<{ items: Counterparty[] }>('/finance/counterparties'),
        api<{ items: BankPayment[] }>('/finance/bank-payments'),
      ]);
      setParties(p.items);
      setPayments(b.items);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  const loadLedger = useCallback(async (id: string) => {
    const request = ++ledgerRequest.current;
    setLedger(null);
    if (!id) return;
    try {
      const result = await api<Ledger>(`/finance/invoices/${id}/ledger`);
      if (request === ledgerRequest.current) {
        setLedger(result);
        setError('');
      }
    } catch (e) {
      if (request === ledgerRequest.current) setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  useEffect(() => {
    void loadLedger(selected);
  }, [selected, loadLedger]);
  const done = () => {
    setModal(null);
    void reload();
    void loadLedger(selected);
    onChanged();
    notify('Изменения сохранены');
  };
  return (
    <>
      <DeskHeading
        eyebrow="ТОЧНЫЙ ОСТАТОК — ОСНОВА КАЖДОГО ДЕЙСТВИЯ"
        title="Финансы без расхождений."
        action={
          <button className="button button-dark" onClick={() => setModal({ type: 'bank' })}>
            <Plus size={16} />
            Добавить поступление
          </button>
        }
      >
        Сверяйте выгрузки, распределяйте поступления и сохраняйте основания каждого изменения.
      </DeskHeading>
      <div className="ops-tabs" role="tablist" aria-label="Финансовые операции">
        {(
          [
            ['bank', 'Поступления'],
            ['import', 'Сверка реестра'],
            ['accounting', 'ОСВ и акты'],
            ['parties', 'Контрагенты'],
            ['ledger', 'Движение по счёту'],
          ] as const
        ).map(([id, label]) => (
          <button role="tab" aria-selected={tab === id} key={id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <DeskError>{error}</DeskError>
      {tab === 'bank' && (
        <section className="ops-card">
          <div className="ops-card-heading">
            <div>
              <h2>Банковские поступления</h2>
              <p>
                Одно поступление — несколько счетов. Общая сумма распределений всегда ограничена
                платежом.
              </p>
            </div>
            <Wallet size={22} />
          </div>
          {payments.length ? (
            <>
              <div className="table-scroll ops-bank-table">
                <table className="invoice-table ops-table">
                  <thead>
                    <tr>
                      <th scope="col">ПЛАТЁЖ / ПОКУПАТЕЛЬ</th>
                      <th scope="col">СУММА</th>
                      <th scope="col">РАСПРЕДЕЛЕНО</th>
                      <th scope="col">ДОСТУПНО</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {payments.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.reference}</strong>
                          <small>
                            {p.payer_name || p.payer_inn} · {dateText(p.paid_on)}
                          </small>
                        </td>
                        <td>{money(p.amount)}</td>
                        <td>{money(p.allocated_amount)}</td>
                        <td>{money(p.available_amount)}</td>
                        <td>
                          <button
                            className="button button-outline button-small"
                            disabled={p.available_amount <= 0}
                            onClick={() => setModal({ type: 'allocate', payment: p })}
                          >
                            Распределить
                            <ArrowUpRight size={13} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="ops-bank-cards">
                {payments.map((p) => (
                  <article className="ops-bank-card" key={p.id}>
                    <div>
                      <strong>{p.reference}</strong>
                      <small>
                        {p.payer_name || p.payer_inn} · {dateText(p.paid_on)}
                      </small>
                    </div>
                    <div className="ops-bank-totals">
                      <div>
                        <span>Поступление</span>
                        <strong>{money(p.amount)}</strong>
                      </div>
                      <div>
                        <span>Распределено</span>
                        <strong>{money(p.allocated_amount)}</strong>
                      </div>
                      <div>
                        <span>Доступно</span>
                        <strong>{money(p.available_amount)}</strong>
                      </div>
                    </div>
                    <button
                      className="button button-outline button-small"
                      disabled={p.available_amount <= 0}
                      onClick={() => setModal({ type: 'allocate', payment: p })}
                    >
                      Распределить
                      <ArrowUpRight size={13} />
                    </button>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <EmptyCard title="Поступления под контролем">
              Добавьте подтверждённую операцию из банковской выписки и распределите её по счетам.
            </EmptyCard>
          )}
        </section>
      )}
      {tab === 'import' && (
        <Reconciliation
          onDone={() => {
            onChanged();
            void reload();
            notify('Реестр сверен');
          }}
        />
      )}
      {tab === 'accounting' && (
        <AccountingDesk
          onSaved={() => {
            void reload();
            notify('Сверка сохранена');
          }}
        />
      )}
      {tab === 'parties' && (
        <section className="ops-card">
          <div className="ops-card-heading">
            <div>
              <h2>Покупатели и правила контакта</h2>
              <p>Одна договорённость действует на все счета покупателя.</p>
            </div>
            <ShieldCheck size={23} />
          </div>
          {parties.length ? (
            <div className="ops-party-grid">
              {parties.map((p) => (
                <article className="ops-party" key={p.id}>
                  <div>
                    <h3>{p.name}</h3>
                    <span>{p.inn ? `ИНН ${p.inn}` : 'ИНН не указан'}</span>
                  </div>
                  <span
                    className={`pill ${p.hold || !p.contact_allowed ? 'status-paused' : 'status-open'}`}
                  >
                    {p.hold || !p.contact_allowed ? 'Контакт приостановлен' : 'В работе'}
                  </span>
                  {p.hold_reason && <p>{p.hold_reason}</p>}
                  <p>
                    {p.agent_promises_allowed
                      ? 'Агент может предлагать договорённости в пределах мандата.'
                      : 'Договорённости подтверждает сотрудник.'}
                  </p>
                  <button
                    className="button button-outline button-small"
                    onClick={() => setModal({ type: 'mandate', party: p })}
                  >
                    Правила работы
                    <ArrowUpRight size={13} />
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <EmptyCard title="Здесь будут ваши покупатели">
              Контрагент создаётся вместе с первым счётом и объединяется по ИНН.
            </EmptyCard>
          )}
        </section>
      )}
      {tab === 'ledger' && (
        <section className="ops-card">
          <div className="ops-card-heading">
            <div>
              <h2>История изменения остатка</h2>
              <p>Платежи, корректировки и договорённости с сохранением исходных оснований.</p>
            </div>
          </div>
          <InvoiceSelect invoices={invoices} value={selected} onChange={setSelected} />
          {ledger && ledger.invoice.id === selected && (
            <>
              <div className="ops-ledger-summary">
                <div>
                  <span>Осталось к оплате</span>
                  <strong>{money(ledger.invoice.balance)}</strong>
                </div>
                <button
                  className="button button-outline"
                  onClick={() => setModal({ type: 'adjust', invoice: ledger.invoice })}
                >
                  Изменить требование
                </button>
                <button
                  className="button button-dark"
                  disabled={!ledger.invoice.balance}
                  onClick={() => setModal({ type: 'promise', invoice: ledger.invoice })}
                >
                  Договорённость
                </button>
              </div>
              <h3>Платежи</h3>
              {ledger.payments.length ? (
                ledger.payments.map((p) => (
                  <div className="ops-ledger-row" key={p.id}>
                    <div>
                      <strong>{p.display_reference || p.reference}</strong>
                      <small>
                        {dateText(p.paid_on)} ·{' '}
                        {p.bank_payment_id ? 'По банковской выписке' : 'Ручная запись'}
                        {p.reversed_amount ? ` · отменено ${money(p.reversed_amount)}` : ''}
                      </small>
                    </div>
                    <strong>{money(p.amount)}</strong>
                    <button
                      className="icon-button"
                      aria-label={`Исправить платёж ${p.display_reference || p.reference}`}
                      onClick={() => setModal({ type: 'reverse', payment: p })}
                    >
                      <RotateCcw size={16} />
                    </button>
                  </div>
                ))
              ) : (
                <p className="ops-muted">По этому счёту ещё нет отдельных платежей.</p>
              )}
              <h3>Корректировки</h3>
              {ledger.adjustments.map((a) => (
                <div className="ops-ledger-row" key={a.id}>
                  <span>{a.reason}</span>
                  <strong>
                    {a.signed_amount > 0 ? '+' : ''}
                    {money(a.signed_amount)}
                  </strong>
                </div>
              ))}
              <h3>Договорённости</h3>
              {ledger.promises.map((p) => (
                <div className="ops-promise" key={p.id}>
                  <div className="ops-ledger-row">
                    <span>
                      До {dateText(p.due_on)}
                      {p.status
                        ? ` · ${p.status === 'active' ? 'В работе' : p.status === 'cancelled' ? 'Заменена новой договорённостью' : 'Исполнена'}`
                        : ''}
                    </span>
                    <strong>{money(p.amount)}</strong>
                  </div>
                  {p.installments?.map((item) => (
                    <div className="ops-schedule-row" key={item.id}>
                      <span>{dateText(item.due_on)}</span>
                      <strong>{money(item.amount)}</strong>
                      <small>
                        {item.fulfilled_amount >= item.amount
                          ? 'Исполнен'
                          : item.fulfilled_amount
                            ? `Осталось ${money(item.amount - item.fulfilled_amount)}`
                            : 'Ожидается'}
                      </small>
                    </div>
                  ))}
                </div>
              ))}
            </>
          )}
        </section>
      )}
      {modal && (
        <FinanceModal
          key={
            modal.type +
            ('party' in modal ? modal.party.id : 'payment' in modal ? modal.payment.id : '')
          }
          modal={modal}
          invoices={invoices}
          onClose={() => setModal(null)}
          onDone={done}
        />
      )}
    </>
  );
}

function FinanceModal({
  modal,
  invoices,
  onClose,
  onDone,
}: {
  modal: Modal;
  invoices: Invoice[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [key] = useState(() => crypto.randomUUID());
  const [installments, setInstallments] = useState<{ date: string; amount: string }[]>([]);
  const names = {
    bank: 'Подтверждённое поступление',
    allocate: 'Распределение поступления',
    mandate: 'Правила работы с покупателем',
    adjust: 'Изменение требования',
    promise: 'Договорённость об оплате',
    reverse: 'Исправление платежа',
  };
  return (
    <Dialog title={names[modal.type]} onClose={onClose} wide>
      <OperationForm
        onDone={onDone}
        label={
          modal.type === 'bank'
            ? 'Сохранить поступление'
            : modal.type === 'allocate'
              ? 'Распределить сумму'
              : modal.type === 'promise'
                ? 'Сохранить договорённость'
                : 'Сохранить изменения'
        }
        submit={async (data) => {
          if (modal.type === 'bank')
            return post('/finance/bank-payments', {
              external_id: value(data, 'external_id'),
              reference: value(data, 'reference'),
              amount: rubles(value(data, 'amount')),
              paid_on: value(data, 'paid_on'),
              payer_inn: value(data, 'payer_inn'),
              payer_name: value(data, 'payer_name'),
              evidence: value(data, 'evidence'),
              confirmed: data.get('confirmed') === 'on',
            });
          if (modal.type === 'allocate')
            return post(`/finance/bank-payments/${modal.payment.id}/allocate`, {
              invoice_id: value(data, 'invoice_id'),
              amount: rubles(value(data, 'amount')),
              idempotency_key: key,
            });
          if (modal.type === 'mandate')
            return patch(`/finance/counterparties/${modal.party.id}`, {
              hold: data.get('hold') === 'on',
              hold_reason: value(data, 'hold_reason'),
              contact_allowed: data.get('contact_allowed') === 'on',
              agent_promises_allowed: data.get('agent_promises_allowed') === 'on',
              max_promise_days: Number(value(data, 'max_promise_days')),
              max_installments: Number(value(data, 'max_installments')),
              mandate_expires_on: value(data, 'mandate_expires_on') || null,
            });
          if (modal.type === 'adjust')
            return post(`/finance/invoices/${modal.invoice.id}/adjustments`, {
              kind: value(data, 'kind'),
              amount: rubles(value(data, 'amount')),
              reason: value(data, 'reason'),
              effective_on: value(data, 'effective_on'),
              idempotency_key: key,
            });
          if (modal.type === 'reverse')
            return post(`/finance/payments/${modal.payment.id}/reverse`, {
              kind: value(data, 'kind'),
              amount: rubles(value(data, 'amount')),
              reason: value(data, 'reason'),
              idempotency_key: key,
            });
          const schedule = installments.map((item) => ({
            date: item.date,
            amount: rubles(item.amount),
          }));
          return post(`/finance/invoices/${modal.invoice.id}/promise`, {
            amount: schedule.length
              ? schedule.reduce((s, i) => s + i.amount, 0)
              : rubles(value(data, 'amount')),
            date: schedule.length ? schedule[schedule.length - 1].date : value(data, 'date'),
            ...(schedule.length ? { installments: schedule } : {}),
            idempotency_key: key,
          });
        }}
      >
        {modal.type === 'bank' && (
          <>
            <label className="field">
              ID операции в выписке
              <input name="external_id" required maxLength={200} />
            </label>
            <label className="field">
              Номер платежа
              <input name="reference" required maxLength={200} />
            </label>
            <label className="field">
              Сумма поступления, ₽<input name="amount" inputMode="decimal" required />
            </label>
            <label className="field">
              Дата поступления
              <input name="paid_on" type="date" defaultValue={today()} max={today()} required />
            </label>
            <label className="field">
              Плательщик
              <input name="payer_name" maxLength={200} />
            </label>
            <label className="field">
              ИНН плательщика
              <input name="payer_inn" inputMode="numeric" pattern="[0-9]{10}|[0-9]{12}|^$" />
            </label>
            <label className="field full-width">
              Основание проверки
              <textarea
                name="evidence"
                required
                placeholder="Выписка банка, дата и номер строки"
                maxLength={2000}
              />
            </label>
            <label className="consent full-width">
              <input type="checkbox" name="confirmed" required />
              <span>Сверил поступление с банковской выпиской</span>
            </label>
          </>
        )}
        {modal.type === 'allocate' && (
          <>
            <div className="ops-context full-width">
              <strong>{modal.payment.reference}</strong>
              <span>Доступно {money(modal.payment.available_amount)}</span>
            </div>
            <InvoiceSelect invoices={invoices.filter((i) => i.balance > 0)} />
            <label className="field full-width">
              Сумма распределения, ₽<input name="amount" inputMode="decimal" required />
            </label>
          </>
        )}
        {modal.type === 'mandate' && (
          <>
            <div className="ops-context full-width">
              <strong>{modal.party.name}</strong>
              <span>{modal.party.inn}</span>
            </div>
            <label className="consent full-width">
              <input
                name="contact_allowed"
                type="checkbox"
                defaultChecked={modal.party.contact_allowed}
              />
              <span>Разрешить контакт по счетам покупателя</span>
            </label>
            <label className="consent full-width">
              <input name="hold" type="checkbox" defaultChecked={modal.party.hold} />
              <span>Приостановить контакт по всем счетам</span>
            </label>
            <label className="field full-width">
              Причина приостановки
              <input name="hold_reason" defaultValue={modal.party.hold_reason} maxLength={2000} />
            </label>
            <label className="consent full-width">
              <input
                name="agent_promises_allowed"
                type="checkbox"
                defaultChecked={modal.party.agent_promises_allowed}
              />
              <span>Разрешить агенту предлагать сроки и график в пределах мандата</span>
            </label>
            <label className="field">
              Максимум дней отсрочки
              <input
                name="max_promise_days"
                type="number"
                min="1"
                max="365"
                defaultValue={modal.party.max_promise_days || 30}
                required
              />
            </label>
            <label className="field">
              Максимум платежей в графике
              <input
                name="max_installments"
                type="number"
                min="1"
                max="24"
                defaultValue={modal.party.max_installments || 3}
                required
              />
            </label>
            <label className="field full-width">
              Мандат действует до
              <input
                name="mandate_expires_on"
                type="date"
                defaultValue={modal.party.mandate_expires_on || ''}
              />
            </label>
          </>
        )}
        {modal.type === 'adjust' && (
          <>
            <div className="ops-context full-width">
              <strong>{modal.invoice.number}</strong>
              <span>Остаток {money(modal.invoice.balance)}</span>
            </div>
            <label className="field">
              Основание
              <select name="kind" defaultValue={modal.invoice.balance === 0 ? 'debit' : 'return'}>
                <option value="return">Возврат товара</option>
                <option value="offset">Зачёт встречного требования</option>
                <option value="credit">Уменьшение требования</option>
                <option value="debit">Дополнительное начисление</option>
              </select>
            </label>
            <label className="field">
              Сумма изменения, ₽<input name="amount" inputMode="decimal" required />
            </label>
            <label className="field">
              Дата основания
              <input
                name="effective_on"
                type="date"
                defaultValue={today()}
                max={today()}
                required
              />
            </label>
            <label className="field full-width">
              Документ и причина
              <textarea name="reason" required maxLength={2000} />
            </label>
          </>
        )}
        {modal.type === 'reverse' && (
          <>
            <div className="ops-context full-width">
              <strong>{modal.payment.display_reference || modal.payment.reference}</strong>
              <span>Исходная сумма {money(modal.payment.amount)}</span>
            </div>
            <label className="field">
              Операция
              <select name="kind">
                <option value="correction">Исправление ошибочного разнесения</option>
                <option value="refund">Возврат денег покупателю</option>
              </select>
            </label>
            <label className="field">
              Сумма отмены, ₽<input name="amount" inputMode="decimal" required />
            </label>
            <label className="field full-width">
              Основание и причина
              <textarea name="reason" required maxLength={2000} />
            </label>
          </>
        )}
        {modal.type === 'promise' && (
          <>
            <div className="ops-context full-width">
              <strong>{modal.invoice.number}</strong>
              <span>Остаток {money(modal.invoice.balance)}</span>
            </div>
            {!installments.length && (
              <>
                <label className="field">
                  Обещанная сумма, ₽<input name="amount" inputMode="decimal" required />
                </label>
                <label className="field">
                  Дата оплаты
                  <input name="date" type="date" min={today()} defaultValue={today()} required />
                </label>
              </>
            )}
            {installments.map((item, index) => (
              <div className="ops-installment full-width" key={index}>
                <label className="field">
                  Дата платежа {index + 1}
                  <input
                    type="date"
                    min={today()}
                    required
                    value={item.date}
                    onChange={(e) =>
                      setInstallments((items) =>
                        items.map((x, i) => (i === index ? { ...x, date: e.target.value } : x))
                      )
                    }
                  />
                </label>
                <label className="field">
                  Сумма, ₽
                  <input
                    inputMode="decimal"
                    required
                    value={item.amount}
                    onChange={(e) =>
                      setInstallments((items) =>
                        items.map((x, i) => (i === index ? { ...x, amount: e.target.value } : x))
                      )
                    }
                  />
                </label>
                <button
                  className="icon-button"
                  type="button"
                  aria-label={`Убрать платёж ${index + 1}`}
                  onClick={() => setInstallments((items) => items.filter((_, i) => i !== index))}
                >
                  ×
                </button>
              </div>
            ))}
            <button
              className="button button-outline full-width"
              type="button"
              disabled={installments.length >= 24}
              onClick={() => setInstallments((items) => [...items, { date: today(), amount: '' }])}
            >
              <Plus size={14} />
              {installments.length ? 'Добавить платёж в график' : 'Разбить на несколько платежей'}
            </button>
          </>
        )}
      </OperationForm>
    </Dialog>
  );
}

function Reconciliation({ onDone }: { onDone: () => void }) {
  const fileRequest = useRef(0);
  const [content, setContent] = useState(''),
    [preview, setPreview] = useState<Preview | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function check() {
    setBusy(true);
    setError('');
    try {
      setPreview(await post<Preview>('/finance/imports/preview', { content }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="ops-card">
      <div className="ops-card-heading">
        <div>
          <h2>Сверка с учётной системой</h2>
          <p>Проверьте начальные оплаты и изменения существующих счетов перед сохранением.</p>
        </div>
        <Upload size={22} />
      </div>
      <fieldset disabled={busy} className="ops-input-group">
        <label className="field">
          Выгрузка CSV
          <input
            type="file"
            accept=".csv,.txt"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              if (file.size > 1500000) {
                setError('Файл слишком большой. Разделите выгрузку на несколько частей.');
                return;
              }
              const request = ++fileRequest.current;
              setContent('');
              setPreview(null);
              const bytes = await file.arrayBuffer();
              if (request !== fileRequest.current) return;
              let text = '';
              try {
                text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
              } catch {
                text = new TextDecoder('windows-1251').decode(bytes);
              }
              setContent(text);
              setPreview(null);
            }}
          />
        </label>
        <label className="field">
          Данные реестра
          <textarea
            className="ops-csv"
            value={content}
            onChange={(e) => {
              fileRequest.current++;
              setContent(e.target.value);
              setPreview(null);
            }}
            rows={7}
            placeholder="контрагент;инн;номер;дата;срок;сумма;оплачено;остаток"
          />
        </label>
        <button
          className="button button-dark"
          disabled={busy || !content.trim()}
          onClick={() => void check()}
        >
          {busy ? 'Проверяем…' : 'Проверить изменения'}
          <ArrowUpRight size={15} />
        </button>
        <DeskError>{error}</DeskError>
        {preview && (
          <div className="ops-preview">
            {preview.errors.map((e, index) => (
              <p className="form-error" key={index}>
                Строка {e.row}: {e.message}
              </p>
            ))}
            <div className="table-scroll">
              <table className="invoice-table ops-table">
                <thead>
                  <tr>
                    <th scope="col">СЧЁТ</th>
                    <th scope="col">ИЗМЕНЕНИЕ</th>
                    <th scope="col">ПРЕЖНИЙ ОСТАТОК</th>
                    <th scope="col">НОВЫЙ ОСТАТОК</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.changes.map((c, index) => (
                    <tr key={index}>
                      <td>
                        {String(c.after?.company || c.before?.company || '')}
                        <small>{String(c.after?.number || c.before?.number || '')}</small>
                      </td>
                      <td>
                        {
                          {
                            create: 'Новый счёт',
                            update: 'Обновление',
                            skip: 'Без изменений',
                            conflict: 'Нужна проверка',
                          }[c.action]
                        }
                        {c.reason && <small>{c.reason}</small>}
                        {c.action === 'update' && <ChangeDetails change={c} />}
                      </td>
                      <td>
                        {typeof c.before?.balance === 'number' ? money(c.before.balance) : '—'}
                      </td>
                      <td>
                        {previewBalance(c.after) !== null ? money(previewBalance(c.after)!) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!preview.errors.length && !preview.changes.some((c) => c.action === 'conflict') && (
              <OperationForm
                label="Подтвердить сверку"
                onDone={() => {
                  setPreview(null);
                  setContent('');
                  onDone();
                }}
                submit={async (data) => {
                  setBusy(true);
                  try {
                    return await post(`/finance/imports/${preview.id}/approve`, {
                      reason: value(data, 'reason'),
                    });
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label className="field full-width">
                  Основание сверки
                  <input
                    name="reason"
                    required
                    placeholder="Выгрузка на дату, согласование бухгалтера"
                    maxLength={2000}
                  />
                </label>
                <label className="consent full-width">
                  <input type="checkbox" required />
                  <span>Проверил суммы, оплаты и изменения реестра</span>
                </label>
              </OperationForm>
            )}
          </div>
        )}
      </fieldset>
    </section>
  );
}

function previewBalance(item: Record<string, unknown> | undefined) {
  if (typeof item?.balance === 'number') return item.balance;
  if (typeof item?.amount === 'number')
    return item.amount - (typeof item.paid_amount === 'number' ? item.paid_amount : 0);
  return null;
}

function ChangeDetails({ change }: { change: Change }) {
  const fields = [
    ['company', 'Контрагент'],
    ['inn', 'ИНН'],
    ['email', 'Почта покупателя'],
    ['number', 'Номер счёта'],
    ['issued_on', 'Дата счёта'],
    ['due_on', 'Срок оплаты'],
    ['amount', 'Сумма счёта'],
    ['paid_amount', 'Оплачено'],
    ['notes', 'Примечание'],
  ] as const;
  const changed = fields.filter(
    ([key]) => String(change.before?.[key] ?? '') !== String(change.after?.[key] ?? '')
  );
  const format = (key: string, item: unknown) =>
    typeof item === 'number' && ['amount', 'paid_amount'].includes(key)
      ? money(item)
      : typeof item === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item)
        ? item.split('-').reverse().join('.')
        : String(item || 'Не указано');
  return changed.length ? (
    <details className="ops-change-details">
      <summary>Что изменится</summary>
      {changed.map(([key, label]) => (
        <div key={key}>
          <strong>{label}</strong>
          <span>
            {format(key, change.before?.[key])} → {format(key, change.after?.[key])}
          </span>
        </div>
      ))}
    </details>
  ) : null;
}
