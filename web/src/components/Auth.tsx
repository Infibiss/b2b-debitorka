import { AccountRecovery, SupportContact } from './AccountHelp';
import { navigate } from '../navigation';
import { useState, type FormEvent } from 'react';
import { ArrowUpRight, ArrowLeft } from 'lucide-react';
import { Brand } from './Brand';
import { AuthAside } from './AuthAside';
import { post, type Session } from '../api';
import { useInvitationToken } from './useInvitationToken';
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
      onSession(await post<Session>(`/auth/${mode}`, data));
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
          На главную
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
              Создать аккаунт
            </button>
            <button
              className={mode === 'login' ? 'active' : ''}
              onClick={() => {
                setMode('login');
                setError('');
              }}
            >
              Войти
            </button>
          </div>
          <h2>{mode === 'login' ? 'Войти в Mandato' : 'Создать аккаунт'}</h2>
          <p>
            {mode === 'login'
              ? 'Введите рабочую почту и пароль.'
              : 'Создайте рабочее пространство вашей компании.'}
          </p>
          <form onSubmit={submit} className="auth-form">
            {mode === 'register' && (
              <>
                <label className="field">
                  Компания
                  <input
                    required
                    name="company"
                    autoComplete="organization"
                    placeholder="ООО «Ваша компания»"
                    maxLength={160}
                  />
                </label>
                <label className="field">
                  Ваше имя
                  <input
                    required
                    name="name"
                    autoComplete="name"
                    placeholder="Как к вам обращаться"
                    maxLength={100}
                  />
                </label>
              </>
            )}
            <label className="field">
              Рабочая почта
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
              Пароль
              <input
                required
                type="password"
                name="password"
                minLength={mode === 'register' ? 12 : 1}
                maxLength={128}
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                placeholder={mode === 'register' ? 'Не менее 12 символов' : 'Ваш пароль'}
              />
            </label>
            {mode === 'register' && (
              <label className="auth-consent">
                <input type="checkbox" required />
                <span>
                  Я уполномочен работать от имени компании и принимаю{' '}
                  <a href="/#pricing" target="_blank" rel="noreferrer">
                    условия подключения
                  </a>
                  .
                </span>
              </label>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button disabled={busy} className="button button-dark" type="submit">
              {busy ? 'Подождите…' : mode === 'login' ? 'Войти' : 'Создать аккаунт'}
              {busy ? <span className="button-loading" /> : <ArrowUpRight size={19} />}
            </button>
          </form>
          {mode === 'login' && (
            <button className="auth-recovery-link" onClick={() => setRecovering(true)}>
              Забыли пароль?
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
          <h1>Присоединиться к команде</h1>
          <p>
            Вы получите доступ бухгалтера к рабочему пространству организации, которая вас
            пригласила.
          </p>
          <form className="auth-form" onSubmit={join}>
            <label className="field">
              Ваше имя
              <input name="name" required maxLength={100} autoComplete="name" />
            </label>
            <label className="field">
              Пароль
              <input
                name="password"
                type="password"
                required
                minLength={10}
                maxLength={256}
                autoComplete="new-password"
              />
            </label>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button className="button button-dark" disabled={busy}>
              {busy ? 'Присоединяем…' : 'Присоединиться'}
              <ArrowUpRight size={16} />
            </button>
          </form>
          <a className="text-link" href="/app?mode=login">
            Уже приняли приглашение? Войти
          </a>
        </div>
      </div>
    </main>
  );
}
