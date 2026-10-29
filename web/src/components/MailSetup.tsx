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
      <h2>Подключение почты</h2>
      <DeskError>{error}</DeskError>
      {!setup ? (
        <p>Проверяем подключение…</p>
      ) : setup.connected ? (
        <p role="status">
          {setup.request?.verified_at
            ? 'Почта подключена, контрольная доставка подтверждена оператором.'
            : 'SMTP настроен. Контрольная доставка ещё не подтверждена оператором.'}{' '}
          Отправка доступна после согласования писем и правил работы.
        </p>
      ) : (
        <>
          <p>
            Почта не подключена. Руководитель оставляет заявку, администратор согласует доступ и
            настраивает SMTP для вашей компании. Пароль от почты здесь не требуется.
          </p>
          {setup.request && (
            <div className="ops-context" role="status">
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
              <p>
                Ответственный:{' '}
                {setup.request.owner || 'Администратор установки — сотрудник ещё не назначен'}.
              </p>
              <p>
                Проверка доставки:{' '}
                {setup.request.verified_at ? 'подтверждена оператором' : 'ожидается'}.
              </p>
              <p>
                {setup.request.note ||
                  'Заявка сохранена. Передайте номер администратору вашей установки Mandato для согласования подключения.'}
              </p>
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
          <button className="button button-outline" onClick={() => void load()}>
            Проверить статус подключения
          </button>
        </>
      )}
      {setup?.connected && setup.request && (
        <p>
          Ответственный: {setup.request.owner || 'администратор установки'}.{' '}
          {setup.request.verification_reference ||
            'Попросите администратора выполнить контрольную отправку и зарегистрировать результат.'}
        </p>
      )}
      <button
        className="button button-outline"
        onClick={() =>
          navigate({ section: 'workflow', case: caseId || null, context: invoiceId || null })
        }
      >
        {caseId ? 'Вернуться к делу' : 'Открыть рабочие дела'}
      </button>
      <SupportContact />
    </section>
  );
}
