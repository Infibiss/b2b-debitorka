import { useEffect, useState } from 'react';
import { api, money, type Invoice } from '../api';
import { navigate, useRouteField } from '../navigation';
import { DeskError, InvoiceSelect } from './OperationsUI';

type Entry = {
  id: string;
  created_at: string;
  title: string;
  body: string;
  section: string;
  reference: string;
  amount: number | null;
};
type Page = { items: Entry[]; total: number; next_offset: number | null };
function entryBody(item: Entry) {
  if (item.title === 'Открыто юридическое дело') return '';
  if (item.title !== 'Подготовлен юридический документ') return item.body;
  const titles: Record<string, string> = {
    pretrial_claim: 'Претензия',
    court_order: 'Заявление о выдаче приказа',
    statement_of_claim: 'Исковое заявление',
  };
  return item.body.replace(
    /^(pretrial_claim|court_order|statement_of_claim)(?=,)/,
    (kind) => titles[kind] || kind
  );
}
export function CaseConversation({
  invoices,
  onOpen,
}: {
  invoices: Invoice[];
  onOpen: (id: string) => void;
}) {
  const [invoiceId, setInvoiceId] = useRouteField<string>('context', '');
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    setData(null);
    setError('');
    setBusy(false);
    if (invoiceId)
      void api<Page>(`/workflow/invoices/${encodeURIComponent(invoiceId)}/timeline`)
        .then((result) => {
          if (alive) setData(result);
        })
        .catch((e) => {
          if (alive) setError((e as Error).message);
        });
    return () => {
      alive = false;
    };
  }, [invoiceId]);
  async function more() {
    if (data?.next_offset == null) return;
    setBusy(true);
    setError('');
    try {
      const next = await api<Page>(
        `/workflow/invoices/${encodeURIComponent(invoiceId)}/timeline?offset=${data.next_offset}`
      );
      if (new URLSearchParams(location.search).get('context') === invoiceId)
        setData({
          ...next,
          items: [
            ...data.items,
            ...next.items.filter((e) => !data.items.some((old) => old.id === e.id)),
          ],
        });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="ops-card case-conversation">
      <h2>Единая история по счёту</h2>
      <p>Входящие и исходящие сообщения, факты, решения, действия и оплаты — от новых к старым.</p>
      <InvoiceSelect invoices={invoices} value={invoiceId} onChange={setInvoiceId} />
      {invoiceId && (
        <div className="wf-actions">
          <button className="button button-outline" onClick={() => onOpen(invoiceId)}>
            Написать покупателю
          </button>
          <button className="button button-outline" onClick={() => navigate({ section: 'agent' })}>
            Добавить входящий ответ
          </button>
          <button
            className="button button-outline"
            onClick={() => navigate({ section: 'intelligence' })}
          >
            Согласовать условия
          </button>
          <button
            className="button button-outline"
            onClick={() => navigate({ section: 'finance', financeTab: 'ledger' })}
          >
            Покупатель оплатил — сверить
          </button>
        </div>
      )}
      <DeskError>{error}</DeskError>
      {!invoiceId ? (
        <p>Выберите счёт для истории и действий по нему.</p>
      ) : !data ? (
        <p>Загружаем историю…</p>
      ) : (
        <>
          <ol className="conversation-timeline">
            {data.items.map((item) => (
              <li key={item.id}>
                <time dateTime={item.created_at}>
                  {new Date(item.created_at).toLocaleString('ru-RU')}
                </time>
                <h3>{item.title}</h3>
                {item.amount != null && <strong>{money(item.amount)}</strong>}
                {entryBody(item) && <p>{entryBody(item)}</p>}
                <button
                  className="wf-text-button"
                  onClick={() =>
                    item.section === 'messages'
                      ? onOpen(invoiceId)
                      : navigate({
                          section: item.section,
                          financeTab: item.section === 'finance' ? 'ledger' : null,
                          agentProposal: item.section === 'agent' ? item.reference || null : null,
                          proposal: item.section === 'intelligence' ? item.reference : null,
                        })
                  }
                >
                  Открыть действие
                </button>
              </li>
            ))}
          </ol>
          {!data.items.length && <p>История пока пуста. Добавьте ответ или подготовьте письмо.</p>}
          {data.next_offset != null && (
            <button disabled={busy} className="button button-outline" onClick={() => void more()}>
              Показать более ранние записи
            </button>
          )}
        </>
      )}
    </section>
  );
}
