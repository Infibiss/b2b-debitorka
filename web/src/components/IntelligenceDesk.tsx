import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import {
  Check,
  ChevronRight,
  Clock3,
  Plus,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  X,
} from 'lucide-react';
import { api, post, money, dateText, today, type Invoice } from '../api';
import { DeskHeading, DeskError, InvoiceSelect, rubles, type DeskProps } from './OperationsUI';
import './mandato-services.css';

type Kind =
  | 'promise'
  | 'installment'
  | 'discount'
  | 'document_request'
  | 'dispute'
  | 'payment_claim';
type Policy = {
  version: number;
  enabled: boolean;
  auto_accept: boolean;
  max_promise_days: number;
  max_installments: number;
  max_discount_bps: number;
  allowed_kinds: Kind[];
};
type Forecast = {
  as_of: string;
  generated_at: string;
  method: string;
  status: string;
  horizons: {
    days: number;
    expected_amount: number | null;
    low_scenario: number | null;
    high_scenario: number | null;
  }[];
  coverage: {
    open_balance: number;
    eligible_balance: number;
    covered_balance: number;
    training_invoices: number;
    bank_allocations: number;
    excluded_balance: number;
    uncovered_balance: number;
  };
  limitations: string[];
  invoices: {
    invoice_id: string;
    status: string;
    reasons?: string[];
    training_invoices?: number;
  }[];
};
type Terms = {
  kind: Kind;
  amount?: number | null;
  due_on?: string | null;
  discount_bps?: number | null;
  installments: { date: string; amount: number }[];
  evidence: string;
  expires_on: string;
  confirmed_by_operator: boolean;
  ambiguous: boolean;
};
type Proposal = {
  id: string;
  invoice_id: string;
  kind: Kind;
  status: string;
  policy_version: number;
  created_at: string;
  terms: Terms;
  reasons: string[];
  outcome: {
    action: string;
    external_delivery: boolean;
    ledger_changed?: boolean;
    concession_amount?: number;
    discount_bps?: number;
    write_off_requires_separate_approval?: boolean;
  } | null;
  events: { id: string; type: string; created_at: string }[];
};
const kinds: Record<Kind, string> = {
  promise: 'Обещание оплаты',
  installment: 'Рассрочка',
  discount: 'Запрос скидки',
  document_request: 'Запрос документов',
  dispute: 'Спор о долге',
  payment_claim: 'Заявление об оплате',
};
const states: Record<string, string> = {
  handoff: 'Требуется решение сотрудника',
  review_required: 'На согласовании',
  accepted: 'Принято · ожидает исполнения',
  executed: 'Исполнено в кабинете',
  rejected: 'Отклонено',
  expired: 'Срок предложения истёк',
};
const reasons: Record<string, string> = {
  policy_disabled: 'Правила переговоров выключены.',
  kind_outside_policy: 'Этот тип предложения не разрешён правилами.',
  unverified_proposal: 'Условия не подтверждены сотрудником.',
  ambiguous_terms: 'Условия неоднозначны: требуется уточнение.',
  financial_snapshot_changed:
    'Изменились остаток, документы или полномочия. Создайте новое предложение.',
  policy_changed: 'Правила изменились. Создайте предложение по текущей версии.',
  counterparty_hold: 'Контрагент поставлен на паузу.',
  contact_not_authorized: 'Нет разрешения на контакт.',
  mandate_expired: 'Срок разрешения истёк.',
  invoice_not_actionable: 'Счёт закрыт, на паузе или в споре.',
  promise_mandate_required: 'В «Финансах» требуется разрешение на обещания для этого контрагента.',
  amount_outside_current_balance: 'Сумма выходит за пределы текущего остатка.',
  date_outside_policy_or_mandate: 'Срок превышает правила или разрешение по контрагенту.',
  installments_outside_policy_or_mandate: 'Число платежей превышает разрешённый предел.',
  installment_date_in_past: 'В графике есть прошедшая дата.',
  discount_outside_policy: 'Скидка превышает установленный предел.',
  offer_expired: 'Срок действия предложения истёк.',
};
const outcomes: Record<string, string> = {
  promise_recorded: 'Обещание сохранено в финансовом графике.',
  dispute_recorded: 'Спор зарегистрирован. Контакт по счёту приостановлен.',
  concession_recorded_for_review: 'Запрос скидки сохранён для отдельного решения. Долг не списан.',
  verify_payment: 'Нужна сверка поступления с выпиской. Остаток не уменьшен.',
  request_documents: 'Запрос документов сохранён для обработки сотрудником.',
};
const forecastReasons: Record<string, string> = {
  held_or_disputed: 'Пауза, спор или ограничение контакта',
  not_yet_available: 'Данные ещё недоступны на дату расчёта',
  unreconstructible_history: 'История включает ручные оплаты или корректировки',
  temporal_history_unavailable: 'Не подтверждены даты финансовой истории',
  insufficient_comparable_history: 'Недостаточно сопоставимой истории',
};
const eventNames: Record<string, string> = {
  proposed: 'Предложение создано',
  reviewed: 'Решение сотрудника записано',
  executed: 'Действие исполнено в кабинете',
  handoff: 'Повторная проверка: передано сотруднику',
};
const futureDate = (days: number) => {
  const value = new Date(`${today()}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
};

export function IntelligenceDesk({ invoices, notify, onChanged }: DeskProps) {
  const [forecast, setForecast] = useState<Forecast | null>(null),
    [policy, setPolicy] = useState<Policy | null>(null),
    [proposals, setProposals] = useState<Proposal[]>([]);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [policyBusy, setPolicyBusy] = useState(false);
  const [kind, setKind] = useState<Kind>('promise'),
    [invoiceId, setInvoiceId] = useState(''),
    [amount, setAmount] = useState(''),
    [dueOn, setDueOn] = useState(futureDate(7)),
    [expiresOn, setExpiresOn] = useState(futureDate(3));
  const [installments, setInstallments] = useState([
    { id: crypto.randomUUID(), date: futureDate(7), amount: '' },
  ]);
  const [confirmed, setConfirmed] = useState(false),
    [ambiguous, setAmbiguous] = useState(false);
  const reload = useCallback(async () => {
    const [forecast, policy, proposals] = await Promise.all([
      api<Forecast>('/forecast'),
      api<Policy>('/negotiation/policy'),
      api<{ items: Proposal[] }>('/negotiation/proposals'),
    ]);
    setForecast(forecast);
    setPolicy(policy);
    setProposals(proposals.items);
  }, []);
  useEffect(() => {
    void reload().catch((e) => setError((e as Error).message));
  }, [reload]);
  async function refresh() {
    setBusy(true);
    setError('');
    try {
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy) return;
    const data = new FormData(event.currentTarget);
    setPolicyBusy(true);
    setError('');
    try {
      const result = await api<Policy>('/negotiation/policy', {
        method: 'PUT',
        body: JSON.stringify({
          expected_version: policy.version,
          enabled: policy.enabled,
          auto_accept: policy.auto_accept,
          max_promise_days: Number(data.get('max_promise_days')),
          max_installments: Number(data.get('max_installments')),
          max_discount_bps: rubles(String(data.get('max_discount_percent'))),
          allowed_kinds: policy.allowed_kinds,
        }),
      });
      setPolicy(result);
      notify(`Правила сохранены. Версия ${result.version}.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPolicyBusy(false);
    }
  }
  const proposalRequest = useRef<{ body: string; key: string } | null>(null);
  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError('');
    try {
      const promise = kind === 'promise' || kind === 'installment';
      const schedule =
        kind === 'installment'
          ? installments.map((item) => ({ date: item.date, amount: rubles(item.amount) }))
          : [];
      const finalDate =
        kind === 'installment'
          ? schedule
              .map((item) => item.date)
              .sort()
              .at(-1)
          : dueOn;
      const request = {
        invoice_id: invoiceId,
        kind,
        amount: promise ? rubles(amount) : null,
        due_on: promise ? finalDate : null,
        installments: schedule,
        discount_bps: kind === 'discount' ? rubles(String(data.get('discount_percent'))) : null,
        ambiguous,
        confirmed_by_operator: confirmed,
        evidence: String(data.get('evidence')).trim(),
        expires_on: expiresOn,
      };
      const body = JSON.stringify(request);
      if (proposalRequest.current?.body !== body)
        proposalRequest.current = { body, key: crypto.randomUUID() };
      await post<Proposal>('/negotiation/proposals', {
        ...request,
        idempotency_key: proposalRequest.current.key,
      });
      await reload();
      proposalRequest.current = null;
      form.reset();
      setAmount('');
      setConfirmed(false);
      notify('Предложение зарегистрировано. Проверьте результат проверки.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function proposalChanged() {
    const [items, forecast] = await Promise.all([
      api<{ items: Proposal[] }>('/negotiation/proposals'),
      api<Forecast>('/forecast'),
    ]);
    setProposals(items.items);
    setForecast(forecast);
    onChanged();
  }
  const selectedInvoice = invoices.find((i) => i.id === invoiceId);
  return (
    <div className="mandato-services">
      <DeskHeading
        eyebrow="СЦЕНАРИИ ПОСТУПЛЕНИЙ И ПРАВИЛА ДОГОВОРЁННОСТЕЙ"
        title="Следующий шаг — с основанием."
        action={
          <button
            disabled={busy || policyBusy}
            className="button button-outline"
            onClick={() => void refresh()}
          >
            <RefreshCw size={16} />
            Обновить
          </button>
        }
      >
        Прогноз опирается на подтверждённую историю. Решения по предложениям проверяются по текущему
        остатку и разрешениям.
      </DeskHeading>
      <DeskError>{error}</DeskError>
      <section className="ms-card">
        <div className="ms-card-heading">
          <h2>
            <TrendingUp size={20} /> Поступления на 7, 30 и 60 дней
          </h2>
          {forecast && <span className="ms-status">На {dateText(forecast.as_of)}</span>}
        </div>
        {!forecast ? (
          <p>Загружаем расчёт…</p>
        ) : (
          <>
            <p>
              {forecast.method === 'empirical_due_cohort_v1'
                ? 'Сценарий по истории счетов на сопоставимом сроке относительно даты оплаты. Учитываются подтверждённые банковские распределения.'
                : 'Метод расчёта требует дополнительной проверки.'}
            </p>
            {forecast.status === 'available' ? (
              <div className="ms-forecast-grid">
                {forecast.horizons.map((h) => (
                  <article key={h.days}>
                    <span>В течение {h.days} дней</span>
                    <strong>
                      {h.expected_amount === null
                        ? 'Недостаточно данных'
                        : money(h.expected_amount)}
                    </strong>
                    <small>
                      Наблюдавшийся диапазон:{' '}
                      {h.low_scenario === null || h.high_scenario === null
                        ? '—'
                        : `${money(h.low_scenario)} — ${money(h.high_scenario)}`}
                    </small>
                  </article>
                ))}
              </div>
            ) : (
              <div className="ms-neutral">
                <h3>Пока недостаточно сопоставимой истории</h3>
                <p>
                  Оценка появится, когда будет достаточно датированных банковских оплат и
                  сопоставимых счетов. Отсутствие оценки не означает нулевые поступления.
                </p>
              </div>
            )}
            <dl className="ms-metrics">
              <div>
                <dt>Открытый остаток</dt>
                <dd>{money(forecast.coverage.open_balance)}</dd>
              </div>
              <div>
                <dt>Остаток с оценкой</dt>
                <dd>{money(forecast.coverage.covered_balance)}</dd>
              </div>
              <div>
                <dt>Без достаточной истории</dt>
                <dd>{money(forecast.coverage.uncovered_balance)}</dd>
              </div>
              <div>
                <dt>Исключено из расчёта</dt>
                <dd>{money(forecast.coverage.excluded_balance)}</dd>
              </div>
              <div>
                <dt>Счетов в истории сравнения</dt>
                <dd>{forecast.coverage.training_invoices}</dd>
              </div>
              <div>
                <dt>Банковских распределений</dt>
                <dd>{forecast.coverage.bank_allocations}</dd>
              </div>
            </dl>
            <details>
              <summary>Основания и ограничения расчёта</summary>
              <ul className="ms-notes">
                {forecast.limitations.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
              {forecast.invoices.length > 0 && (
                <ul className="ms-notes">
                  {forecast.invoices.map((item) => (
                    <li key={item.invoice_id}>
                      <strong>
                        {invoices.find((i) => i.id === item.invoice_id)?.number ?? 'Счёт'}
                      </strong>
                      :{' '}
                      {item.status === 'available'
                        ? 'Включён в оценку'
                        : item.reasons
                            ?.map(
                              (code) => forecastReasons[code] ?? 'Нужна проверка исходных данных'
                            )
                            .join('; ')}
                    </li>
                  ))}
                </ul>
              )}
            </details>
          </>
        )}
      </section>
      <div className="ms-columns">
        <section className="ms-card">
          <div className="ms-card-heading">
            <h2>
              <ShieldCheck size={20} /> Правила переговоров
            </h2>
            {policy && <span className="ms-status">Версия {policy.version}</span>}
          </div>
          {!policy ? (
            <p>Загружаем правила…</p>
          ) : (
            <form className="ms-form" onSubmit={savePolicy} key={policy.version}>
              <label className="ms-check">
                <input
                  type="checkbox"
                  checked={policy.enabled}
                  disabled={policyBusy}
                  onChange={(e) => setPolicy({ ...policy, enabled: e.target.checked })}
                />{' '}
                Разрешить обработку предложений
              </label>
              <label className="ms-check">
                <input
                  type="checkbox"
                  checked={policy.auto_accept}
                  disabled={policyBusy}
                  onChange={(e) => setPolicy({ ...policy, auto_accept: e.target.checked })}
                />{' '}
                Принимать внутри согласованных пределов
              </label>
              <p className="ms-note">
                Принятие — внутренний статус. Исполнение выполняется отдельно; письма и документы
                контрагенту не отправляются. Разрешения по контрагентам задаются в «Финансах».
              </p>
              <div className="ms-fields">
                <label className="field">
                  Максимальный срок обещания, дней
                  <input
                    name="max_promise_days"
                    type="number"
                    required
                    min={1}
                    max={365}
                    defaultValue={policy.max_promise_days}
                  />
                </label>
                <label className="field">
                  Максимум платежей в графике
                  <input
                    name="max_installments"
                    type="number"
                    required
                    min={1}
                    max={60}
                    defaultValue={policy.max_installments}
                  />
                </label>
                <label className="field">
                  Предел запроса скидки, %
                  <input
                    name="max_discount_percent"
                    type="number"
                    required
                    min={0}
                    max={100}
                    step="0.01"
                    defaultValue={policy.max_discount_bps / 100}
                  />
                </label>
              </div>
              <fieldset className="ms-fieldset">
                <legend>Разрешённые предложения</legend>
                {(Object.keys(kinds) as Kind[]).map((kind) => (
                  <label key={kind} className="ms-check">
                    <input
                      type="checkbox"
                      checked={policy.allowed_kinds.includes(kind)}
                      disabled={policyBusy}
                      onChange={(e) =>
                        setPolicy({
                          ...policy,
                          allowed_kinds: e.target.checked
                            ? [...policy.allowed_kinds, kind]
                            : policy.allowed_kinds.filter((k) => k !== kind),
                        })
                      }
                    />
                    {kinds[kind]}
                  </label>
                ))}
              </fieldset>
              <button className="button button-dark" disabled={policyBusy || busy}>
                <Check size={16} />
                {policyBusy ? 'Сохраняем…' : 'Сохранить правила'}
              </button>
            </form>
          )}
        </section>
        <section className="ms-card">
          <h2>
            <Plus size={20} /> Зарегистрировать предложение
          </h2>
          <p>
            Внесите подтверждённые условия из обращения покупателя. Система проверит их перед
            принятием и повторно перед исполнением.
          </p>
          {!invoices.length ? (
            <div className="ms-neutral">
              <h3>Сначала добавьте счета</h3>
              <p>Предложение должно относиться к конкретному обязательству из реестра.</p>
            </div>
          ) : (
            <form className="ms-form" onSubmit={propose}>
              <InvoiceSelect
                invoices={invoices}
                value={invoiceId}
                onChange={(id) => {
                  setInvoiceId(id);
                  setConfirmed(false);
                }}
              />
              {selectedInvoice && (
                <p className="ms-note">
                  Текущий остаток: {money(selectedInvoice.balance)}. Новое обещание заменит прежний
                  активный график по этому счёту.
                </p>
              )}
              <label className="field">
                Тип предложения
                <select
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value as Kind);
                    setConfirmed(false);
                  }}
                >
                  {(Object.keys(kinds) as Kind[]).map((kind) => (
                    <option value={kind} key={kind}>
                      {kinds[kind]}
                    </option>
                  ))}
                </select>
              </label>
              {(kind === 'promise' || kind === 'installment') && (
                <label className="field">
                  Обещанная сумма, ₽
                  <input
                    required
                    inputMode="decimal"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="В пределах текущего остатка"
                  />
                </label>
              )}
              {kind === 'promise' && (
                <label className="field">
                  Дата обещанной оплаты
                  <input
                    type="date"
                    required
                    min={today()}
                    value={dueOn}
                    onChange={(e) => setDueOn(e.target.value)}
                  />
                </label>
              )}
              {kind === 'installment' && (
                <fieldset className="ms-fieldset">
                  <legend>График платежей</legend>
                  {installments.map((item, index) => (
                    <div className="ms-schedule" key={item.id}>
                      <label className="field">
                        Дата платежа {index + 1}
                        <input
                          type="date"
                          required
                          min={today()}
                          value={item.date}
                          onChange={(e) =>
                            setInstallments(
                              installments.map((row) =>
                                row.id === item.id ? { ...row, date: e.target.value } : row
                              )
                            )
                          }
                        />
                      </label>
                      <label className="field">
                        Сумма платежа {index + 1}, ₽
                        <input
                          required
                          inputMode="decimal"
                          value={item.amount}
                          onChange={(e) =>
                            setInstallments(
                              installments.map((row) =>
                                row.id === item.id ? { ...row, amount: e.target.value } : row
                              )
                            )
                          }
                        />
                      </label>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Удалить платёж ${index + 1}`}
                        disabled={installments.length === 1}
                        onClick={() =>
                          setInstallments(installments.filter((row) => row.id !== item.id))
                        }
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="button button-outline"
                    disabled={installments.length >= 60}
                    onClick={() =>
                      setInstallments([
                        ...installments,
                        { id: crypto.randomUUID(), date: futureDate(7), amount: '' },
                      ])
                    }
                  >
                    <Plus size={16} />
                    Добавить платёж
                  </button>
                  <p className="ms-note">
                    Сумма графика должна совпадать с обещанной суммой. Общий срок — последняя дата
                    графика.
                  </p>
                </fieldset>
              )}
              {kind === 'discount' && (
                <>
                  <label className="field">
                    Запрошенная скидка, %
                    <input
                      type="number"
                      name="discount_percent"
                      required
                      min="0.01"
                      max={100}
                      step="0.01"
                    />
                  </label>
                  <p className="ms-note">
                    Исполнение сохранит запрос для отдельного решения. Списание задолженности здесь
                    не выполняется.
                  </p>
                </>
              )}
              {kind === 'payment_claim' && (
                <p className="ms-note">
                  Сообщение покупателя не подтверждает поступление. После исполнения останется
                  задача сверки с выпиской.
                </p>
              )}
              <label className="field">
                Срок действия предложения
                <input
                  type="date"
                  required
                  min={today()}
                  value={expiresOn}
                  onChange={(e) => setExpiresOn(e.target.value)}
                />
              </label>
              <label className="field">
                Обращение и основание условий
                <textarea
                  name="evidence"
                  required
                  maxLength={5000}
                  placeholder="Что сообщил покупатель, когда и на основании какой переписки"
                />
              </label>
              <label className="ms-check">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />{' '}
                Условия проверены по обращению покупателя
              </label>
              <label className="ms-check">
                <input
                  type="checkbox"
                  checked={ambiguous}
                  onChange={(e) => setAmbiguous(e.target.checked)}
                />{' '}
                В обращении остались неоднозначные условия
              </label>
              <button className="button button-dark" disabled={busy || policyBusy || !invoiceId}>
                <ChevronRight size={16} />
                {busy ? 'Проверяем…' : 'Проверить предложение'}
              </button>
            </form>
          )}
        </section>
      </div>
      <section className="ms-card">
        <h2>
          <Clock3 size={20} /> Предложения и решения
        </h2>
        <p>
          Принятие и исполнение фиксируются отдельно. Исходящая отправка через этот раздел не
          выполняется.
        </p>
        {!proposals.length ? (
          <div className="ms-neutral">
            <p>Зарегистрированных предложений пока нет.</p>
          </div>
        ) : (
          <div className="ms-proposals">
            {proposals.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                proposal={proposal}
                invoice={invoices.find((i) => i.id === proposal.invoice_id)}
                onChanged={proposalChanged}
                notify={notify}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ProposalCard({
  proposal,
  invoice,
  onChanged,
  notify,
}: {
  proposal: Proposal;
  invoice?: Invoice;
  onChanged: () => Promise<void>;
  notify: DeskProps['notify'];
}) {
  const [busy, setBusy] = useState(false),
    [reason, setReason] = useState(''),
    [error, setError] = useState('');
  async function action(kind: 'approve' | 'reject' | 'execute') {
    setBusy(true);
    setError('');
    try {
      await post(
        `/negotiation/proposals/${proposal.id}/${kind === 'execute' ? 'execute' : 'review'}`,
        kind === 'execute' ? {} : { decision: kind, reason: reason.trim() }
      );
      await onChanged();
      notify(
        kind === 'execute'
          ? 'Действие исполнено в кабинете. Исходящая отправка не выполнялась.'
          : kind === 'approve'
            ? 'Предложение принято. Для исполнения используйте отдельную кнопку.'
            : 'Предложение отклонено.'
      );
    } catch (e) {
      setError((e as Error).message);
      await onChanged().catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  const canReview = ['review_required', 'accepted'].includes(proposal.status);
  return (
    <article className="ms-proposal">
      <div className="ms-card-heading">
        <div>
          <h3>{kinds[proposal.kind]}</h3>
          <p>{invoice ? `${invoice.company} · счёт ${invoice.number}` : 'Счёт из реестра'}</p>
        </div>
        <span className={`ms-status ms-status-${proposal.status}`}>
          {states[proposal.status] ?? 'Требуется проверка статуса'}
        </span>
      </div>
      <dl className="ms-proposal-facts">
        <div>
          <dt>Создано</dt>
          <dd>{dateText(proposal.created_at)}</dd>
        </div>
        <div>
          <dt>Правила</dt>
          <dd>Версия {proposal.policy_version}</dd>
        </div>
        {proposal.terms.amount != null && (
          <div>
            <dt>Обещанная сумма</dt>
            <dd>{money(proposal.terms.amount)}</dd>
          </div>
        )}
        {proposal.terms.due_on && (
          <div>
            <dt>Срок оплаты</dt>
            <dd>{dateText(proposal.terms.due_on)}</dd>
          </div>
        )}
        {proposal.terms.discount_bps != null && (
          <div>
            <dt>Запрос скидки</dt>
            <dd>{proposal.terms.discount_bps / 100}%</dd>
          </div>
        )}
        <div>
          <dt>Действует до</dt>
          <dd>{dateText(proposal.terms.expires_on)}</dd>
        </div>
      </dl>
      <p className="ms-evidence">{proposal.terms.evidence}</p>
      {proposal.terms.installments.length > 0 && (
        <ul className="ms-notes">
          {proposal.terms.installments.map((item, index) => (
            <li key={index}>
              {dateText(item.date)} · {money(item.amount)}
            </li>
          ))}
        </ul>
      )}
      {proposal.reasons.length > 0 && (
        <ul className="ms-errors">
          {proposal.reasons.map((code) => (
            <li key={code}>
              {reasons[code] ??
                'Есть ограничение. Уточните условия и полномочия перед новым предложением.'}
            </li>
          ))}
        </ul>
      )}
      {proposal.status === 'handoff' && (
        <p className="ms-note">
          Уточните условия или разрешения и зарегистрируйте новое предложение. Ограничения этого
          предложения не обходятся ручным согласием.
        </p>
      )}
      {proposal.outcome && (
        <div className="ms-neutral">
          <p>
            {outcomes[proposal.outcome.action] ?? 'Результат сохранён для обработки сотрудником.'}
          </p>
          {proposal.outcome.concession_amount != null && (
            <p>
              Сумма запрошенной уступки: {money(proposal.outcome.concession_amount)}. Требуется
              отдельное согласование списания.
            </p>
          )}
          <p className="ms-note">
            {proposal.outcome.external_delivery
              ? 'Для подтверждения внешней доставки проверьте канал отправки.'
              : 'Контрагенту ничего не отправлено.'}
          </p>
        </div>
      )}
      <DeskError>{error}</DeskError>
      {canReview && (
        <div className="ms-form">
          <label className="field">
            Основание решения
            <textarea maxLength={3000} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="ms-actions">
            {proposal.status === 'review_required' && (
              <button
                className="button button-outline"
                disabled={busy || !reason.trim()}
                onClick={() => void action('approve')}
              >
                <Check size={16} />
                Принять предложение
              </button>
            )}
            <button
              className="button button-outline"
              disabled={busy || !reason.trim()}
              onClick={() => void action('reject')}
            >
              <X size={16} />
              Отклонить
            </button>
            {proposal.status === 'accepted' && (
              <button
                className="button button-dark"
                disabled={busy}
                onClick={() => void action('execute')}
              >
                <Check size={16} />
                Исполнить в кабинете
              </button>
            )}
          </div>
        </div>
      )}
      <details>
        <summary>История решений</summary>
        <ul className="ms-notes">
          {proposal.events.map((event) => (
            <li key={event.id}>
              {dateText(event.created_at)} · {eventNames[event.type] ?? 'Состояние обновлено'}
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}
