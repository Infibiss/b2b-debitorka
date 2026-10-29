import { useEffect, useState } from 'react';
import { api, post } from '../api';
import { DeskError } from './OperationsUI';
type Source = {
  id: string;
  kind: string;
  reference: string;
  occurred_on: string;
  sha256: string;
  download_url?: string;
};
export function ArchiveEvidence({
  invoiceId,
  caseId,
  existing,
  onAdded,
}: {
  invoiceId: string;
  caseId: string;
  existing: { reference: string }[];
  onAdded: () => Promise<unknown>;
}) {
  const [items, setItems] = useState<Source[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState('');
  useEffect(() => {
    let alive = true;
    void api<{ items: Source[] }>(`/portfolio/invoices/${invoiceId}/evidence`)
      .then((r) => {
        if (alive) setItems(r.items);
      })
      .catch((e) => {
        if (alive) setError((e as Error).message);
      });
    return () => {
      alive = false;
    };
  }, [invoiceId]);
  const available = items.filter(
    (item) => !existing.some((proof) => proof.reference === item.reference)
  );
  return (
    <div className="ops-context">
      <strong>Документы из общего архива</strong>
      <DeskError>{error}</DeskError>
      {available.length ? (
        available.map((item) => (
          <div className="portfolio-document" key={item.id}>
            <span>{item.reference}</span>
            <button
              type="button"
              className="button button-outline button-small"
              disabled={!!busy}
              onClick={async () => {
                setBusy(item.id);
                setError('');
                try {
                  await post(`/legal/cases/${caseId}/evidence`, {
                    kind: ['contract', 'performance', 'reconciliation'].includes(item.kind)
                      ? item.kind
                      : 'other',
                    title: item.reference.slice(0, 300),
                    reference: item.reference,
                    occurred_on: item.occurred_on,
                    sha256: item.sha256,
                  });
                  await onAdded();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy('');
                }
              }}
            >
              {busy === item.id ? 'Добавляем…' : 'Использовать в деле'}
            </button>
          </div>
        ))
      ) : (
        <p>
          Новых документов в архиве по этому счёту нет. Добавьте договор в разделе «Документы» или
          зарегистрируйте доказательство ниже.
        </p>
      )}
    </div>
  );
}
