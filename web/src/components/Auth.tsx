import { useState, type FormEvent } from 'react';
import { ArrowUpRight, ArrowLeft, ShieldCheck, Check } from 'lucide-react';
import { Brand } from './Brand';
import { post, type Session } from '../api';
export function Auth({ onSession }: { onSession: (session: Session) => void }) {
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
      history.replaceState({}, '', '/app');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <div className="auth-aside">
        <Brand light />
        <div>
          <span className="eyebrow">
            <i className="status-dot" /> ДЕНЬГИ ВОЗВРАЩАЮТСЯ В ДЕЛО
          </span>
          <h1>
            Ваша работа
            <br />
            заслуживает
            <br />
            <span>
              своевременной
              <br />
              оплаты.
            </span>
          </h1>
          <p>
            Понятный процесс работы с дебиторкой.
            <br />
            От первого письма до поступления денег.
          </p>
        </div>
        <span className="auth-aside-bottom">
          ВАШИ КЛИЕНТЫ. ВАШИ ПРАВИЛА. <ArrowUpRight size={19} />
        </span>
      </div>
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
          <h2>{mode === 'login' ? 'С возвращением.' : 'Начнём с порядка.'}</h2>
          <p>
            {mode === 'login'
              ? 'Ваши счета и договорённости — на месте.'
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
          <div className="auth-trust">
            <ShieldCheck size={17} />
            <span>
              Письма отправляются только с вашего согласия.
              <br />
              Деньги поступают напрямую вашей компании.
            </span>
          </div>
          {mode === 'register' && (
            <p className="auth-no-charge">
              <Check size={13} /> Подключение без списаний с карты
            </p>
          )}
        </div>
        <span className="auth-copyright">© {new Date().getFullYear()} AgentPay</span>
      </main>
    </div>
  );
}
