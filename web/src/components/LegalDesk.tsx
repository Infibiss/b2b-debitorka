import { useEffect, useState } from 'react';
import { ArrowLeft, FileText, Plus, Scale, Download, CheckCircle2 } from 'lucide-react';
import { api, post, patch, money, dateText, today, type Invoice, type Settings } from '../api';
import { Dialog } from './Dialog';
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
  pretrial_fee_percent: string;
  judicial_fee_percent: string;
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
  agreement_reference: string;
  confirmed_recovery_amount: number;
  fee_amount: number;
  excluded_manual_amount: number;
  excluded_before_start_amount: number;
  rounding_difference: string;
  line_items: {
    payment_id: string;
    paid_on: string;
    stage: string;
    amount: number;
    rate_percent: string;
    fee_amount: number;
    date_ordering_ambiguous: boolean;
  }[];
};
type LegalCase = {
  id: string;
  invoice_id: string;
  facts: Facts;
  facts_revision: number;
  invoice: Invoice;
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
    <fieldset className="legal-fieldset full-width">
      <legend>{prefix === 'creditor' ? 'Кредитор' : 'Должник'}</legend>
      <div className="legal-field-grid">
        <label className="field">
          Тип {role}
          <select
            name={`${prefix}.kind`}
            defaultValue={kind}
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
      name === 'opening_reductions' && field === 'amount'
        ? rubles(text)
        : field === 'annual_percent'
          ? text.replace(',', '.')
          : text;
    groups.set(id, row);
  }
  return [...groups.values()];
}

export default function LegalDesk({ invoices, onChanged, notify }: DeskProps) {
  const [cases, setCases] = useState<LegalCase[]>([]),
    [selected, setSelected] = useState<LegalCase | null>(null),
    [settings, setSettings] = useState<Settings | null>(null),
    [tab, setTab] = useState('Факты'),
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
    Promise.all([api<{ items: LegalCase[] }>('/legal/cases'), api<Settings>('/settings')])
      .then(([list, prefs]) => {
        if (alive) {
          setCases(list.items);
          setSettings(prefs);
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
  async function openCase(item: LegalCase) {
    setError('');
    setCalculation(null);
    setCalculationInput(null);
    setSanction('none');
    setTab('Факты');
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
  return (
    <div className="legal-desk">
      <DeskHeading
        eyebrow="ЮРИДИЧЕСКОЕ СОПРОВОЖДЕНИЕ"
        title="Претензии и суд"
        action={
          <button className="button button-dark" onClick={() => setOpening(true)}>
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
                Откройте дело по счёту. Оплаты и корректировки будут учтены в расчёте требований.
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
                    {item.invoice.company} · {item.invoice.number}
                  </strong>
                  <span>{stages[item.stage] ?? item.stage}</span>
                </div>
                <strong>{money(item.invoice.balance)}</strong>
              </button>
            ))
          )}
        </section>
      ) : (
        <>
          <div className="ops-detail-bar">
            <button className="button button-ghost button-small" onClick={() => setSelected(null)}>
              <ArrowLeft size={14} />
              Все дела
            </button>
            <span className="ops-badge">{stages[selected.stage] ?? selected.stage}</span>
          </div>
          <div className="ops-context">
            <strong>
              {selected.invoice.company} · {selected.invoice.number}
            </strong>
            <span>Остаток по реестру: {money(selected.invoice.balance)}</span>
          </div>
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
                  <h2>Юридически значимые факты</h2>
                  <p>
                    Укажите стороны, условия договора и основания требования. Сведения нужны для
                    подготовки документов.
                  </p>
                </div>
              </div>
              <OperationForm
                key={`${selected.id}-${selected.facts_revision}`}
                label="Сохранить факты"
                submit={async (data) => {
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
                    pretrial_fee_percent: value(data, 'pretrial_fee_percent'),
                    judicial_fee_percent: value(data, 'judicial_fee_percent'),
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
                <PartyFields prefix="creditor" party={selected.facts.creditor} role="кредитора" />
                <PartyFields prefix="debtor" party={selected.facts.debtor} role="должника" />
                <h3 className="full-width">Обязательство и основание требования</h3>
                <Field
                  label="Номер договора"
                  name="contract_number"
                  initial={selected.facts.contract_number}
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
                <h3 className="full-width">Претензионный порядок и суд</h3>
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
                <h3 className="full-width">Условия вознаграждения</h3>
                <p className="ops-muted full-width">
                  Заполните ставки из договора сопровождения и дату начала работы.
                </p>
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
                />
                <Field
                  label="Досудебный гонорар, %"
                  name="pretrial_fee_percent"
                  initial={selected.facts.pretrial_fee_percent}
                  required
                />
                <Field
                  label="Судебный гонорар, %"
                  name="judicial_fee_percent"
                  initial={selected.facts.judicial_fee_percent}
                  required
                />
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
                  if (value(data, 'penalty_daily_percent'))
                    input.penalty_daily_percent = value(data, 'penalty_daily_percent');
                  if (value(data, 'penalty_cap_amount'))
                    input.penalty_cap_amount = rubles(value(data, 'penalty_cap_amount'));
                  if (rates.length) input.rate_override = rates;
                  const result = await post<Calculation>('/legal/calculations', {
                    invoice_id: selected.invoice_id,
                    ...input,
                  });
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
                  <RepeatableRows
                    name="opening_reductions"
                    title="Оплаты начального остатка"
                    addLabel="Добавить начальную оплату"
                    fields={[
                      { key: 'effective_on', label: 'Дата начальной оплаты', type: 'date' },
                      { key: 'amount', label: 'Начальная оплата, ₽' },
                      { key: 'evidence', label: 'Подтверждение начальной оплаты' },
                    ]}
                  />
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
              <OperationForm
                key={`${selected.id}-${proofs.length}`}
                label="Зарегистрировать доказательство"
                submit={async (data) => {
                  await post(`/legal/cases/${selected.id}/evidence`, {
                    kind: value(data, 'kind'),
                    title: value(data, 'title'),
                    reference: value(data, 'reference'),
                    occurred_on: value(data, 'occurred_on'),
                    sha256: '',
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
          <p className="ops-muted">Выберите счёт, по которому готовите претензию или иск.</p>
          <OperationForm
            label="Открыть дело"
            submit={async (data) => {
              const invoice = invoices.find((item) => item.id === value(data, 'invoice_id'));
              if (!invoice) throw new Error('Выберите счёт.');
              const item = await post<LegalCase>('/legal/cases', {
                invoice_id: invoice.id,
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
            <InvoiceSelect invoices={invoices} />
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
            <Field label="Проверяющий" name="reviewer_name" required />
            <Field label="Полномочия проверяющего" name="authority_reference" required />
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
          <h2>Вознаграждение по результату</h2>
          <p>
            База — подтверждённые банковские поступления, распределённые на этот счёт, за вычетом
            отмен и возвратов.
          </p>
        </div>
      </div>
      {!fee.configured && (
        <div className="ops-context">
          Укажите договор сопровождения и дату его начала на вкладке «Факты». Без них гонорар не
          начисляется.
        </div>
      )}
      <div className="ops-result-grid">
        <div>
          <span>Подтверждённые поступления</span>
          <strong>{money(fee.confirmed_recovery_amount)}</strong>
        </div>
        <div>
          <span>Расчётный гонорар</span>
          <strong>{money(fee.fee_amount)}</strong>
        </div>
        <div>
          <span>Ручные оплаты вне базы</span>
          <strong>{money(fee.excluded_manual_amount)}</strong>
        </div>
        <div>
          <span>Поступления до сопровождения</span>
          <strong>{money(fee.excluded_before_start_amount)}</strong>
        </div>
      </div>
      <p className="ops-muted">
        {fee.agreement_reference || 'Договор не указан'}. Ставки и право на вознаграждение требуют
        проверки договора. Поступление в день подачи считается досудебным без доказанного порядка
        событий внутри дня.
      </p>
      {!!fee.line_items.length && (
        <div className="legal-table-scroll">
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Поступление</th>
                <th scope="col">База</th>
                <th scope="col">Стадия</th>
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
                    {row.stage === 'judicial' ? 'Судебная' : 'Досудебная'}
                    {row.date_ordering_ambiguous && (
                      <small>Порядок событий в течение дня не подтверждён</small>
                    )}
                  </td>
                  <td>{row.rate_percent}%</td>
                  <td>{money(row.fee_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
