import { navigate, useWorkContext } from '../navigation';
import { useEffect, useState } from 'react';
import { api, post } from '../api';
import { OperationForm, DeskError, value } from './OperationsUI';
import { SupportContact } from './AccountHelp';
type Setup = {
  connected: boolean;
  can_request: boolean;
  request: null | {
    id: string;
    email: string;
    status: string;
    note: string;
    owner?: string;
    verified_at?: string;
    verification_reference?: string;
  };
};
export function MailSetup() {
  const { invoiceId, caseId } = useWorkContext();
  const [setup, setSetup] = useState<Setup | null>(null),
    [error, setError] = useState('');
  const load = () =>
    api<Setup>('/mail/setup')
      .then(setSetup)
      .catch((e) => setError((e as Error).message));
  useEffect(() => {
    void load();
  }, []);
  return (
    <section className="ops-card mail-setup">
      <div className="mail-setup-heading">
        <h2>Подключение почты</h2>
        {setup && (
          <span
            className={`mail-setup-badge ${setup.connected && setup.request?.verified_at ? 'is-success' : 'is-warning'}`}
          >
            {setup.connected
              ? setup.request?.verified_at
                ? 'Подключена'
                : 'Нужна проверка'
              : 'Не подключена'}
          </span>
        )}
      </div>
      <DeskError>{error}</DeskError>
      {!setup ? (
        <p>Проверяем подключение…</p>
      ) : setup.connected ? (
        <p
          className={`mail-setup-status ${setup.request?.verified_at ? 'is-success' : 'is-warning'}`}
          role="status"
        >
          {setup.request?.verified_at
            ? 'Контрольное письмо доставлено. Можно включать отправку по вашим правилам.'
            : 'Настройки сохранены. Администратору нужно проверить доставку письма.'}
        </p>
      ) : (
        <>
          <p className="mail-setup-status is-warning">
            Письма пока можно готовить и скачивать. Чтобы отправлять их из Mandato, оставьте заявку
            на подключение.
          </p>
          {setup.request && (
            <div className="mail-setup-request" role="status">
              <strong>
                Заявка № {setup.request.id.slice(0, 8)} ·{' '}
                {(
                  {
                    pending: 'Ожидает администратора',
                    in_progress: 'В работе',
                    completed: 'Обработана',
                  } as Record<string, string>
                )[setup.request.status] || setup.request.status}
              </strong>
              <p>Адрес: {setup.request.email}</p>
              {setup.request.owner && <p>Ответственный: {setup.request.owner}</p>}
              {setup.request.note && <p>{setup.request.note}</p>}
            </div>
          )}
          {setup.can_request ? (
            <OperationForm
              draftKey="mail-setup"
              label={setup.request ? 'Обновить заявку' : 'Оставить заявку на подключение'}
              submit={async (data) => {
                setSetup(await post<Setup>('/mail/setup', { email: value(data, 'email') }));
              }}
              onDone={() => {}}
            >
              <label className="field full-width">
                Почта для отправки писем покупателям
                <input
                  type="email"
                  name="email"
                  defaultValue={setup.request?.email || ''}
                  required
                />
              </label>
            </OperationForm>
          ) : (
            <p>Попросите руководителя оставить заявку в этом разделе.</p>
          )}
          <button className="mail-status-refresh" onClick={() => void load()}>
            Проверить статус подключения
          </button>
        </>
      )}
      {caseId && (
        <button
          className="mail-return-link"
          onClick={() =>
            navigate({ section: 'workflow', case: caseId, context: invoiceId || null })
          }
        >
          Вернуться к делу
        </button>
      )}
      <SupportContact />
    </section>
  );
}
