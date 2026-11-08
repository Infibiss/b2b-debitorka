import { t } from '../i18n';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { AlertCircle, Check, CircleCheck, Mail, Plus, RefreshCw, Users } from 'lucide-react';
import { api, dateText, post } from '../api';
import './workflow.css';

type Team = {
  role: 'manager' | 'accountant';
  members: { id: string; name: string; email: string; role: string }[];
  invitations: { id: string; email: string; expires_at: string; accepted_at: string | null }[];
};
type Notify = (text: string, error?: boolean) => void;
const failure = (error: unknown) =>
  error instanceof Error ? error.message : t('Не удалось загрузить данные. Попробуйте ещё раз.');

export function TeamSettings({ notify }: { notify: Notify }) {
  const [team, setTeam] = useState<Team | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [inviteLink, setInviteLink] = useState('');
  const reload = useCallback(async () => {
    try {
      setTeam(await api<Team>('/workflow/team'));
      setError('');
    } catch (e) {
      setError(failure(e));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const email = String(new FormData(form).get('email')).trim();
    setBusy(true);
    setError('');
    try {
      const result = await post<{ token: string }>('/workflow/invitations', { email });
      setInviteLink(`${window.location.origin}/app#invite=${encodeURIComponent(result.token)}`);
      form.reset();
      await reload();
      notify(t('Приглашение создано. Передайте ссылку бухгалтеру.'));
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  const manager = team?.role === 'manager';
  return (
    <div className="wf-desk wf-management">
      {error && (
        <div className="wf-error" role="alert">
          {error}
        </div>
      )}
      <section className="wf-panel">
        <div className="wf-panel-title">
          <Users size={21} />
          <div>
            <h2>{t('Ваша команда')}</h2>
            <p>{t('Общее пространство счетов, истории и решений')}</p>
          </div>
        </div>
        <span className="wf-role">
          {t('Ваша роль:')} {manager ? t('руководитель') : t('бухгалтер')}
        </span>
        <div className="wf-members">
          {team?.members.map((member) => (
            <div className="wf-member" key={member.id}>
              <span className="wf-avatar">
                {(member.name || member.email).slice(0, 1).toUpperCase()}
              </span>
              <div>
                <strong>{member.name || member.email}</strong>
                <small>{member.email}</small>
              </div>
              <span>{member.role === 'manager' ? t('Руководитель') : t('Бухгалтер')}</span>
            </div>
          ))}
        </div>
        {manager && (
          <form className="wf-invite-form" onSubmit={invite}>
            <h3>{t('Пригласить бухгалтера')}</h3>
            <p>
              {t(
                'Бухгалтер работает с делами и платежами. Согласования и правила остаются у руководителя.'
              )}
            </p>
            <label>
              {t('Электронная почта')}
              <input
                type="email"
                name="email"
                required
                maxLength={254}
                placeholder="accountant@company.ru"
              />
            </label>
            <button className="button button-white" disabled={busy}>
              <Plus size={15} />
              {t('Создать приглашение')}
            </button>
          </form>
        )}
        {inviteLink && (
          <div className="wf-invite-link">
            <label>
              {t('Ссылка для приглашённого бухгалтера')}
              <input readOnly value={inviteLink} onFocus={(e) => e.currentTarget.select()} />
            </label>
            <p>{t('Передайте ссылку лично. Вход выполняется с указанным в приглашении email.')}</p>
          </div>
        )}
        {team?.invitations.some((invitation) => !invitation.accepted_at) && (
          <div className="wf-pending">
            <h3>{t('Приглашения ожидают ответа')}</h3>
            {team.invitations
              .filter((invitation) => !invitation.accepted_at)
              .map((invitation) => (
                <div key={invitation.id}>
                  <span>{invitation.email}</span>
                  <small>
                    {new Date(invitation.expires_at).getTime() < Date.now()
                      ? t('Истекло')
                      : t('До {0}', [dateText(invitation.expires_at)])}
                  </small>
                </div>
              ))}
          </div>
        )}
      </section>
    </div>
  );
}

type MailboxIssue = { id: string; status: string; reason: string; created_at: string };
type Mailbox = {
  configured: boolean;
  status: string;
  checked_at: string | null;
  reason: string | null;
  issues_count: number;
  issues: MailboxIssue[];
};
const mailboxReasons: Record<string, string> = {
  mailbox_sync_failed: t(
    'Не удалось проверить почтовый ящик. Проверьте доступ и настройки подключения.'
  ),
  mailbox_authentication: t('Почтовый сервер не подтвердил доступ. Проверьте данные подключения.'),
  mailbox_folder: t('Не удалось открыть папку входящих писем.'),
  ambiguous_sender: t('В письме неоднозначно указан отправитель. Проверьте исходное письмо.'),
  invalid_sender: t('Не удалось определить корректный адрес отправителя.'),
  sender_authentication_required: t('Подлинность отправителя не подтверждена почтовым сервером.'),
  reply_not_correlated: t('Не удалось однозначно связать ответ с исходящим письмом и делом.'),
  sender_mismatch: t('Адрес отправителя не совпадает с подтверждённым контактом дела.'),
  plain_text_required: t('В письме нет доступного текстового содержимого. Прочитайте его вручную.'),
  text_size_invalid: t(
    'Текст письма не подходит для автоматического разбора. Проверьте его вручную.'
  ),
  message_size_unavailable: t('Не удалось определить размер письма до загрузки.'),
  message_too_large: t('Письмо превышает допустимый размер. Просмотрите его в почтовом ящике.'),
  message_body_unavailable: t('Почтовый сервер не передал содержимое письма.'),
  processing_interrupted: t('Разбор письма был прерван. Проверьте, обработан ли ответ по делу.'),
  invalid_message: t('Формат письма не удалось проверить. Нужен ручной разбор.'),
  invalid_received_time: t('Не удалось подтвердить время получения письма.'),
};
function mailboxReason(reason: string | null) {
  return reason
    ? mailboxReasons[reason] || t('Для этого письма или подключения требуется ручная проверка.')
    : '';
}
function mailboxTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? t('Дата проверки недоступна')
    : new Intl.DateTimeFormat('ru-RU', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'Europe/Moscow',
      }).format(date);
}
export function InboxStatus({ notify }: { notify: Notify }) {
  const [mailbox, setMailbox] = useState<Mailbox | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [issueError, setIssueError] = useState<{ id: string; text: string } | null>(null);
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setMailbox(await api<Mailbox>('/workflow/mailbox'));
      setError('');
    } catch (e) {
      setError(failure(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  async function resolve(event: FormEvent<HTMLFormElement>, id: string) {
    event.preventDefault();
    const resolution = String(new FormData(event.currentTarget).get('resolution')).trim();
    setBusy(id);
    setIssueError(null);
    try {
      await post(`/workflow/mailbox/issues/${encodeURIComponent(id)}/resolve`, { resolution });
      await reload();
      notify(t('Результат разбора входящего письма сохранён'));
    } catch (e) {
      setIssueError({ id, text: failure(e) });
    } finally {
      setBusy(null);
    }
  }
  const checkedTime = mailbox?.checked_at ? new Date(mailbox.checked_at).getTime() : NaN;
  const stale = !Number.isFinite(checkedTime) || clock - checkedTime > 5 * 60_000;
  const verified = !error && mailbox?.configured && mailbox.status === 'ok' && !stale;
  const statusTitle = error
    ? t('Состояние почты не удалось обновить')
    : !mailbox?.configured
      ? t('Входящая почта не настроена')
      : mailbox.status === 'not_checked' || !mailbox.checked_at
        ? t('Настроено, проверка ещё не выполнена')
        : mailbox.status === 'error'
          ? t('Ошибка проверки входящей почты')
          : mailbox.status === 'backlog'
            ? t('Есть очередь необработанной почты')
            : mailbox.status === 'ok' && stale
              ? t('Проверка почты устарела')
              : verified
                ? t('Получение почты проверено')
                : t('Входящая почта требует проверки');
  return (
    <section className="wf-panel wf-mailbox-panel" aria-label={t('Входящая почта')}>
      <div className="wf-panel-title">
        <Mail size={21} />
        <div>
          <h2>{t('Входящая почта')}</h2>
          <p>{t('Подключение, последняя проверка и письма для ручного разбора')}</p>
        </div>
        <button
          className="icon-button"
          aria-label={t('Обновить статус почты')}
          disabled={loading}
          onClick={() => void reload()}
        >
          <RefreshCw size={16} className={loading ? 'wf-spinning' : ''} />
        </button>
      </div>
      {error && (
        <div className="wf-error" role="alert">
          {t('Не удалось загрузить состояние входящей почты.')} {error}
          <button onClick={() => void reload()}>{t('Повторить загрузку почты')}</button>
        </div>
      )}
      {loading && !mailbox ? (
        <p className="wf-muted" role="status">
          {t('Проверяем сохранённое состояние почты…')}
        </p>
      ) : (
        mailbox && (
          <>
            <div className={`wf-mailbox-status ${verified ? 'is-verified' : ''}`}>
              <span className="wf-mailbox-symbol">
                {verified ? <CircleCheck size={22} /> : <AlertCircle size={22} />}
              </span>
              <div>
                <h3>{statusTitle}</h3>
                <p>
                  {!mailbox.configured
                    ? t(
                        'Автоматическое получение ответов по почте недоступно. Настройте подключение и дождитесь успешной серверной проверки.'
                      )
                    : verified
                      ? t(
                          'Сервер успешно проверил ящик. Это состояние последней проверки; новые письма появятся после следующего чтения.'
                        )
                      : t(
                          'Настройка подключения сама по себе не подтверждает, что письма успешно получаются. Проверьте канал до продолжения автоматической работы.'
                        )}
                </p>
                {mailbox.reason && (
                  <p className="wf-mailbox-reason">{mailboxReason(mailbox.reason)}</p>
                )}
                <small>
                  {mailbox.checked_at
                    ? t('Последняя проверка: {0} · МСК', [mailboxTime(mailbox.checked_at)])
                    : t('Успешная проверка ещё не зарегистрирована')}
                </small>
              </div>
            </div>
            <div className="wf-mailbox-issues-title">
              <h3>
                {t('Входящих для разбора:')} {mailbox.issues_count}
              </h3>
            </div>
            {mailbox.issues?.length > 0 ? (
              <>
                <p className="wf-mailbox-note">
                  {t(
                    'Проверьте исходное письмо в вашем почтовом ящике и внесите результат разбора. Эта запись не изменяет суммы и не запускает повторную обработку письма.'
                  )}
                </p>
                <div className="wf-mailbox-issues">
                  {mailbox.issues.map((issue, index) => (
                    <article className="wf-mailbox-issue" key={issue.id}>
                      <div className="wf-mailbox-issue-heading">
                        <strong>
                          {t('Письмо для проверки ·')} {index + 1}
                        </strong>
                        <small>
                          {mailboxTime(issue.created_at)} {t('· МСК')}
                        </small>
                      </div>
                      <p>{mailboxReason(issue.reason)}</p>
                      {issue.status === 'processing' && (
                        <span className="wf-mailbox-processing">{t('Обработка не завершена')}</span>
                      )}
                      <form onSubmit={(event) => void resolve(event, issue.id)}>
                        <label>
                          {t('Результат проверки')}
                          <input
                            name="resolution"
                            required
                            minLength={3}
                            maxLength={2000}
                            aria-label={t('Результат проверки письма {0}', [index + 1])}
                            placeholder={t('Что проверено и какое действие принято')}
                          />
                        </label>
                        {issueError?.id === issue.id && (
                          <p className="wf-error" role="alert">
                            {issueError.text}
                          </p>
                        )}
                        <button className="button button-white" disabled={!!busy}>
                          <Check size={14} />
                          {busy === issue.id ? t('Сохраняем…') : t('Зафиксировать разбор')}
                        </button>
                      </form>
                    </article>
                  ))}
                </div>
                {mailbox.issues_count > mailbox.issues.length && (
                  <p className="wf-mailbox-note">
                    {t('Показаны последние')} {mailbox.issues.length}{' '}
                    {t('писем. После разбора список обновится.')}
                  </p>
                )}
              </>
            ) : (
              <p className="wf-mailbox-note">
                {mailbox.configured
                  ? t('В текущем списке нет писем, ожидающих ручного разбора.')
                  : t('Список входящих появится после настройки и проверки канала.')}
              </p>
            )}
          </>
        )
      )}
    </section>
  );
}
