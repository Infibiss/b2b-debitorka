import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Copy, Phone, Settings } from 'lucide-react';
import { api, post } from '../api';
import { DeskError } from './OperationsUI';

type Telephony = {
  ready: boolean;
  status: string;
  provider: string | null;
  message: string;
  setup_steps: string[];
};
type Readiness = { speech_configured: boolean; telephony: Telephony };
type Preparation = Readiness & {
  status: string;
  call_started: false;
  phone: string;
  opening: string;
  next_action: string;
};

export function VoiceCallPanel({ invoiceId }: { invoiceId: string }) {
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [phone, setPhone] = useState('');
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [preparation, setPreparation] = useState<Preparation | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const setup = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    let alive = true;
    api<Readiness>('/yandex/voice/readiness')
      .then((result) => {
        if (alive) setReadiness(result);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);
  function resetPreparation() {
    setPreparation(null);
    setNotice('');
    setError('');
  }
  async function prepare(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setPreparation(null);
    try {
      const result = await post<Preparation>('/yandex/voice/calls/prepare', {
        invoice_id: invoiceId,
        phone,
        contact_authorized: authorized,
      });
      setPreparation(result);
      setReadiness(result);
      if (result.next_action === 'configure_telephony') {
        setSetupOpen(true);
        requestAnimationFrame(() =>
          setup.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function copySetup() {
    if (!readiness) return;
    const request = [
      'Mandato · подключение исходящих голосовых звонков',
      readiness.telephony.message,
      ...readiness.telephony.setup_steps.map((step, index) => `${index + 1}. ${step}`),
      'SpeechKit: ' +
        (readiness.speech_configured
          ? 'настройки речи присутствуют; доступ отдельно проверяется'
          : 'требуются ключ, права и привязка организации'),
      'Секреты передаются администратору по защищённому каналу. Это задание не разрешает покупку услуг или исходящие звонки.',
    ].join('\n');
    try {
      await navigator.clipboard.writeText(request);
      setNotice('Задание на подключение скопировано');
    } catch {
      setNotice('Буфер обмена недоступен. Передайте администратору шаги ниже');
    }
  }
  return (
    <section className="yx-card" aria-labelledby="yx-voice-title">
      <div className="yx-title">
        <Phone size={22} />
        <h2 id="yx-voice-title">Звонок по счёту</h2>
      </div>
      <p>Агент уточнит причину задержки и дату оплаты. Спорные вопросы передаст сотруднику.</p>
      <DeskError>{error}</DeskError>
      <form className="yx-text-form" onSubmit={(event) => void prepare(event)}>
        <label className="field">
          Телефон контрагента
          <input
            type="tel"
            autoComplete="tel"
            required
            maxLength={40}
            value={phone}
            placeholder="+7 999 123-45-67"
            disabled={busy}
            onChange={(event) => {
              setPhone(event.target.value);
              resetPreparation();
            }}
          />
        </label>
        <label className="yx-identity">
          <input
            type="checkbox"
            checked={authorized}
            disabled={busy}
            onChange={(event) => {
              setAuthorized(event.target.checked);
              resetPreparation();
            }}
          />
          Номер принадлежит представителю контрагента, полномочия на контакт проверены
        </label>
        {!invoiceId && <p className="yx-callout">Выберите счёт, чтобы подготовить звонок</p>}
        <div className="yx-actions">
          <button
            className="button button-dark"
            disabled={busy || !invoiceId || !phone.trim() || !authorized}
          >
            <Phone size={16} />
            {busy ? 'Проверяем звонок…' : 'Позвонить'}
          </button>
          <button
            type="button"
            className="button button-outline"
            onClick={() => setSetupOpen(true)}
          >
            <Settings size={16} />
            Настройки телефонии
          </button>
        </div>
      </form>
      <div className="yx-connection yx-connection-missing" role="status">
        <strong>
          {readiness
            ? readiness.telephony.ready
              ? 'Соединение доступно'
              : 'Нужно подключить телефонию'
            : 'Проверяем соединение…'}
        </strong>
        <span>{readiness?.telephony.message || 'Ожидаем подтверждение настроек сервера'}</span>
      </div>
      {preparation && (
        <div className="yx-callout" role="status">
          <strong>
            {preparation.status === 'connection_required'
              ? 'Звонок не начат'
              : 'Подготовка завершена'}
          </strong>
          <p>
            Номер {preparation.phone}: формат проверен. По счёту нет запрета на контакт.
            Принадлежность номера подтверждена сотрудником, соединение ещё не проверено.
          </p>
          <p>
            {preparation.status === 'connection_required'
              ? 'Для продолжения выполните настройку телефонии ниже'
              : 'Запуск требует отдельного подтверждения и повторной проверки условий'}
          </p>
        </div>
      )}
      <details
        className="yx-note"
        ref={setup}
        open={setupOpen}
        onToggle={(event) => setSetupOpen(event.currentTarget.open)}
      >
        <summary>Подключение телефонии</summary>
        <p>
          Для подключения потребуются исходящий номер и доступ к телефонии вашей организации.
          Передайте настройки её администратору.
        </p>
        {readiness && (
          <ol>
            {readiness.telephony.setup_steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        )}
        <p>
          Обработка речи:{' '}
          {readiness
            ? readiness.speech_configured
              ? 'настройки присутствуют; доступ проверяется отдельно'
              : 'нужны ключ SpeechKit, права на распознавание и озвучивание и привязка организации'
            : 'статус ещё не получен'}
        </p>
        <p>Секреты передаются администратору по защищённому каналу. Здесь они не запрашиваются.</p>
        <button
          type="button"
          className="button button-outline"
          disabled={!readiness}
          onClick={() => void copySetup()}
        >
          <Copy size={16} />
          Скопировать задание на подключение
        </button>
        <p role="status">{notice}</p>
      </details>
      <details className="yx-note">
        <summary>Ход разговора и результат</summary>
        <ol>
          <li>Представиться и проверить полномочия собеседника до раскрытия сведений счёта</li>
          <li>Уточнить причину задержки и согласовать точные сумму и дату</li>
          <li>Сохранить ответ для проверки сотрудником; заявление об оплате направить на сверку</li>
          <li>Передать спор или просьбу о сотруднике ответственному</li>
        </ol>
        <p>
          Звонки и стенограммы появятся после подключения телефонии. Обещание оплаты и разговор сами
          по себе не меняют финансовый учёт.
        </p>
      </details>
    </section>
  );
}
