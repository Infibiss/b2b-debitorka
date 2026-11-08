import { ArchiveEvidence } from './ArchiveEvidence';
import { navigate, useRouteField, useWorkContext } from '../navigation';
import { useEffect, useState } from 'react';
import { ArrowLeft, FileText, Plus, Scale, Download, CheckCircle2 } from 'lucide-react';
import { api, post, patch, money, dateText, today, type Invoice, type Settings } from '../api';
import { Dialog } from './Dialog';
import { tariff } from '../pricing';
import {
  DeskHeading,
  OperationForm,
  InvoiceSelect,
  DeskError,
  EmptyCard,
  value,
  rubles,
  type DeskProps,
} from './OperationsUI';
import './legal.css';

type Party = {
  kind: string;
  name: string;
  inn: string;
  ogrn: string;
  address: string;
  email: string;
  phone: string;
  bank_details: string;
  birth_on: string | null;
  birth_place: string;
  birth_details_unknown: boolean;
};
type Facts = {
  creditor: Party;
  debtor: Party;
  contract_number: string;
  contract_date: string | null;
  obligation_description: string;
  performance_description: string;
  due_basis: string;
  legal_basis: string;
  court_name: string;
  court_address: string;
  jurisdiction_basis: string;
  undisputed: boolean;
  business_debt_confirmed: boolean;
  special_regimes_checked: boolean;
  pretrial_days: number;
  pretrial_basis: string;
  fee_agreement_reference: string;
  fee_start_on: string | null;
  fee_model_version?: string;
  lawyer_agreement_reference?: string;
  responsible_lawyer?: string;
  lawyer_authority?: string;
  review_due_on?: string | null;
};
type CalculationInput = {
  through_on: string;
  sanction: string;
  penalty_agreed: boolean;
  penalty_daily_percent?: string;
  penalty_basis: string;
  penalty_cap_amount?: number;
  combination_basis: string;
  rate_override?: unknown[];
  override_reason: string;
  excluded_periods: unknown[];
  opening_reductions: unknown[];
  invoice_opening_reductions?: Record<string, unknown[]>;
};
type Calculation = {
  principal_amount: number;
  interest_amount: number;
  penalty_amount: number;
  total_claim_amount: number;
  fee_claim_amount: number;
  fee_order_amount: number;
  rates_version: string;
  rates_source: string;
  through_on: string;
  order_eligible: boolean;
  line_items: {
    from_on: string;
    to_on: string;
    days: number;
    principal_amount: number;
    annual_percent: string;
    denominator: number;
    interest_amount: number;
    penalty_amount: number;
    excluded: boolean;
    basis: string;
  }[];
};
type Evidence = {
  id: string;
  kind: string;
  title: string;
  reference: string;
  occurred_on: string;
  sha256: string;
  invoice_ids?: string[];
};
type LegalDocument = {
  id: string;
  kind: string;
  version: number;
  created_at: string;
  status: string;
  stale: boolean;
  sha256: string;
  download_url: string;
  calculation: Calculation;
  reviews: {
    decision: string;
    reviewer_name: string;
    authority_reference: string;
    notes: string;
    created_at: string;
  }[];
};
type Milestone = {
  id: string;
  stage: string;
  occurred_on: string;
  reference: string;
  notes: string;
  manual: boolean;
};
type Fee = {
  configured: boolean;
  lawyer_configured: boolean;
  requires_fee_model_confirmation: boolean;
  agreement_reference: string;
  lawyer_agreement_reference: string;
  confirmed_recovery_amount: number;
  fee_amount: number;
  pretrial_fee_amount: number;
  judicial_package_amount: number;
  lawyer_fee_amount: number;
  excluded_manual_amount: number;
  excluded_before_start_amount: number;
  excluded_before_claim_amount: number;
  ambiguous_recovery_amount: number;
  lawyer_unconfigured_recovery_amount: number;
  rounding_difference: number;
  lawyer_rounding_difference: number;
  package_items: {
    kind: string;
    document_id: string;
    filed_on: string;
    reference: string;
    tariff_amount: number;
    fee_amount: number;
    billable: boolean;
  }[];
  line_items: {
    payment_id: string;
    paid_on: string;
    stage: string;
    amount: number;
    recipient: 'mandato' | 'lawyer' | null;
    rate_percent: string | null;
    fee_amount: number;
    date_ordering_ambiguous: boolean;
  }[];
};
type LegalCase = {
  id: string;
  invoice_id: string;
  facts: Facts;
  facts_revision: number;
  suggested_contract_number?: string;
  invoice: Invoice;
  invoice_ids?: string[];
  invoices?: Invoice[];
  invoice_count?: number;
  balance?: number;
  next_action?: string;
  stage: string;
  pretrial: {
    sent_on: string | null;
    ready_on: string | null;
    days: number;
    ready: boolean;
    applicable: boolean;
  };
  evidence?: Evidence[];
  documents?: LegalDocument[];
  milestones?: Milestone[];
  fee?: Fee;
  calculation?: Calculation | null;
};
const kinds: Record<string, string> = {
  pretrial_claim: 'Досудебная претензия',
  court_order: 'Заявление о судебном приказе',
  statement_of_claim: 'Исковое заявление',
};
const evidenceKinds: Record<string, string> = {
  contract: 'Договор',
  performance: 'Исполнение обязательства',
  reconciliation: 'Акт сверки',
  claim_dispatch: 'Отправка претензии',
  claim_delivery: 'Доставка претензии',
  duty_payment: 'Оплата госпошлины',
  application_copy_sent: 'Отправка копии заявления',
  filing_receipt: 'Квитанция подачи',
  court_act: 'Судебный акт',
  order_cancellation: 'Определение об отмене приказа',
  writ: 'Исполнительный лист',
  bank_submission: 'Предъявление в банк',
  fssp_submission: 'Предъявление в ФССП',
  other: 'Иное доказательство',
};
const stages: Record<string, string> = {
  intake: 'Подготовка',
  claim_sent: 'Претензия отправлена',
  claim_delivered: 'Претензия доставлена',
  filed: 'Подача в суд',
  order_issued: 'Судебный приказ получен',
  order_cancelled: 'Судебный приказ отменён',
  judgment: 'Решение суда получено',
  writ_received: 'Исполнительный лист получен',
  bank_submitted: 'Предъявление в банк',
  fssp_submitted: 'Предъявление в ФССП',
  stopped: 'Сопровождение остановлено',
  closed: 'Дело закрыто',
};
const statuses: Record<string, string> = {
  draft: 'Требует проверки',
  approved: 'Согласовано',
  changes_requested: 'Нужны исправления',
  stale: 'Устарела',
};
const tabs = ['Факты', 'Расчёт', 'Доказательства', 'Документы', 'Ход дела', 'Гонорар'];

function Field({
  label,
  name,
  initial = '',
  type = 'text',
  required = false,
  area = false,
  max,
}: {
  label: string;
  name: string;
  initial?: string | number | null;
  type?: string;
  required?: boolean;
  area?: boolean;
  max?: string;
}) {
  return (
    <label className={`field${area ? ' full-width' : ''}`}>
      {label}
      {area ? (
        <textarea name={name} defaultValue={initial ?? ''} required={required} />
      ) : (
        <input name={name} type={type} defaultValue={initial ?? ''} required={required} max={max} />
      )}
    </label>
  );
}
function Check({
  name,
  label,
  checked = false,
  required = false,
}: {
  name: string;
  label: string;
  checked?: boolean;
  required?: boolean;
}) {
  return (
    <label className="consent full-width">
      <input name={name} type="checkbox" defaultChecked={checked} required={required} />
      {label}
    </label>
  );
}
function PartyFields({ prefix, party, role }: { prefix: string; party: Party; role: string }) {
  const [kind, setKind] = useState(party.kind);
  return (
    <fieldset id={`facts-${prefix}`} className="legal-fieldset full-width">
      <legend>{prefix === 'creditor' ? 'Кредитор' : 'Должник'}</legend>
      <div className="legal-field-grid">
        <label className="field">
          Тип {role}
          <select
            name={`${prefix}.kind`}
            defaultValue={party.kind}
            onChange={(e) => setKind(e.target.value)}
          >
            <option value="organization">Организация</option>
            <option value="sole_proprietor">Индивидуальный предприниматель</option>
          </select>
        </label>
        <Field
          label={`Наименование ${role}`}
          name={`${prefix}.name`}
          initial={party.name}
          required
        />
        <Field label={`ИНН ${role}`} name={`${prefix}.inn`} initial={party.inn} required />
        <Field
          label={`ОГРН / ОГРНИП ${role}`}
          name={`${prefix}.ogrn`}
          initial={party.ogrn}
          required
        />
        <Field
          label={`Адрес ${role}`}
          name={`${prefix}.address`}
          initial={party.address}
          required
          area
        />
        <Field
          label={`Email ${role}`}
          name={`${prefix}.email`}
          initial={party.email}
          type="email"
        />
        <Field label={`Телефон ${role}`} name={`${prefix}.phone`} initial={party.phone} />
        <Field
          label={`Банковские реквизиты ${role}`}
          name={`${prefix}.bank_details`}
          initial={party.bank_details}
          required={prefix === 'creditor'}
          area
        />
        {kind === 'sole_proprietor' && (
          <>
            <Field
              label={`Дата рождения ${role}`}
              name={`${prefix}.birth_on`}
              initial={party.birth_on}
              type="date"
              max={today()}
            />
            <Field
              label={`Место рождения ${role}`}
              name={`${prefix}.birth_place`}
              initial={party.birth_place}
            />
            <Check
              name={`${prefix}.birth_details_unknown`}
              label={`Дата и место рождения ${role} неизвестны`}
              checked={party.birth_details_unknown}
            />
          </>
        )}
      </div>
    </fieldset>
  );
}
function readParty(data: FormData, prefix: string): Party {
  const key = (name: string) => value(data, `${prefix}.${name}`);
  return {
    kind: key('kind'),
    name: key('name'),
    inn: key('inn'),
    ogrn: key('ogrn'),
    address: key('address'),
    email: key('email'),
    phone: key('phone'),
    bank_details: key('bank_details'),
    birth_on: key('birth_on') || null,
    birth_place: key('birth_place'),
    birth_details_unknown: data.has(`${prefix}.birth_details_unknown`),
  };
}
type RepeatedField = { key: string; label: string; type?: string };
function RepeatableRows({
  name,
  title,
  addLabel,
  fields,
}: {
  name: string;
  title: string;
  addLabel: string;
  fields: RepeatedField[];
}) {
  const [rows, setRows] = useState<number[]>([]);
  const [sequence, setSequence] = useState(0);
  return (
    <fieldset className="legal-fieldset legal-repeatable">
      <legend>{title}</legend>
      {rows.map((id, index) => (
        <div className="legal-repeatable-row" key={id}>
          <div className="legal-repeatable-heading">
            <strong>Запись {index + 1}</strong>
            <button
              className="button button-ghost button-small"
              type="button"
              aria-label={`Удалить: ${title}, запись ${index + 1}`}
              onClick={() => setRows(rows.filter((row) => row !== id))}
            >
              Удалить
            </button>
          </div>
          <div className="legal-field-grid">
            {fields.map((field) => (
              <Field
                key={field.key}
                label={field.label}
                name={`${name}.${id}.${field.key}`}
                type={field.type ?? 'text'}
                required
              />
            ))}
          </div>
        </div>
      ))}
      {!rows.length && <p className="ops-muted">Не указано</p>}
      <button
        className="button button-ghost button-small"
        type="button"
        onClick={() => {
          setRows([...rows, sequence]);
          setSequence(sequence + 1);
        }}
      >
        <Plus size={14} />
        {addLabel}
      </button>
    </fieldset>
  );
}
function repeatedInput(data: FormData, name: string): Record<string, string | number>[] {
  const groups = new Map<string, Record<string, string | number>>();
  for (const [key, raw] of data.entries()) {
    const [prefix, id, field] = key.split('.');
    if (prefix !== name || !id || !field) continue;
    const row = groups.get(id) ?? {};
    const text = String(raw).trim();
    row[field] =
      name.startsWith('opening_reductions') && field === 'amount'
        ? rubles(text)
        : field === 'annual_percent'
          ? text.replace(',', '.')
          : text;
    groups.set(id, row);
  }
  return [...groups.values()];
}

export default function LegalDesk({ invoices, onChanged, notify }: DeskProps) {
  const { invoiceId } = useWorkContext();
  const [newInvoiceId, setNewInvoiceId] = useState(invoiceId || '');
  const [archiveInvoiceId, setArchiveInvoiceId] = useState('');
  const [contractGroups, setContractGroups] = useState<
    { invoice_ids: string[]; contract_known: boolean; contract_number: string }[]
  >([]);
  const [legalId] = useRouteField<string>('legal', '');
  const [tab, setTab] = useRouteField<string>('legalTab', 'Факты');
  const [factsStep, setFactsStep] = useRouteField<string>('factsStep', 'contract');
  const [cases, setCases] = useState<LegalCase[]>([]),
    [selected, setSelected] = useState<LegalCase | null>(null),
    [settings, setSettings] = useState<Settings | null>(null),
    [opening, setOpening] = useState(false),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [reviewing, setReviewing] = useState<LegalDocument | null>(null),
    [calculation, setCalculation] = useState<Calculation | null>(null),
    [calculationInput, setCalculationInput] = useState<CalculationInput | null>(null),
    [sanction, setSanction] = useState('none'),
    [decision, setDecision] = useState('');
  async function loadList() {
    const result = await api<{ items: LegalCase[] }>('/legal/cases');
    setCases(result.items);
  }
  async function refreshCase(id: string) {
    const next = await api<LegalCase>(`/legal/cases/${id}`);
    setSelected(next);
    return next;
  }
  useEffect(() => {
    let alive = true;
    Promise.all([
      api<{ items: LegalCase[] }>('/legal/cases'),
      api<Settings>('/settings'),
      api<{ items: { invoice_ids: string[]; contract_known: boolean; contract_number: string }[] }>(
        '/workflow/cases'
      ),
    ])
      .then(([list, prefs, groups]) => {
        if (alive) {
          setCases(list.items);
          setSettings(prefs);
          setContractGroups(groups.items);
        }
      })
      .catch((e) => {
        if (alive) setError((e as Error).message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (loading) return;
    let alive = true;
    const id =
      legalId ||
      cases.find((c) => c.invoice_id === invoiceId || c.invoice_ids?.includes(invoiceId))?.id;
    if (id) {
      void api<LegalCase>(`/legal/cases/${id}`)
        .then((item) => {
          if (alive) {
            setSelected(item);
            setError('');
          }
        })
        .catch((e) => {
          if (alive) {
            setSelected(null);
            setError((e as Error).message);
          }
        });
      if (!legalId) navigate({ legal: id }, true);
    } else setSelected(null);
    return () => {
      alive = false;
    };
  }, [legalId, invoiceId, loading]);
  async function openCase(item: LegalCase) {
    setError('');
    setCalculation(null);
    setCalculationInput(null);
    setSanction('none');
    navigate({ legal: item.id, legalTab: 'Факты', context: item.invoice_id });
    try {
      await refreshCase(item.id);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const done = () => {
    onChanged();
    void loadList().catch((e) => setError((e as Error).message));
  };
  const proofs = selected?.evidence ?? [],
    documents = selected?.documents ?? [];
  const archiveSource = selected?.invoice_ids?.includes(archiveInvoiceId)
    ? archiveInvoiceId
    : selected?.invoice_id || '';
  return (
    <div className="legal-desk">
      <DeskHeading
        eyebrow="ЮРИДИЧЕСКОЕ СОПРОВОЖДЕНИЕ"
        title="Претензии и суд"
        action={
          <button
            className="button button-dark"
            onClick={() => {
              setNewInvoiceId(
                invoices.some(
                  (inv) =>
                    inv.id === invoiceId &&
                    !cases.some((c) => (c.invoice_ids || [c.invoice_id]).includes(inv.id))
                )
                  ? invoiceId
                  : ''
              );
              setOpening(true);
            }}
          >
            <Plus size={16} />
            Новое дело
          </button>
        }
      >
        Рассчитайте требования, подготовьте претензию или иск и сохраните историю взыскания.
      </DeskHeading>
      <DeskError>{error}</DeskError>
      {!selected ? (
        <section className="ops-card">
          <div className="ops-card-heading">
            <div>
              <h2>Дела компании</h2>
              <p>
                Соберите счета одного договора в общее требование и передайте документы на проверку.
              </p>
            </div>
            <Scale size={22} />
          </div>
          {loading ? (
            <p className="ops-muted">Загружаем дела…</p>
          ) : !cases.length ? (
            <EmptyCard title="Юридических дел пока нет">
              Нажмите «Новое дело», выберите счёт и добавьте сведения о договоре.
            </EmptyCard>
          ) : (
            cases.map((item) => (
              <button
                className="ops-proposal-row"
                key={item.id}
                onClick={() => void openCase(item)}
              >
                <div className="ops-proposal-icon">
                  <FileText size={21} />
                </div>
                <div>
                  <strong>
                    {item.invoice.company} · {item.facts.contract_number || item.invoice.number}
                  </strong>
                  <span>{stages[item.stage] ?? item.stage}</span>
                  {item.facts.responsible_lawyer && (
                    <span>
                      {item.facts.responsible_lawyer}
                      {item.facts.review_due_on
                        ? ` · проверка до ${dateText(item.facts.review_due_on)}`
                        : ''}
                    </span>
                  )}
                </div>
                <strong>{money(item.balance ?? item.invoice.balance)}</strong>
              </button>
            ))
          )}
        </section>
      ) : (
        <>
          <div className="ops-detail-bar">
            <button
              className="button button-ghost button-small"
              onClick={() => {
                setSelected(null);
                navigate({ legal: null, context: null, legalTab: null });
              }}
            >
              <ArrowLeft size={14} />
              Все дела
            </button>
            <span className={`ops-badge legal-stage-${selected.stage}`}>
              {stages[selected.stage] ?? selected.stage}
            </span>
          </div>
          <div className="ops-context">
            <strong>
              {selected.invoice.company} ·{' '}
              {selected.facts.contract_number || selected.invoice.number}
            </strong>
            <span>
              Счетов: {selected.invoice_count || 1} · Остаток:{' '}
              {money(selected.balance ?? selected.invoice.balance)}
            </span>
            <span>
              Счета: {(selected.invoices || [selected.invoice]).map((inv) => inv.number).join(', ')}
            </span>
          </div>
          {selected.stage === 'order_cancelled' && (
            <div className="legal-case-next" role="status">
              <strong>Приказ отменён</strong>
              <p>Подготовьте иск и передайте его юристу на проверку.</p>
              <button className="button button-outline small" onClick={() => setTab('Документы')}>
                Перейти к документам
              </button>
            </div>
          )}
          <div className="ops-tabs legal-tabs" role="tablist" aria-label="Юридическое дело">
            {tabs.map((name) => (
              <button
                type="button"
                role="tab"
                aria-label={name}
                aria-selected={tab === name}
                key={name}
                onClick={() => setTab(name)}
              >
                {name}
                {name === 'Документы' && documents.length ? ` · ${documents.length}` : ''}
              </button>
            ))}
          </div>
          {tab === 'Факты' && (
            <section className="ops-card">
              <div className="ops-card-heading">
                <div>
                  <h2>Данные дела</h2>
                  <p>
                    Заполните стороны и условия договора. Реквизиты из реестра проверьте по
                    документам.
                  </p>
                </div>
              </div>
              <LegalReadiness item={selected} />
              <OperationForm
                allowIncomplete
                key={`${selected.id}-${selected.facts_revision}`}
                draftKey={`legal-facts:${selected.id}`}
                revision={String(selected.facts_revision)}
                label="Сохранить факты"
                submit={async (data) => {
                  if (
                    selected.fee?.requires_fee_model_confirmation &&
                    !data.has('confirm_fee_model')
                  )
                    throw new Error('Подтвердите новые условия на шаге «Вознаграждение».');
                  const f: Facts = {
                    creditor: readParty(data, 'creditor'),
                    debtor: readParty(data, 'debtor'),
                    contract_number: value(data, 'contract_number'),
                    contract_date: value(data, 'contract_date') || null,
                    obligation_description: value(data, 'obligation_description'),
                    performance_description: value(data, 'performance_description'),
                    due_basis: value(data, 'due_basis'),
                    legal_basis: value(data, 'legal_basis'),
                    court_name: value(data, 'court_name'),
                    court_address: value(data, 'court_address'),
                    jurisdiction_basis: value(data, 'jurisdiction_basis'),
                    undisputed: data.has('undisputed'),
                    business_debt_confirmed: data.has('business_debt_confirmed'),
                    special_regimes_checked: data.has('special_regimes_checked'),
                    pretrial_days: Number(value(data, 'pretrial_days')),
                    pretrial_basis: value(data, 'pretrial_basis'),
                    fee_agreement_reference: value(data, 'fee_agreement_reference'),
                    fee_start_on: value(data, 'fee_start_on') || null,
                    fee_model_version: tariff.version,
                    lawyer_agreement_reference: value(data, 'lawyer_agreement_reference'),
                    responsible_lawyer: value(data, 'responsible_lawyer'),
                    lawyer_authority: value(data, 'lawyer_authority'),
                    review_due_on: value(data, 'review_due_on') || null,
                  };
                  await patch(`/legal/cases/${selected.id}`, { facts: f });
                  await refreshCase(selected.id);
                  setCalculationInput(null);
                  setCalculation(null);
                }}
                onDone={() => {
                  notify('Факты сохранены');
                  done();
                }}
              >
                <nav className="legal-facts-nav full-width" aria-label="Разделы фактов">
                  {(
                    [
                      ['creditor', 'Кредитор'],
                      ['debtor', 'Должник'],
                      ['contract', 'Договор'],
                      ['court', 'Суд'],
                      ['fees', 'Вознаграждение'],
                      ['all', 'Все поля'],
                    ] as const
                  ).map(([id, label]) => (
                    <button
                      type="button"
                      key={id}
                      aria-pressed={factsStep === id}
                      onClick={() => setFactsStep(id)}
                    >
                      {label}
                    </button>
                  ))}
                </nav>
                <div
                  className="legal-step full-width"
                  hidden={!['creditor', 'all'].includes(factsStep)}
                >
                  <p>
                    Источник исходных реквизитов: настройки организации. Сверьте с документами
                    кредитора.
                  </p>
                  <PartyFields prefix="creditor" party={selected.facts.creditor} role="кредитора" />
                </div>
                <div
                  className="legal-step full-width"
                  hidden={!['debtor', 'all'].includes(factsStep)}
                >
                  <p>
                    Источник исходных реквизитов: реестр счетов. Сверьте с документами должника.
                  </p>
                  <PartyFields prefix="debtor" party={selected.facts.debtor} role="должника" />
                </div>
                <div
                  className="legal-step full-width"
                  hidden={!['contract', 'all'].includes(factsStep)}
                >
                  <p className="full-width">
                    Источник номера договора:{' '}
                    {selected.suggested_contract_number
                      ? `рабочее дело, ${selected.suggested_contract_number}`
                      : 'данные сотрудника'}
                    . Остальные условия подтвердите по договору и первичным документам.
                  </p>
                  <h3 id="facts-contract" className="full-width">
                    Обязательство и основание требования
                  </h3>
                  <Field
                    label="Ответственный юрист"
                    name="responsible_lawyer"
                    initial={selected.facts.responsible_lawyer}
                  />
                  <Field
                    label="Проверить до"
                    name="review_due_on"
                    type="date"
                    initial={selected.facts.review_due_on}
                  />
                  <Field
                    label="Полномочия юриста"
                    name="lawyer_authority"
                    initial={selected.facts.lawyer_authority}
                  />
                  <Field
                    label="Номер договора"
                    name="contract_number"
                    initial={selected.facts.contract_number || selected.suggested_contract_number}
                    required
                  />
                  <Field
                    label="Дата договора"
                    name="contract_date"
                    initial={selected.facts.contract_date}
                    type="date"
                    max={today()}
                    required
                  />
                  <Field
                    label="Содержание обязательства"
                    name="obligation_description"
                    initial={selected.facts.obligation_description}
                    area
                    required
                  />
                  <Field
                    label="Факт исполнения"
                    name="performance_description"
                    initial={selected.facts.performance_description}
                    area
                    required
                  />
                  <Field
                    label="Основание срока оплаты"
                    name="due_basis"
                    initial={selected.facts.due_basis}
                    area
                    required
                  />
                  <Field
                    label="Правовое основание требования"
                    name="legal_basis"
                    initial={selected.facts.legal_basis}
                    area
                    required
                  />
                  <Check
                    name="business_debt_confirmed"
                    label="Долг возник в предпринимательской деятельности"
                    checked={selected.facts.business_debt_confirmed}
                  />
                  <Check
                    name="special_regimes_checked"
                    label="Проверены специальные режимы, банкротство, моратории и давность"
                    checked={selected.facts.special_regimes_checked}
                  />
                  <Check
                    name="undisputed"
                    label="Требование бесспорно и подтверждено документами"
                    checked={selected.facts.undisputed}
                  />
                </div>
                <div
                  className="legal-step full-width"
                  hidden={!['court', 'all'].includes(factsStep)}
                >
                  <h3 id="facts-court" className="full-width">
                    Претензионный порядок и суд
                  </h3>
                  <Field
                    label="Срок претензии, календарных дней"
                    name="pretrial_days"
                    initial={selected.facts.pretrial_days}
                    type="number"
                    required
                  />
                  <Field
                    label="Основание претензионного срока"
                    name="pretrial_basis"
                    initial={selected.facts.pretrial_basis}
                    required
                  />
                  <Field
                    label="Наименование суда"
                    name="court_name"
                    initial={selected.facts.court_name}
                  />
                  <Field
                    label="Адрес суда"
                    name="court_address"
                    initial={selected.facts.court_address}
                  />
                  <Field
                    label="Основание подсудности"
                    name="jurisdiction_basis"
                    initial={selected.facts.jurisdiction_basis}
                    area
                  />
                </div>
                <div
                  className="legal-step full-width"
                  hidden={!['fees', 'all'].includes(factsStep)}
                >
                  <h3 id="facts-fees" className="full-width">
                    Условия вознаграждения
                  </h3>
                  <p className="ops-muted full-width">
                    Mandato: {tariff.pretrial_percent}% от поступлений после претензии и до подачи в
                    суд. Поданный пакет: приказ — {money(tariff.court_order_amount)}, иск —{' '}
                    {money(tariff.statement_of_claim_amount)}. Адвокату — {tariff.lawyer_percent}%
                    после подачи по отдельному соглашению. Условия подтверждает руководитель.
                  </p>
                  {selected.fee?.requires_fee_model_confirmation && (
                    <label className="consent full-width">
                      <input type="checkbox" name="confirm_fee_model" required />
                      Подтверждаю переход с прежних условий на {tariff.pretrial_percent}%, фикс за
                      судебные пакеты и отдельные 12% адвокату по согласованным договорам
                    </label>
                  )}
                  <Field
                    label="Договор сопровождения"
                    name="fee_agreement_reference"
                    initial={selected.facts.fee_agreement_reference}
                  />
                  <Field
                    label="Дата начала сопровождения"
                    name="fee_start_on"
                    initial={selected.facts.fee_start_on}
                    type="date"
                    max={today()}
                  />
                  <Field
                    label="Отдельное соглашение с адвокатом"
                    name="lawyer_agreement_reference"
                    initial={selected.facts.lawyer_agreement_reference}
                  />
                </div>
              </OperationForm>
            </section>
          )}
          {tab === 'Расчёт' && (
            <section className="ops-card">
              <div className="ops-card-heading">
                <div>
                  <h2>Расчёт требований</h2>
                  <p>
                    Выберите применимые условия начисления. Оплаты и корректировки учитываются по
                    финансовому реестру.
                  </p>
                </div>
              </div>
              <OperationForm
                label="Рассчитать требования"
                submit={async (data) => {
                  const rates = repeatedInput(data, 'rate_override');
                  const input: CalculationInput = {
                    through_on: value(data, 'through_on'),
                    sanction: value(data, 'sanction'),
                    penalty_agreed: data.has('penalty_agreed'),
                    penalty_basis: value(data, 'penalty_basis'),
                    combination_basis: value(data, 'combination_basis'),
                    override_reason: value(data, 'override_reason'),
                    excluded_periods: repeatedInput(data, 'excluded_periods'),
                    opening_reductions: repeatedInput(data, 'opening_reductions'),
                  };
                  if ((selected.invoices?.length || 0) > 1) {
                    input.invoice_opening_reductions = Object.fromEntries(
                      selected.invoices!.map((inv) => [
                        inv.id,
                        repeatedInput(data, `opening_reductions:${inv.id}`),
                      ])
                    );
                  }
                  if (value(data, 'penalty_daily_percent'))
                    input.penalty_daily_percent = value(data, 'penalty_daily_percent');
                  if (value(data, 'penalty_cap_amount'))
                    input.penalty_cap_amount = rubles(value(data, 'penalty_cap_amount'));
                  if (rates.length) input.rate_override = rates;
                  const result = await post<Calculation>(
                    `/legal/cases/${selected.id}/calculation`,
                    input
                  );
                  setCalculation(result);
                  setCalculationInput(input);
                }}
                onDone={() => notify('Расчёт готов')}
              >
                <label className="field">
                  Вид начислений
                  <select
                    name="sanction"
                    aria-label="Вид начислений"
                    value={sanction}
                    onChange={(e) => setSanction(e.target.value)}
                  >
                    <option value="none">Только основной долг</option>
                    <option value="art395">Проценты по ст. 395 ГК РФ</option>
                    <option value="penalty">Договорная неустойка</option>
                    <option value="both">Неустойка и проценты при отдельном основании</option>
                  </select>
                </label>
                <Field
                  label="Рассчитать по"
                  name="through_on"
                  initial={today()}
                  type="date"
                  max={today()}
                  required
                />
                {(sanction === 'penalty' || sanction === 'both') && (
                  <>
                    <Field label="Дневная неустойка, %" name="penalty_daily_percent" required />
                    <Field label="Предел неустойки, ₽" name="penalty_cap_amount" />
                    <Field
                      label="Условие договора о неустойке"
                      name="penalty_basis"
                      area
                      required
                    />
                    <Check
                      name="penalty_agreed"
                      label="Проверено согласованное условие договора о неустойке"
                      required
                    />
                    {sanction === 'both' && (
                      <Field
                        label="Основание одновременного взыскания неустойки и процентов"
                        name="combination_basis"
                        area
                        required
                      />
                    )}
                  </>
                )}
                <details className="legal-advanced full-width">
                  <summary>Особые периоды и подтверждённые начальные оплаты</summary>
                  <p className="ops-muted">
                    Укажите исключения из начисления, подтверждённые даты оплат начального остатка
                    или проверенные периоды иной ставки. Замена ставок должна покрывать весь расчёт
                    без пересечений.
                  </p>
                  <RepeatableRows
                    name="excluded_periods"
                    title="Исключённые периоды"
                    addLabel="Добавить исключённый период"
                    fields={[
                      { key: 'from_on', label: 'Исключить с', type: 'date' },
                      { key: 'to_on', label: 'Исключить по', type: 'date' },
                      { key: 'basis', label: 'Правовое основание исключения' },
                    ]}
                  />
                  {(selected.invoices || [selected.invoice]).map((inv) => (
                    <RepeatableRows
                      key={inv.id}
                      name={
                        (selected.invoices?.length || 0) > 1
                          ? `opening_reductions:${inv.id}`
                          : 'opening_reductions'
                      }
                      title={`Оплаты начального остатка: ${inv.number}`}
                      addLabel="Добавить начальную оплату"
                      fields={[
                        { key: 'effective_on', label: 'Дата начальной оплаты', type: 'date' },
                        { key: 'amount', label: 'Начальная оплата, ₽' },
                        { key: 'evidence', label: 'Подтверждение начальной оплаты' },
                      ]}
                    />
                  ))}
                  <RepeatableRows
                    name="rate_override"
                    title="Проверенные периоды иной ставки"
                    addLabel="Добавить период ставки"
                    fields={[
                      { key: 'from_on', label: 'Ставка действует с', type: 'date' },
                      { key: 'to_on', label: 'Ставка действует по', type: 'date' },
                      { key: 'annual_percent', label: 'Годовая ставка, %' },
                      { key: 'source', label: 'Источник ставки' },
                    ]}
                  />
                  <Field label="Обоснование замены ставок" name="override_reason" area />
                </details>
              </OperationForm>
              {(calculation ?? selected.calculation) && (
                <CalculationView result={(calculation ?? selected.calculation)!} />
              )}
            </section>
          )}
          {tab === 'Доказательства' && (
            <section className="ops-card">
              <div className="ops-card-heading">
                <div>
                  <h2>Доказательства по делу</h2>
                  <p>
                    Укажите подтверждающие документы и место их хранения. При отправке претензии или
                    подаче иска приложите оригиналы или копии самостоятельно.
                  </p>
                </div>
              </div>
              {(selected.invoices?.length || 0) > 1 && (
                <label className="field full-width">
                  Документы какого счёта добавить
                  <select
                    aria-label="Счёт для выбора доказательств"
                    value={archiveSource}
                    onChange={(event) => setArchiveInvoiceId(event.target.value)}
                  >
                    {selected.invoices!.map((inv) => (
                      <option key={inv.id} value={inv.id}>
                        {inv.number}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <ArchiveEvidence
                key={archiveSource}
                invoiceId={archiveSource}
                caseId={selected.id}
                existing={proofs}
                onAdded={() => refreshCase(selected.id)}
              />
              <OperationForm
                draftKey={`legal-evidence:${selected.id}`}
                key={`${selected.id}-${proofs.length}`}
                label="Зарегистрировать доказательство"
                submit={async (data) => {
                  await post(`/legal/cases/${selected.id}/evidence`, {
                    kind: value(data, 'kind'),
                    title: value(data, 'title'),
                    reference: value(data, 'reference'),
                    occurred_on: value(data, 'occurred_on'),
                    sha256: '',
                    invoice_ids: data.getAll('evidence_invoice_ids').map(String),
                    covers_all_invoices: data.has('covers_all_invoices'),
                  });
                  await refreshCase(selected.id);
                }}
                onDone={() => notify('Доказательство зарегистрировано')}
              >
                <label className="field">
                  Вид доказательства
                  <select name="kind" aria-label="Вид доказательства">
                    {Object.entries(evidenceKinds).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <Field label="Название доказательства" name="title" required />
                {(selected.invoices?.length || 0) > 1 && (
                  <fieldset className="full-width">
                    <legend>Какие счета подтверждает документ</legend>
                    {selected.invoices!.map((inv) => (
                      <label className="checkbox-row" key={inv.id}>
                        <input type="checkbox" name="evidence_invoice_ids" value={inv.id} />
                        {inv.number}
                      </label>
                    ))}
                    <label className="checkbox-row">
                      <input type="checkbox" name="covers_all_invoices" />
                      Документ подтверждает все счета этого дела
                    </label>
                  </fieldset>
                )}
                <Field label="Номер, ссылка или место хранения" name="reference" area required />
                <Field
                  label="Дата документа"
                  name="occurred_on"
                  type="date"
                  initial={today()}
                  max={today()}
                  required
                />
              </OperationForm>
              <div className="legal-evidence-list">
                {proofs.map((proof) => (
                  <div key={proof.id} className="ops-evidence">
                    <span>
                      {evidenceKinds[proof.kind]} · {dateText(proof.occurred_on)}
                    </span>
                    <strong>{proof.title}</strong>
                    <div>{proof.reference}</div>
                    {(selected.invoices?.length || 0) > 1 && (
                      <span>
                        Счета:{' '}
                        {(selected.invoices || [])
                          .filter((inv) => proof.invoice_ids?.includes(inv.id))
                          .map((inv) => inv.number)
                          .join(', ') || 'не указаны'}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
          {tab === 'Документы' && (
            <section className="ops-card">
              <div className="ops-card-heading">
                <div>
                  <h2>Версии документов</h2>
                  <p>
                    Подготовьте документ и проверьте его перед отправкой. Если долг или сведения по
                    делу изменились, нужна новая версия.
                  </p>
                </div>
              </div>
              {calculationInput ? (
                <OperationForm
                  label="Подготовить DOCX"
                  submit={async (data) => {
                    await post(`/legal/cases/${selected.id}/documents`, {
                      kind: value(data, 'kind'),
                      calculation: calculationInput,
                    });
                    await refreshCase(selected.id);
                  }}
                  onDone={() => notify('DOCX подготовлен и ожидает проверки')}
                >
                  <label className="field full-width">
                    Вид документа
                    <select name="kind" aria-label="Вид документа">
                      {Object.entries(kinds).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                </OperationForm>
              ) : (
                <div className="ops-context">
                  <span>Для новой версии рассчитайте требования на выбранную дату.</span>
                  <button
                    className="button button-ghost button-small"
                    onClick={() => setTab('Расчёт')}
                  >
                    Перейти к расчёту
                  </button>
                </div>
              )}
              <div className="legal-document-list">
                {!documents.length && (
                  <EmptyCard title="Документы появятся после подготовки">
                    Заполните сведения сторон, договор, факт исполнения и зарегистрированные
                    доказательства.
                  </EmptyCard>
                )}
                {documents.map((doc) => (
                  <article className="ops-document" key={doc.id}>
                    <div>
                      <h3>{kinds[doc.kind]}</h3>
                      <small>
                        Версия {doc.version} · {dateText(doc.created_at)}
                      </small>
                      <p>
                        <span className={`ops-badge legal-status-${doc.status}`}>
                          {statuses[doc.status] ?? doc.status}
                        </span>
                      </p>
                      <details className="legal-version-details">
                        <summary>История проверки</summary>
                        <p>
                          Требование: {money(doc.calculation.total_claim_amount)} по{' '}
                          {dateText(doc.calculation.through_on)}
                        </p>
                        {doc.reviews.map((review, index) => (
                          <p key={index}>
                            {review.reviewer_name} · {review.authority_reference}
                            <br />
                            {review.notes}
                          </p>
                        ))}
                      </details>
                    </div>
                    <div className="ops-action-row">
                      <a
                        className="button button-ghost button-small"
                        href={doc.download_url}
                        download
                      >
                        <Download size={14} />
                        Скачать DOCX
                      </a>
                      {!doc.stale && (
                        <button
                          className="button button-dark button-small"
                          onClick={() => {
                            setDecision('');
                            setReviewing(doc);
                          }}
                        >
                          <CheckCircle2 size={14} />
                          Проверить версию
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
          {tab === 'Ход дела' && (
            <section className="ops-card">
              <div className="ops-card-heading">
                <div>
                  <h2>Ход взыскания</h2>
                  <p>
                    Отмечайте отправку претензии, подачу иска и другие выполненные действия.
                    Документы в суд, банк и ФССП подаются отдельно.
                  </p>
                </div>
              </div>
              {selected.pretrial.sent_on && (
                <div className="ops-context">
                  <span>
                    Претензия: {dateText(selected.pretrial.sent_on)} · срок {selected.pretrial.days}{' '}
                    дней
                  </span>
                  <strong>
                    {selected.pretrial.ready
                      ? 'Срок ожидания истёк'
                      : `Ожидание до ${selected.pretrial.ready_on ? dateText(selected.pretrial.ready_on) : 'уточнения даты'}`}
                  </strong>
                </div>
              )}
              <OperationForm
                key={`${selected.id}-${selected.milestones?.length}`}
                label="Записать ручное действие"
                submit={async (data) => {
                  await post(`/legal/cases/${selected.id}/milestones`, {
                    stage: value(data, 'stage'),
                    occurred_on: value(data, 'occurred_on'),
                    reference: value(data, 'reference'),
                    notes: value(data, 'notes'),
                    document_id: value(data, 'document_id') || null,
                    evidence_ids: data.getAll('evidence_ids').map(String),
                  });
                  await refreshCase(selected.id);
                }}
                onDone={() => {
                  notify('Ручное действие записано');
                  done();
                }}
              >
                <label className="field">
                  Ручное действие
                  <select name="stage" aria-label="Ручное действие">
                    {Object.entries(stages)
                      .filter(([key]) => key !== 'intake')
                      .map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                  </select>
                </label>
                <Field
                  label="Дата действия"
                  name="occurred_on"
                  type="date"
                  max={today()}
                  initial={today()}
                  required
                />
                <Field
                  label="Номер дела, отправления или квитанции"
                  name="reference"
                  required
                  area
                />
                <Field label="Описание ручного действия" name="notes" required area />
                <label className="field full-width">
                  Версия документа
                  <select name="document_id" aria-label="Версия документа">
                    <option value="">Внешний документ / без версии</option>
                    {documents
                      .filter((d) => d.status === 'approved' && !d.stale)
                      .map((doc) => (
                        <option key={doc.id} value={doc.id}>
                          {kinds[doc.kind]} · версия {doc.version}
                        </option>
                      ))}
                  </select>
                </label>
                <fieldset className="legal-fieldset full-width">
                  <legend>Подтверждающие доказательства</legend>
                  {proofs.length ? (
                    proofs.map((proof) => (
                      <label className="consent" key={proof.id}>
                        <input type="checkbox" name="evidence_ids" value={proof.id} />
                        {proof.title}
                      </label>
                    ))
                  ) : (
                    <p className="ops-muted">
                      Сначала зарегистрируйте доказательства на соответствующей вкладке.
                    </p>
                  )}
                </fieldset>
              </OperationForm>
              <div className="legal-milestones">
                {selected.milestones?.map((item) => (
                  <div className="ops-evidence" key={item.id}>
                    <span>{dateText(item.occurred_on)} · Записано вручную</span>
                    <strong>{stages[item.stage]}</strong>
                    <div>{item.reference}</div>
                    <div>{item.notes}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
          {tab === 'Гонорар' && <FeeView fee={selected.fee} />}
        </>
      )}
      {opening && (
        <Dialog title="Новое юридическое дело" onClose={() => setOpening(false)}>
          <p className="ops-muted">
            Выберите счёт. Другие счета того же договора можно включить в общее требование.
          </p>
          <OperationForm
            label="Открыть дело"
            submit={async (data) => {
              const invoice = invoices.find((item) => item.id === value(data, 'invoice_id'));
              if (!invoice) throw new Error('Выберите счёт.');
              const item = await post<LegalCase>('/legal/cases', {
                invoice_id: invoice.id,
                invoice_ids: data.getAll('invoice_ids').map(String),
                facts: {
                  creditor: {
                    name: settings?.company ?? '',
                    email: settings?.reply_to ?? '',
                    bank_details: settings?.bank_details ?? '',
                  },
                  debtor: { name: invoice.company, inn: invoice.inn, email: invoice.email },
                },
              });
              await openCase(item);
            }}
            onDone={() => {
              setOpening(false);
              done();
            }}
          >
            <InvoiceSelect
              invoices={invoices.filter(
                (inv) => !cases.some((c) => (c.invoice_ids || [c.invoice_id]).includes(inv.id))
              )}
              value={newInvoiceId}
              onChange={setNewInvoiceId}
            />
            {contractGroups
              .filter((group) => group.contract_known && group.invoice_ids.includes(newInvoiceId))
              .map((group) => (
                <fieldset className="full-width" key={group.contract_number}>
                  <legend>Добавить счета договора {group.contract_number}</legend>
                  {invoices
                    .filter(
                      (inv) =>
                        inv.id !== newInvoiceId &&
                        group.invoice_ids.includes(inv.id) &&
                        !cases.some((c) => (c.invoice_ids || [c.invoice_id]).includes(inv.id))
                    )
                    .map((inv) => (
                      <label className="checkbox-row" key={inv.id}>
                        <input type="checkbox" name="invoice_ids" value={inv.id} />
                        {inv.number} · {money(inv.balance)}
                      </label>
                    ))}
                </fieldset>
              ))}
          </OperationForm>
        </Dialog>
      )}
      {reviewing && selected && (
        <Dialog title="Проверка документа" onClose={() => setReviewing(null)}>
          <p className="ops-muted">
            {kinds[reviewing.kind]} · версия {reviewing.version}. Подтвердите проверку фактов,
            расчёта, доказательств, подсудности и полномочий.
          </p>
          <OperationForm
            label="Зафиксировать проверку"
            submit={async (data) => {
              await post(`/legal/documents/${reviewing.id}/review`, {
                decision: value(data, 'decision'),
                reviewer_name: value(data, 'reviewer_name'),
                authority_reference: value(data, 'authority_reference'),
                qualification_confirmed: data.has('qualification_confirmed'),
                notes: value(data, 'notes'),
              });
              await refreshCase(selected.id);
            }}
            onDone={() => {
              setReviewing(null);
              notify('Результат проверки сохранён');
            }}
          >
            <label className="field full-width">
              Решение проверяющего
              <select
                name="decision"
                aria-label="Решение проверяющего"
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
                required
              >
                <option value="" disabled>
                  Выберите решение
                </option>
                <option value="approved">Согласовать</option>
                <option value="changes_requested">Вернуть на исправление</option>
              </select>
            </label>
            <Field
              label="Проверяющий"
              name="reviewer_name"
              initial={selected.facts.responsible_lawyer}
              required
            />
            <Field
              label="Полномочия проверяющего"
              name="authority_reference"
              initial={selected.facts.lawyer_authority}
              required
            />
            <Field label="Комментарий проверяющего" name="notes" area required />
            <Check
              name="qualification_confirmed"
              label="Подтверждаю полномочия и квалификацию для проверки"
              required={decision === 'approved'}
            />
          </OperationForm>
        </Dialog>
      )}
    </div>
  );
}

function CalculationView({ result }: { result: Calculation }) {
  return (
    <div className="legal-calculation-result">
      <h3>Требования по {dateText(result.through_on)}</h3>
      <div className="ops-result-grid">
        {[
          ['Основной долг', result.principal_amount],
          ['Проценты по ст. 395', result.interest_amount],
          ['Договорная неустойка', result.penalty_amount],
          ['Итого к взысканию', result.total_claim_amount],
          ['Госпошлина: иск', result.fee_claim_amount],
          ['Госпошлина: приказ', result.fee_order_amount],
        ].map(([label, amount]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{money(Number(amount))}</strong>
          </div>
        ))}
      </div>
      <p className="ops-muted">
        {result.order_eligible
          ? 'Сумма укладывается в предел приказного производства. Бесспорность и остальные условия проверяются отдельно.'
          : 'Сумма превышает предел приказного производства.'}
      </p>
      <div className="legal-table-scroll">
        <table className="ops-table">
          <thead>
            <tr>
              <th scope="col">Период</th>
              <th scope="col">Дней</th>
              <th scope="col">База</th>
              <th scope="col">Ставка / год</th>
              <th scope="col">Проценты</th>
              <th scope="col">Неустойка</th>
            </tr>
          </thead>
          <tbody>
            {result.line_items.map((row, i) => (
              <tr key={i}>
                <td>
                  {dateText(row.from_on)} — {dateText(row.to_on)}
                  {row.excluded && <small>Исключён: {row.basis}</small>}
                </td>
                <td>{row.days}</td>
                <td>{money(row.principal_amount)}</td>
                <td>
                  {row.annual_percent}% / {row.denominator}
                </td>
                <td>{money(row.interest_amount)}</td>
                <td>{money(row.penalty_amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="ops-muted legal-rate-source">
        История ключевой ставки.{' '}
        {result.rates_source && (
          <a href={result.rates_source} target="_blank" rel="noreferrer">
            Источник Банка России
          </a>
        )}{' '}
        День поступления включается в начисление; остаток требования учитывает поступления на конец
        выбранного дня.
      </p>
    </div>
  );
}
function FeeView({ fee }: { fee?: Fee }) {
  if (!fee)
    return (
      <EmptyCard title="Расчёт гонорара пока недоступен">
        Обновите дело после настройки договора сопровождения.
      </EmptyCard>
    );
  return (
    <section className="ops-card legal-fee">
      <div className="ops-card-heading">
        <div>
          <h2>Вознаграждение Mandato и адвоката</h2>
          <p>
            Проценты — только с подтверждённых банковских поступлений за вычетом отмен и возвратов.
            Фикс за поданный судебный пакет не зависит от взыскания.
          </p>
        </div>
      </div>
      {fee.requires_fee_model_confirmation ? (
        <div className="ops-context">
          В деле сохранены прежние условия. Руководителю нужно подтвердить новую модель на вкладке
          «Факты». До подтверждения новые суммы не рассчитываются.
        </div>
      ) : (
        !fee.configured && (
          <div className="ops-context">
            Укажите договор сопровождения и дату его начала на вкладке «Факты». Без них гонорар не
            начисляется.
          </div>
        )
      )}
      <div className="ops-result-grid">
        <div>
          <span>Подтверждённые поступления</span>
          <strong>{money(fee.confirmed_recovery_amount)}</strong>
        </div>
        <div>
          <span>Итого Mandato</span>
          <strong>{money(fee.fee_amount)}</strong>
        </div>
        <div>
          <span>Mandato: {tariff.pretrial_percent}% до суда</span>
          <strong>{money(fee.pretrial_fee_amount)}</strong>
        </div>
        <div>
          <span>Mandato: судебные пакеты</span>
          <strong>{money(fee.judicial_package_amount)}</strong>
        </div>
        <div>
          <span>Адвокату отдельно: {tariff.lawyer_percent}% после подачи</span>
          <strong>{money(fee.lawyer_fee_amount)}</strong>
        </div>
        <div>
          <span>Ручные оплаты вне базы</span>
          <strong>{money(fee.excluded_manual_amount)}</strong>
        </div>
        <div>
          <span>Поступления до претензии</span>
          <strong>{money(fee.excluded_before_claim_amount)}</strong>
        </div>
        <div>
          <span>Порядок событий требует проверки</span>
          <strong>{money(fee.ambiguous_recovery_amount)}</strong>
        </div>
        <div>
          <span>Поступления до сопровождения</span>
          <strong>{money(fee.excluded_before_start_amount)}</strong>
        </div>
      </div>
      <p className="ops-muted">
        {fee.agreement_reference || 'Договор Mandato не указан'}. {tariff.pretrial_percent}%
        применяются после подтверждённого направления претензии и до подачи в суд. Поступления в
        день претензии или подачи показаны для проверки; процент автоматически не начисляется.
      </p>
      <p className="ops-muted">
        {fee.lawyer_agreement_reference || 'Отдельное соглашение с адвокатом не указано'}.
        Вознаграждение адвоката оплачивается отдельно и не входит в итог Mandato.
        {!fee.lawyer_configured && ' Без отдельного соглашения 12% не рассчитываются.'}
        {fee.lawyer_unconfigured_recovery_amount > 0 &&
          ` Поступления после подачи без соглашения: ${money(fee.lawyer_unconfigured_recovery_amount)}.`}
      </p>
      <h3>Судебные пакеты</h3>
      <p className="ops-muted">
        Приказ — {money(tariff.court_order_amount)}, иск — {money(tariff.statement_of_claim_amount)}{' '}
        за подготовленный и поданный пакет. Госпошлина оплачивается клиентом отдельно. Заявление в
        банк по исполнительному листу — бесплатно. Повторная отметка подачи или новая версия того же
        вида пакета не увеличивает фикс.
      </p>
      {fee.package_items.length ? (
        <div className="legal-table-scroll">
          <table className="ops-table" aria-label="Стоимость поданных судебных пакетов">
            <thead>
              <tr>
                <th scope="col">Пакет</th>
                <th scope="col">Подан</th>
                <th scope="col">Основание</th>
                <th scope="col">Mandato</th>
              </tr>
            </thead>
            <tbody>
              {fee.package_items.map((row) => (
                <tr key={row.kind}>
                  <td>{kinds[row.kind]}</td>
                  <td>{dateText(row.filed_on)}</td>
                  <td>{row.reference}</td>
                  <td>
                    {money(row.fee_amount)}
                    {!row.billable && <small>Вне подтверждённых условий сопровождения</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="ops-muted">Поданные судебные пакеты пока не зарегистрированы.</p>
      )}
      <h3>Проценты по поступлениям</h3>
      {!!fee.line_items.length && (
        <div className="legal-table-scroll">
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Поступление</th>
                <th scope="col">База</th>
                <th scope="col">Условия</th>
                <th scope="col">Получатель</th>
                <th scope="col">Ставка</th>
                <th scope="col">Гонорар</th>
              </tr>
            </thead>
            <tbody>
              {fee.line_items.map((row) => (
                <tr key={row.payment_id}>
                  <td>{dateText(row.paid_on)}</td>
                  <td>{money(row.amount)}</td>
                  <td>
                    {{
                      pretrial: 'После претензии, до суда',
                      judicial: 'После подачи в суд',
                      before_start: 'До сопровождения',
                      before_claim: 'До претензии',
                      ambiguous: 'Нужна проверка порядка событий',
                      unconfigured: 'Условия не подтверждены',
                    }[row.stage] || row.stage}
                  </td>
                  <td>
                    {row.recipient === 'mandato'
                      ? 'Mandato'
                      : row.recipient === 'lawyer'
                        ? 'Адвокат отдельно'
                        : 'Не начислено'}
                  </td>
                  <td>{row.rate_percent === null ? '—' : `${row.rate_percent}%`}</td>
                  <td>{money(row.fee_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(fee.rounding_difference !== 0 || fee.lawyer_rounding_difference !== 0) && (
        <p className="ops-muted">
          Округление итогов отдельно по получателям: Mandato — {money(fee.rounding_difference)},
          адвокат — {money(fee.lawyer_rounding_difference)} относительно суммы строк.
        </p>
      )}
      <p className="ops-muted">
        Это расчёт по реестру. Он не списывает деньги и требует проверки договоров и оснований
        оплаты.
      </p>
    </section>
  );
}

function LegalReadiness({ item }: { item: LegalCase }) {
  const f = item.facts;
  const partyReady = (p: Party) =>
    Boolean(
      p.name &&
        p.inn &&
        p.ogrn &&
        p.address &&
        (p.kind !== 'sole_proprietor' || (p.birth_on && p.birth_place) || p.birth_details_unknown)
    );
  const checks: [string, boolean][] = [
    [
      'Реквизиты сторон и банк кредитора',
      partyReady(f.creditor) && partyReady(f.debtor) && Boolean(f.creditor.bank_details),
    ],
    [
      'Договор, исполнение и основания требования',
      Boolean(
        f.contract_number &&
          f.contract_date &&
          f.obligation_description &&
          f.performance_description &&
          f.due_basis &&
          f.legal_basis
      ),
    ],
    [
      'Проверка характера долга и специальных режимов',
      f.business_debt_confirmed && f.special_regimes_checked,
    ],
    [
      'Договор и первичка в доказательствах',
      ['contract', 'performance'].every((kind) =>
        (item.invoice_ids || [item.invoice_id]).every((id) =>
          item.evidence?.some(
            (e) => e.kind === kind && (e.invoice_ids || [item.invoice_id]).includes(id)
          )
        )
      ),
    ],
    [
      'Суд и основание подсудности (для судебного пакета)',
      Boolean(f.court_name && f.court_address && f.jurisdiction_basis),
    ],
  ];
  return (
    <details className="legal-readiness">
      <summary>
        Готовность сохранённых данных: {checks.filter(([, ready]) => ready).length} из{' '}
        {checks.length} разделов
      </summary>
      <ul>
        {checks.map(([label, ready]) => (
          <li key={label}>
            {ready ? '✓ Заполнено' : '○ Требуется заполнить'} — {label}
          </li>
        ))}
      </ul>
      <p>
        Перед выпуском пакета дополнительно проверяются актуальный расчёт, претензионный порядок и
        применимость процедуры. Документ проверяет специалист. Черновик браузера здесь не
        учитывается.
      </p>
    </details>
  );
}
