import { useEffect, useState, type FormEvent } from 'react';
import { api, post } from '../api';

export function SupportContact() {
  const [email, setEmail] = useState('');
  useEffect(() => {
    void api<{ support_email: string }>('/auth/help')
      .then((r) => setEmail(r.support_email))
      .catch(() => {});
  }, []);
  return (
    <details className="support-contact">
      <summary>Нужна помощь со входом или подключением?</summary>
      {email ? (
        <p>
          Напишите в поддержку: <a href={`mailto:${email}`}>{email}</a>. Укажите компанию и email
          аккаунта.
        </p>
      ) : (
        <p>
          Контакт поддержки пока не настроен. Обратитесь к администратору вашей организации, который
          предоставил доступ к Mandato. Пароль и ссылки восстановления передавать не нужно.
        </p>
      )}
    </details>
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
        if (data.get('password') !== data.get('confirm')) throw new Error('Пароли не совпадают.');
        await post('/auth/reset-password', { token, password: data.get('password') });
        history.replaceState({}, '', '/app?mode=login');
        setMessage('Пароль изменён. Войдите с новым паролем.');
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
    <main className="auth-page invite-page">
      <div className="auth-main">
        <div className="auth-box">
          <h1>{token ? 'Новый пароль' : 'Восстановить доступ'}</h1>
          {message ? (
            <p role="status">{message}</p>
          ) : (
            <form className="auth-form" onSubmit={submit}>
              {token ? (
                <>
                  <label className="field">
                    Новый пароль
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
                    Повторите пароль
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
                  Email аккаунта
                  <input name="email" type="email" required autoComplete="email" />
                </label>
              )}
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <button className="button button-dark" disabled={busy}>
                {busy ? 'Подождите…' : token ? 'Сменить пароль' : 'Получить ссылку'}
              </button>
            </form>
          )}
          <button className="button button-ghost" onClick={onBack}>
            Вернуться ко входу
          </button>
          <SupportContact />
        </div>
      </div>
    </main>
  );
}
