import { navigate, useRouteField, useWorkContext } from '../navigation';
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, Check, CircleHelp, Inbox, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { api, post, dateText, money } from '../api';
import { Dialog } from './Dialog';
import {
  DeskHeading,
  DeskError,
  EmptyCard,
  OperationForm,
  InvoiceSelect,
  value,
  type DeskProps,
} from './OperationsUI';

type Proposal = {
  id: string;
  invoice_id: string;
  source_text: string;
  received_at: string;
  created_at: string;
  expires_at: string;
  status:
    | 'processing'
    | 'review_required'
    | 'handoff'
    | 'executed'
    | 'rejected'
    | 'stale'
    | 'superseded';
  intent: 'promise' | 'dispute' | 'payment_claim' | 'unknown';
  action: string;
  reasons: string[];
  extraction: {
    amount_kopeks?: number | null;
    due_date?: string | null;
    evidence?: { field: string; quote: string }[];
  };
  outcome?: { message?: string; action?: string; status?: string } | null;
};
const statusText: Record<Proposal['status'], string> = {
  processing: 'Обрабатывается',
  review_required: 'Ждёт решения',
  handoff: 'Нужна проверка',
  executed: 'Подтверждено',
  rejected: 'Отклонено',
  stale: 'Данные изменились',
  superseded: 'Есть новая редакция',
};
const intentText = {
  promise: 'Договорённость об оплате',
  dispute: 'Возражение покупателя',
  payment_claim: 'Сообщение об оплате',
  unknown: 'Обращение покупателя',
};
const reasons: Record<string, string> = {
  provider_tenant_denied:
    'Обработка сообщений для вашей организации ещё не подключена. Обратитесь к администратору.',
  provider_unconfigured: 'Обработка сообщений ещё не подключена. Обратитесь к администратору.',
  provider_unavailable: 'Не удалось обработать сообщение. Повторите проверку позже.',
  invalid_schema: 'Не удалось надёжно определить содержание сообщения.',
  evidence_mismatch: 'Для одного из выводов не найдено подтверждение в тексте.',
  intent_unverified: 'Намерение покупателя требует проверки.',
  untrusted_instruction: 'В сообщении есть посторонние инструкции. Проверьте его вручную.',
  quoted_history: 'В сообщении есть история переписки. Оставьте только новый ответ покупателя.',
  ambiguous: 'В сообщении несколько возможных трактовок.',
  ambiguous_facts: 'Указано несколько сумм или дат. Уточните договорённость с покупателем.',
  unknown_intent: 'Нужен ответ сотрудника.',
  amount_mismatch: 'Сумма не подтверждается текстом.',
  amount_required: 'В сообщении нет точной суммы обещанного платежа.',
  currency_unsupported: 'Нужно проверить валюту платежа.',
  date_required: 'В сообщении нет точной даты оплаты.',
  date_mismatch: 'Дата не подтверждается текстом.',
  date_unverified: 'Дата оплаты требует уточнения.',
  negated_promise: 'Покупатель не подтвердил обещание оплаты.',
  negated_claim: 'Покупатель не подтвердил факт оплаты.',
  mandate_required: 'Для покупателя не разрешено согласование договорённостей агентом.',
  mandate_expired: 'Срок полномочий по этому покупателю истёк.',
  counterparty_hold: 'Работа с покупателем приостановлена.',
  contact_not_allowed: 'Контакт с покупателем запрещён.',
  invoice_disputed: 'По счёту есть спор.',
  invoice_paused: 'Работа по счёту приостановлена.',
  invoice_paid: 'Счёт уже оплачен.',
  amount_exceeds_balance: 'Обещанная сумма больше текущего остатка.',
  promise_date_outside_mandate: 'Срок оплаты выходит за пределы разрешённой отсрочки.',
  approval_expired: 'Срок согласования истёк. Проверьте сообщение заново.',
  stale_snapshot: 'Остаток или правила работы изменились. Проверьте сообщение заново.',
  promise_mandate_required: 'Для покупателя не разрешено согласование договорённостей агентом.',
  contact_not_authorized: 'Контакт с покупателем запрещён.',
  invoice_not_actionable: 'Счёт оплачен, приостановлен или находится в споре.',
  invalid_promise_amount: 'Сумма обещания выходит за допустимый остаток.',
  date_outside_mandate: 'Срок оплаты выходит за пределы разрешённой отсрочки.',
  provider_busy: 'Сейчас обрабатываются другие сообщения. Повторите проверку немного позже.',
  provider_timeout: 'Обработка заняла слишком много времени. Повторите проверку.',
  provider_authentication: 'Нужно проверить подключение обработки сообщений.',
  provider_permission: 'У подключения недостаточно прав для обработки сообщений.',
  provider_rate_limit: 'Достигнут лимит обработки сообщений. Повторите проверку позже.',
  provider_network: 'Обработка сообщений временно недоступна.',
  provider_http_error: 'Обработка сообщений временно недоступна.',
  provider_invalid_response: 'Не удалось надёжно разобрать сообщение. Проверьте его вручную.',
};

export function AgentDesk({ invoices, onChanged, notify }: DeskProps) {
  const { invoiceId } = useWorkContext();
  const [proposalRoute] = useRouteField<string>('agentProposal', '');
  const [provider, setProvider] = useState<{ enabled: boolean; reason: string } | null>(null);
  useEffect(() => {
    void api<{ enabled: boolean; reason: string }>('/agent/status')
      .then(setProvider)
      .catch(() => setProvider({ enabled: false, reason: 'provider_unavailable' }));
  }, []);
  const [items, setItems] = useState<Proposal[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const [compose, setCompose] = useState(false),
    [selected, setSelected] = useState<Proposal | null>(null),
    [revision, setRevision] = useState(false);
  const reload = useCallback(async () => {
    try {
      const result = await api<{ proposals: Proposal[] }>('/agent/proposals');
      setItems(result.proposals);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  useEffect(() => {
    let alive = true;
    if (proposalRoute)
      void api<Proposal>(`/agent/proposals/${encodeURIComponent(proposalRoute)}`)
        .then((p) => {
          if (alive) setSelected(p);
        })
        .catch((e) => {
          if (alive) setError((e as Error).message);
        });
    return () => {
      alive = false;
    };
  }, [proposalRoute]);
  async function review(decision: 'approve' | 'reject') {
    if (!selected) return;
    setBusy(true);
    setError('');
    try {
      const result = await post<Proposal>(`/agent/proposals/${selected.id}/review`, { decision });
      setSelected(result);
      await reload();
      onChanged();
      notify(decision === 'approve' ? 'Решение подтверждено' : 'Предложение отклонено');
    } catch (e) {
      setError((e as Error).message);
      await reload();
      try {
        setSelected(await api<Proposal>(`/agent/proposals/${selected.id}`));
      } catch {
        /* retain current context */
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <DeskHeading
        eyebrow="ВХОДЯЩИЕ СООБЩЕНИЯ"
        title="Разбор ответов"
        action={
          <button className="button button-dark" onClick={() => setCompose(true)}>
            <Inbox size={16} />
            Разобрать сообщение
          </button>
        }
      >
        Добавьте ответ контрагента. Mandato определит, что он просит, и предложит следующий шаг.
      </DeskHeading>
      <div className="ops-context ops-agent-principle">
        <ShieldCheck size={22} />
        <div>
          <strong>Контрагент сообщил об оплате?</strong>
          <p>
            Проверьте поступление по выписке. Долг уменьшится только после подтверждения оплаты.
          </p>
        </div>
      </div>
      <div className="ops-context" role="status">
        <strong>
          {!provider
            ? 'Проверяем обработку сообщений…'
            : provider.enabled
              ? 'Обработка сообщений подключена'
              : 'Автоматическая обработка недоступна'}
        </strong>
        <p>
          {provider && !provider.enabled
            ? reasons[provider.reason]
            : 'Перед подтверждением проверьте извлечённые факты по исходному ответу.'}
        </p>
        <div className="wf-actions">
          <button
            className="button button-outline"
            onClick={() => navigate({ section: 'intelligence' })}
          >
            Зарегистрировать условия вручную
          </button>
          <button
            className="button button-outline"
            onClick={() => navigate({ section: 'finance', financeTab: 'ledger' })}
          >
            Сверить оплату по счёту
          </button>
          <button
            className="button button-outline"
            onClick={() => navigate({ section: 'messages' })}
          >
            Вся история общения
          </button>
        </div>
      </div>
      <DeskError>{error}</DeskError>
      <section className="ops-card">
        <div className="ops-card-heading">
          <div>
            <h2>Ответы и следующие действия</h2>
            <p>Откройте ответ, чтобы проверить условия и подтвердить действие.</p>
          </div>
          <button
            className="icon-button"
            aria-label="Обновить решения"
            onClick={() => void reload()}
          >
            <RefreshCw size={17} />
          </button>
        </div>
        {items.length ? (
          <div className="ops-proposal-list">
            {items
              .filter((p) => !invoiceId || p.invoice_id === invoiceId)
              .map((p) => {
                const invoice = invoices.find((i) => i.id === p.invoice_id);
                return (
                  <button
                    className="ops-proposal-row"
                    key={p.id}
                    onClick={() => {
                      navigate({ agentProposal: p.id });
                      setSelected(p);
                      setRevision(false);
                      setError('');
                    }}
                  >
                    <div className="ops-proposal-icon">
                      {p.status === 'executed' ? (
                        <Check size={20} />
                      ) : p.status === 'review_required' ? (
                        <Inbox size={20} />
                      ) : (
                        <CircleHelp size={20} />
                      )}
                    </div>
                    <div>
                      <strong>{intentText[p.intent]}</strong>
                      <span>
                        {invoice?.company} · {invoice?.number} · {dateText(p.created_at)}
                      </span>
                      <p>
                        {p.source_text.slice(0, 160)}
                        {p.source_text.length > 160 ? '…' : ''}
                      </p>
                    </div>
                    <span
                      className={`pill ${p.status === 'executed' ? 'status-paid' : p.status === 'review_required' ? 'status-promised' : 'status-paused'}`}
                    >
                      {statusText[p.status]}
                    </span>
                    <ArrowRight size={17} />
                  </button>
                );
              })}
          </div>
        ) : (
          <EmptyCard title="Ответов пока нет">
            Нажмите «Разобрать сообщение» и вставьте полученный текст.
          </EmptyCard>
        )}
      </section>
      {compose && (
        <MessageForm
          invoices={invoices}
          onClose={() => setCompose(false)}
          onDone={(p) => {
            setCompose(false);
            setSelected(p);
            setRevision(false);
            void reload();
          }}
        />
      )}
      {selected && !compose && (
        <Dialog
          title={intentText[selected.intent]}
          onClose={() => {
            navigate({ agentProposal: null });
            setSelected(null);
            setRevision(false);
          }}
          wide
        >
          <div className="ops-detail-bar">
            <span
              className={`pill ${selected.status === 'executed' ? 'status-paid' : 'status-promised'}`}
            >
              {statusText[selected.status]}
            </span>
            <span className="ops-muted">
              {invoices.find((i) => i.id === selected.invoice_id)?.number}
            </span>
          </div>
          {selected.intent === 'payment_claim' && (
            <button
              className="button button-outline"
              onClick={() =>
                navigate({ section: 'finance', financeTab: 'ledger', context: selected.invoice_id })
              }
            >
              Сверить оплату этого счёта
            </button>
          )}
          <h3>Ответ покупателя</h3>
          <p className="ops-muted">
            Получено:{' '}
            <time dateTime={selected.received_at}>
              {new Date(selected.received_at).toLocaleString('ru-RU', {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}
            </time>{' '}
            · {Intl.DateTimeFormat().resolvedOptions().timeZone}
          </p>
          <blockquote className="ops-source">{selected.source_text}</blockquote>
          {(selected.extraction.amount_kopeks || selected.extraction.due_date) && (
            <div className="ops-result-grid">
              {selected.extraction.amount_kopeks && (
                <div>
                  <span>Сумма</span>
                  <strong>{money(selected.extraction.amount_kopeks)}</strong>
                </div>
              )}
              {selected.extraction.due_date && (
                <div>
                  <span>Срок оплаты</span>
                  <strong>{dateText(selected.extraction.due_date)}</strong>
                </div>
              )}
            </div>
          )}
          {!!selected.extraction.evidence?.length && (
            <>
              <h3>Что сообщил контрагент</h3>
              {selected.extraction.evidence.map((e, i) => (
                <div className="ops-evidence" key={i}>
                  <span>
                    {{ intent: 'Намерение', amount: 'Сумма', due_date: 'Дата' }[e.field] ||
                      'Основание'}
                  </span>
                  <q>{e.quote}</q>
                </div>
              ))}
            </>
          )}
          {!!selected.reasons.length && (
            <div className="ops-reasons">
              {selected.reasons.map((r) => (
                <p key={r}>
                  {reasons[r] ||
                    'Действие выходит за разрешённые условия. Проверьте счёт и правила работы с покупателем.'}
                </p>
              ))}
            </div>
          )}
          {selected.outcome && (
            <div className="ops-context">
              <Check size={20} />
              <p>
                {selected.outcome.message ||
                  (selected.intent === 'promise'
                    ? 'Договорённость записана. Остаток долга сохранён.'
                    : selected.intent === 'dispute'
                      ? 'Спор зафиксирован. Контакты по счёту приостановлены до разрешения.'
                      : 'Поступление направлено на проверку.')}
              </p>
            </div>
          )}
          <div className="wf-actions">
            <button
              className="button button-outline"
              onClick={() =>
                navigate({
                  section: 'intelligence',
                  context: selected.invoice_id,
                  sourceAgent: selected.id,
                })
              }
            >
              Разобрать условия вручную
            </button>
            <button
              className="button button-outline"
              onClick={() =>
                navigate({ section: 'finance', financeTab: 'ledger', context: selected.invoice_id })
              }
            >
              Открыть сверку счёта
            </button>
          </div>
          <DeskError>{error}</DeskError>
          {selected.status === 'review_required' && (
            <div className="dialog-actions">
              <button
                className="button button-outline"
                disabled={busy}
                onClick={() => void review('reject')}
              >
                <X size={15} />
                Отклонить
              </button>
              <button
                className="button button-dark"
                disabled={busy}
                onClick={() => void review('approve')}
              >
                <Check size={15} />
                {busy
                  ? 'Проверяем…'
                  : selected.intent === 'payment_claim'
                    ? 'Направить на сверку'
                    : 'Подтвердить действие'}
              </button>
            </div>
          )}
          {!['executed', 'rejected', 'superseded', 'processing'].includes(selected.status) && (
            <>
              <button className="text-link ops-revise" onClick={() => setRevision((v) => !v)}>
                Уточнить сообщение
                <ArrowRight size={14} />
              </button>
              {revision && (
                <MessageRevision
                  proposal={selected}
                  onDone={(p) => {
                    navigate({ agentProposal: p.id });
                    setSelected(p);
                    setRevision(false);
                    void reload();
                  }}
                />
              )}
            </>
          )}
        </Dialog>
      )}
    </>
  );
}

function MessageForm({
  invoices,
  onClose,
  onDone,
}: {
  invoices: DeskProps['invoices'];
  onClose: () => void;
  onDone: (p: Proposal) => void;
}) {
  const { invoiceId } = useWorkContext();
  const [key] = useState(() => crypto.randomUUID());
  const [initialReceivedAt] = useState(() => {
    const now = new Date();
    return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  });
  return (
    <Dialog title="Ответ покупателя" onClose={onClose} wide>
      <OperationForm
        draftKey={`incoming:${invoiceId || 'new'}`}
        label="Разобрать сообщение"
        onDone={() => undefined}
        submit={async (data) => {
          const p = await post<Proposal>('/agent/ingest', {
            invoice_id: value(data, 'invoice_id'),
            text: value(data, 'text'),
            received_at: new Date(value(data, 'received_at')).toISOString(),
            idempotency_key: key,
          });
          onDone(p);
        }}
      >
        <InvoiceSelect invoices={invoices} />
        <label className="field full-width">
          Дата и время получения ответа
          <input
            name="received_at"
            type="datetime-local"
            defaultValue={initialReceivedAt}
            aria-describedby="agent-receipt-help"
            required
          />
        </label>
        <p id="agent-receipt-help" className="ops-muted full-width">
          Сроки вроде «завтра» считаются от даты получения. Часовой пояс:{' '}
          {Intl.DateTimeFormat().resolvedOptions().timeZone}.
        </p>
        <label className="field full-width">
          Новый ответ покупателя
          <textarea
            name="text"
            required
            minLength={3}
            maxLength={12000}
            rows={7}
            placeholder="Вставьте текст полученного ответа без истории переписки"
          />
        </label>
      </OperationForm>
    </Dialog>
  );
}
function MessageRevision({
  proposal,
  onDone,
}: {
  proposal: Proposal;
  onDone: (p: Proposal) => void;
}) {
  const { invoiceId } = useWorkContext();
  const [key] = useState(() => crypto.randomUUID());
  return (
    <OperationForm
      draftKey={`incoming-revision:${invoiceId}:${proposal.id}`}
      label="Проверить новую редакцию"
      onDone={() => undefined}
      submit={async (data) => {
        onDone(
          await post<Proposal>(`/agent/proposals/${proposal.id}/revise`, {
            text: value(data, 'text'),
            idempotency_key: key,
          })
        );
      }}
    >
      <label className="field full-width">
        Уточнённый ответ
        <textarea
          name="text"
          defaultValue={proposal.source_text}
          required
          minLength={3}
          maxLength={12000}
          rows={5}
        />
      </label>
    </OperationForm>
  );
}
