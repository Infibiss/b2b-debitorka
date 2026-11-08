import { t } from '../i18n';
import { AccountRecovery, SupportContact } from './AccountHelp';
import { navigate } from '../navigation';
import { useState, type FormEvent } from 'react';
import { ArrowUpRight, ArrowLeft } from 'lucide-react';
import { Brand } from './Brand';
import { AuthAside } from './AuthAside';
import { post, type Session } from '../api';
import { useInvitationToken } from './useInvitationToken';

const legalVersion = '2026-11-08';
export function Auth({ onSession }: { onSession: (session: Session) => void }) {
  const invitation = useInvitationToken();
  const [resetToken, setResetToken] = useState(
    () => new URLSearchParams(location.hash.slice(1)).get('reset') || ''
  );
  const [recovering, setRecovering] = useState(false);
  const [mode, setMode] = useState(
      new URLSearchParams(location.search).get('mode') === 'login' ? 'login' : 'register'
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    setError('');
    try {
      onSession(
        await post<Session>(`/auth/${mode}`, {
          ...data,
          ...(mode === 'register'
            ? {
                terms_accepted: true,
                terms_version: legalVersion,
                personal_data_consent: true,
                consent_version: legalVersion,
              }
            : {}),
        })
      );
      navigate({ mode: null }, true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (recovering || resetToken)
    return (
      <AccountRecovery
        token={resetToken || undefined}
        onBack={() => {
          setResetToken('');
          setRecovering(false);
          setMode('login');
          history.replaceState({}, '', '/app?mode=login');
        }}
      />
    );
  if (invitation) return <InvitationRegistration token={invitation} onSession={onSession} />;
  return (
    <div className="auth-page">
      <AuthAside />
      <main className="auth-main">
        <a className="auth-back" href="/">
          <ArrowLeft size={15} />
          {t('На главную')}
        </a>
        <div className="auth-box">
          <div className="auth-tabs">
            <button
              className={mode === 'register' ? 'active' : ''}
              onClick={() => {
                setMode('register');
                setError('');
              }}
            >
              {t('Создать аккаунт')}
            </button>
            <button
              className={mode === 'login' ? 'active' : ''}
              onClick={() => {
                setMode('login');
                setError('');
              }}
            >
              {t('Войти')}
            </button>
          </div>
          <h2>{mode === 'login' ? t('Войти в Mandato') : t('Создать аккаунт')}</h2>
          <p>
            {mode === 'login'
              ? t('Введите рабочую почту и пароль.')
              : t('Создайте рабочее пространство вашей компании.')}
          </p>
          <form onSubmit={submit} className="auth-form">
            {mode === 'register' && (
              <>
                <label className="field">
                  {t('Компания')}
                  <input
                    required
                    name="company"
                    autoComplete="organization"
                    placeholder={t('ООО «Ваша компания»')}
                    maxLength={160}
                  />
                </label>
                <label className="field">
                  {t('Ваше имя')}
                  <input
                    required
                    name="name"
                    autoComplete="name"
                    placeholder={t('Как к вам обращаться')}
                    maxLength={100}
                  />
                </label>
              </>
            )}
            <label className="field">
              {t('Рабочая почта')}
              <input
                required
                type="email"
                name="email"
                autoComplete="email"
                placeholder="name@company.ru"
                maxLength={254}
              />
            </label>
            <label className="field">
              {t('Пароль')}
              <input
                required
                type="password"
                name="password"
                minLength={mode === 'register' ? 12 : 1}
                maxLength={128}
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                placeholder={mode === 'register' ? t('Не менее 12 символов') : t('Ваш пароль')}
              />
            </label>
            {mode === 'register' && (
              <label className="auth-consent">
                <input type="checkbox" required />
                <span>
                  {t('Мне исполнилось 18 лет, я уполномочен работать от имени компании и принимаю')}{' '}
                  <a href="/terms" target="_blank" rel="noreferrer">
                    {t('условия использования')}
                  </a>
                  .
                </span>
              </label>
            )}
            {mode === 'register' && (
              <label className="auth-consent">
                <input type="checkbox" required />
                <span>
                  {t('Даю')}{' '}
                  <a href="/consent" target="_blank" rel="noreferrer">
                    {t('согласие на обработку персональных данных')}
                  </a>
                  .
                </span>
              </label>
            )}
            {mode === 'register' && (
              <p className="auth-policy-note">
                {t('Как используются имя, рабочая почта и данные компании — в')}{' '}
                <a href="/privacy" target="_blank" rel="noreferrer">
                  {t('политике обработки данных')}
                </a>
                {t('. Запрос на исправление или удаление можно направить')}{' '}
                <a href="/data-request" target="_blank" rel="noreferrer">
                  {t('отдельно')}
                </a>
                .
              </p>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button disabled={busy} className="button button-dark" type="submit">
              {busy ? t('Подождите…') : mode === 'login' ? t('Войти') : t('Создать аккаунт')}
              {busy ? <span className="button-loading" /> : <ArrowUpRight size={19} />}
            </button>
          </form>
          {mode === 'login' && (
            <button className="auth-recovery-link" onClick={() => setRecovering(true)}>
              {t('Забыли пароль?')}
            </button>
          )}
          <SupportContact />
        </div>
        <span className="auth-copyright">© {new Date().getFullYear()} Mandato</span>
      </main>
    </div>
  );
}

function InvitationRegistration({
  token,
  onSession,
}: {
  token: string;
  onSession: (session: Session) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function join(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    setError('');
    try {
      const password = String(data.get('password'));
      const result = await post<{ user: { email: string } }>('/workflow/invitations/accept', {
        token,
        name: String(data.get('name')),
        password,
        personal_data_consent: true,
        consent_version: legalVersion,
      });
      const session = await post<Session>('/auth/login', { email: result.user.email, password });
      history.replaceState({}, '', '/app');
      onSession(session);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page invite-page">
      <div className="auth-main">
        <div className="auth-box">
          <Brand />
          <h1>{t('Присоединиться к команде')}</h1>
          <p>
            {t(
              'Вы получите доступ бухгалтера к рабочему пространству организации, которая вас пригласила.'
            )}
          </p>
          <form className="auth-form" onSubmit={join}>
            <label className="field">
              {t('Ваше имя')}
              <input name="name" required maxLength={100} autoComplete="name" />
            </label>
            <label className="field">
              {t('Пароль')}
              <input
                name="password"
                type="password"
                required
                minLength={10}
                maxLength={256}
                autoComplete="new-password"
              />
            </label>
            <label className="auth-consent">
              <input type="checkbox" required />
              <span>
                {t('Мне исполнилось 18 лет. Даю')}{' '}
                <a href="/consent" target="_blank" rel="noreferrer">
                  {t('согласие на обработку персональных данных')}
                </a>
                .
              </span>
            </label>
            <p className="auth-policy-note">
              {t('Присоединяясь, вы работаете в пределах доступа, предоставленного организацией.')}{' '}
              <a href="/terms" target="_blank" rel="noreferrer">
                {t('Условия использования')}
              </a>{' '}
              {t('и')}{' '}
              <a href="/privacy" target="_blank" rel="noreferrer">
                {t('обработка данных')}
              </a>
              .
            </p>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button className="button button-dark" disabled={busy}>
              {busy ? t('Присоединяем…') : t('Присоединиться')}
              <ArrowUpRight size={16} />
            </button>
          </form>
          <a className="text-link" href="/app?mode=login">
            {t('Уже приняли приглашение? Войти')}
          </a>
        </div>
      </div>
    </main>
  );
}
