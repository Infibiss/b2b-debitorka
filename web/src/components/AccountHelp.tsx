import { t } from '../i18n';
import { useEffect, useState, type FormEvent } from 'react';
import { api, post } from '../api';
import { ArrowLeft, ArrowUpRight } from 'lucide-react';
import { AuthAside } from './AuthAside';
import './auth-settings.css';

export function SupportContact() {
  const [email, setEmail] = useState('');
  useEffect(() => {
    void api<{ support_email: string }>('/auth/help')
      .then((r) => setEmail(r.support_email))
      .catch(() => {});
  }, []);
  return (
    <div className="support-contact">
      {email ? (
        <a href={`mailto:${email}`}>
          {t('Написать в поддержку')} <ArrowUpRight size={14} />
        </a>
      ) : (
        <p>{t('Для помощи со входом обратитесь к администратору вашей компании.')}</p>
      )}
    </div>
  );
}
export function AccountRecovery({ token, onBack }: { token?: string; onBack: () => void }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const data = new FormData(event.currentTarget);
    try {
      if (token) {
        if (data.get('password') !== data.get('confirm'))
          throw new Error(t('Пароли не совпадают.'));
        await post('/auth/reset-password', { token, password: data.get('password') });
        history.replaceState({}, '', '/app?mode=login');
        setMessage(t('Пароль изменён. Войдите с новым паролем.'));
      } else {
        const result = await post<{ detail: string }>('/auth/recovery', {
          email: data.get('email'),
        });
        setMessage(result.detail);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page recovery-page">
      <AuthAside />
      <main className="auth-main">
        <button className="auth-back" onClick={onBack}>
          <ArrowLeft size={15} />
          {t('Вернуться ко входу')}
        </button>
        <div className="auth-box recovery-box">
          <h2>{token ? t('Новый пароль') : t('Восстановить доступ')}</h2>
          {!message && (
            <p>
              {token
                ? t('Придумайте пароль не короче 12 символов.')
                : t('Пришлём ссылку на почту вашего аккаунта.')}
            </p>
          )}
          {message ? (
            <p className="recovery-result" role="status">
              {message}
            </p>
          ) : (
            <form className="auth-form" onSubmit={submit}>
              {token ? (
                <>
                  <label className="field">
                    {t('Новый пароль')}
                    <input
                      name="password"
                      type="password"
                      required
                      minLength={12}
                      maxLength={128}
                      autoComplete="new-password"
                    />
                  </label>
                  <label className="field">
                    {t('Повторите пароль')}
                    <input
                      name="confirm"
                      type="password"
                      required
                      minLength={12}
                      maxLength={128}
                      autoComplete="new-password"
                    />
                  </label>
                </>
              ) : (
                <label className="field">
                  {t('Почта аккаунта')}
                  <input name="email" type="email" required autoComplete="email" />
                </label>
              )}
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <button className="button button-dark" disabled={busy}>
                {busy ? t('Подождите…') : token ? t('Сменить пароль') : t('Получить ссылку')}
              </button>
            </form>
          )}
          {message && (
            <button className="button button-dark recovery-signin" onClick={onBack}>
              {t('Вернуться ко входу')}
              <ArrowUpRight size={17} />
            </button>
          )}
          <SupportContact />
        </div>
        <span className="auth-copyright">© {new Date().getFullYear()} Mandato</span>
      </main>
    </div>
  );
}
