import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, post } from '../api';
import './workspace-data-settings.css';

type DeletionRequest = { id: string; status: string };
type DataAccount = { can_manage: boolean; deletion_request: DeletionRequest | null };

export default function WorkspaceDataSettings() {
  const sectionRef = useRef<HTMLElement>(null);
  const didScroll = useRef(false);
  const [account, setAccount] = useState<DataAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!didScroll.current && window.location.hash === '#workspace-data') {
      sectionRef.current?.scrollIntoView({ block: 'start' });
      didScroll.current = true;
    }
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    api<DataAccount>('/commercial/account')
      .then((result) => {
        if (active) setAccount(result);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadAttempt]);

  async function requestDeletion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      busy ||
      !account?.can_manage ||
      account.deletion_request ||
      confirmation !== 'УДАЛИТЬ' ||
      !consent
    )
      return;
    setBusy(true);
    setError('');
    try {
      const request = await post<DeletionRequest>('/commercial/deletion-request', {
        confirmation,
        consent,
      });
      setAccount((current) => (current ? { ...current, deletion_request: request } : current));
      setConfirming(false);
      setConfirmation('');
      setConsent(false);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function closeConfirmation() {
    setConfirming(false);
    setConfirmation('');
    setConsent(false);
    setError('');
  }

  return (
    <section
      ref={sectionRef}
      id="workspace-data"
      className="workspace-data"
      aria-labelledby="workspace-data-title"
    >
      <div className="workspace-data-heading">
        <h2 id="workspace-data-title">Данные организации</h2>
        <p>
          Запрос на удаление данных рабочего пространства проверяем вручную. Перед удалением
          подтвердим полномочия и обязательные сроки хранения.
        </p>
      </div>
      {error && (
        <p className="workspace-data-error" role="alert">
          {error}
        </p>
      )}
      {loading ? (
        <p role="status">Загружаем сведения о данных организации…</p>
      ) : !account ? (
        <button
          type="button"
          className="workspace-data-secondary"
          onClick={() => setLoadAttempt((value) => value + 1)}
        >
          Повторить загрузку
        </button>
      ) : account.deletion_request ? (
        <div className="workspace-data-status" role="status">
          <p>Запрос на удаление зарегистрирован. Свяжемся с вами для уточнения объёма удаления.</p>
          <p>
            Номер запроса: <strong>{account.deletion_request.id}</strong>
          </p>
        </div>
      ) : !account.can_manage ? (
        <p>
          Отправить запрос на удаление может только администратор организации. Обратитесь к нему для
          управления данными рабочего пространства.
        </p>
      ) : confirming ? (
        <form
          className="workspace-data-form"
          onSubmit={requestDeletion}
          aria-label="Запрос на удаление данных"
        >
          <label className="workspace-data-field" htmlFor="workspace-data-confirmation">
            Введите УДАЛИТЬ
          </label>
          <input
            id="workspace-data-confirmation"
            name="confirmation"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            pattern="УДАЛИТЬ"
            required
            autoComplete="off"
            autoFocus
            disabled={busy}
          />
          <label className="workspace-data-consent">
            <input
              name="consent"
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
              required
              disabled={busy}
            />
            <span>Подтверждаю отправку запроса от имени организации</span>
          </label>
          <div className="workspace-data-actions">
            <button
              className="workspace-data-primary"
              disabled={busy || confirmation !== 'УДАЛИТЬ' || !consent}
            >
              {busy ? 'Отправляем запрос…' : 'Отправить запрос'}
            </button>
            <button
              type="button"
              className="workspace-data-secondary"
              onClick={closeConfirmation}
              disabled={busy}
            >
              Вернуться
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          className="workspace-data-secondary"
          onClick={() => setConfirming(true)}
        >
          Запросить удаление данных
        </button>
      )}
      <a className="workspace-data-policy" href="/data-request">
        Как рассматриваются запросы по данным
      </a>
    </section>
  );
}
