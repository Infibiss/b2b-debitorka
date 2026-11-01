import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { FileCheck2, Mic, Square, Upload, Volume2 } from 'lucide-react';
import { api, post, type Invoice } from '../api';
import { DeskError, DeskHeading } from './OperationsUI';
import './yandex.css';

type ServiceStatus = {
  configured: boolean;
  status: string;
  message: string;
  required_roles: string[];
};
type Status = { ocr: ServiceStatus; voice: ServiceStatus };
type DocumentResult = {
  id: string;
  filename: string;
  invoice_id: string | null;
  status: string;
  error_code: string;
  text: string;
  page_count: number;
  source_hash: string;
  acceptance: { text: string; fields: Record<string, string>; reason: string } | null;
};
type VoiceTurn = {
  id: string;
  status: string;
  transcript: string;
  reply: string;
  audio: string;
  audio_mime: string;
  error_code: string;
  intent_source?: string;
  opening?: boolean;
  handoff_required?: boolean;
};
export type YandexDeskProps = {
  invoices: Invoice[];
  notify: (text: string, error?: boolean) => void;
  invoiceId?: string;
  mode?: 'all' | 'ocr' | 'voice';
};
const labels: Record<string, string> = {
  unconfigured: 'Нужно подключение',
  not_checked: 'Права ещё не проверены',
  completed: 'Последний запрос выполнен',
  processing: 'Запрос выполняется',
  unavailable: 'Последний запрос не выполнен',
  permission_required: 'Нужны права Яндекса',
};
const errors: Record<string, string> = {
  permission: 'Нет доступа к сервису. Обратитесь к администратору Mandato.',
  authentication: 'Подключение к Яндексу не работает. Обратитесь к администратору Mandato.',
  rate_limit: 'Достигнут лимит сервиса. Попробуйте позже или обратитесь к администратору Mandato.',
  timeout: 'Яндекс не ответил вовремя. Результат запроса не подтверждён.',
  speech_not_recognized: 'Речь не распознана. Запишите новую короткую реплику или введите текст.',
  invalid_response: 'Ответ Яндекса не прошёл проверку. Результат не подтверждён.',
};
function message(code: string) {
  return errors[code] || 'Не удалось завершить обработку. Попробуйте позже.';
}
function base64(bytes: Uint8Array) {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}
/** Resample mono input to raw PCM16LE. The server accepts at most 20 seconds. */
function pcm16(chunks: Float32Array[], rate: number) {
  const input = new Float32Array(chunks.reduce((n, a) => n + a.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    input.set(chunk, offset);
    offset += chunk.length;
  }
  const count = Math.min(320000, Math.floor((input.length * 16000) / rate));
  const output = new Uint8Array(count * 2),
    view = new DataView(output.buffer);
  for (let i = 0; i < count; i++) {
    const start = Math.floor((i * rate) / 16000),
      end = Math.max(start + 1, Math.floor(((i + 1) * rate) / 16000));
    let value = 0;
    for (let j = start; j < end && j < input.length; j++) value += input[j];
    value = Math.max(-1, Math.min(1, value / (end - start)));
    view.setInt16(i * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
  }
  return output;
}
function TurnAudio({ turn, autoplay }: { turn: VoiceTurn; autoplay: boolean }) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    if (!turn.audio) return;
    const raw = atob(turn.audio),
      bytes = Uint8Array.from(raw, (c) => c.charCodeAt(0));
    const next = URL.createObjectURL(new Blob([bytes], { type: turn.audio_mime }));
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [turn.audio, turn.audio_mime]);
  return url ? (
    <audio
      className="yx-audio"
      controls
      autoPlay={autoplay}
      preload="metadata"
      src={url}
      aria-label="Ответ Mandato голосом"
    >
      Ваш браузер не поддерживает аудио OggOpus.
    </audio>
  ) : null;
}

type Recording = {
  stream: MediaStream;
  context: AudioContext;
  source: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode;
  gain: GainNode;
  chunks: Float32Array[];
  samples: number;
  timer: ReturnType<typeof setTimeout>;
  clock: ReturnType<typeof setInterval>;
};

export function YandexDesk({ invoices, notify, invoiceId, mode = 'all' }: YandexDeskProps) {
  const [status, setStatus] = useState<Status | null>(null),
    [documents, setDocuments] = useState<DocumentResult[]>([]);
  const [selectedInvoice, setSelectedInvoice] = useState(invoiceId || ''),
    [document, setDocument] = useState<DocumentResult | null>(null);
  const [text, setText] = useState(''),
    [number, setNumber] = useState(''),
    [reason, setReason] = useState('');
  const [turns, setTurns] = useState<VoiceTurn[]>([]),
    [typed, setTyped] = useState('');
  const [spokenId, setSpokenId] = useState('');
  const [identityConfirmed, setIdentityConfirmed] = useState(false);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(''),
    [recording, setRecording] = useState(false),
    [seconds, setSeconds] = useState(0);
  const recorder = useRef<Recording | null>(null),
    mounted = useRef(true),
    generation = useRef(0);
  const stopRef = useRef<() => void>(() => {});
  const micPending = useRef(false);

  const reload = useCallback(async () => {
    const [nextStatus, nextDocuments] = await Promise.all([
      api<Status>('/yandex/status'),
      api<{ items: DocumentResult[] }>('/yandex/documents'),
    ]);
    if (mounted.current) {
      setStatus(nextStatus);
      setDocuments(nextDocuments.items);
    }
  }, []);
  function cleanup() {
    const active = recorder.current;
    recorder.current = null;
    if (active) {
      clearTimeout(active.timer);
      clearInterval(active.clock);
      active.processor.onaudioprocess = null;
      active.source.disconnect();
      active.processor.disconnect();
      active.gain.disconnect();
      active.stream.getTracks().forEach((track) => track.stop());
      void active.context.close().catch(() => {});
    }
    return active;
  }
  useEffect(() => {
    mounted.current = true;
    void reload().catch((e: Error) => {
      if (mounted.current) setError(e.message);
    });
    return () => {
      mounted.current = false;
      generation.current++;
      cleanup();
    };
  }, [reload]);
  useEffect(() => {
    if (invoiceId) setSelectedInvoice(invoiceId);
  }, [invoiceId]);
  useEffect(() => {
    let current = true;
    setTurns([]);
    if (selectedInvoice)
      void api<{ items: VoiceTurn[] }>(
        `/yandex/voice/turns?invoice_id=${encodeURIComponent(selectedInvoice)}`
      )
        .then((result) => {
          if (current) setTurns(result.items);
        })
        .catch((e: Error) => {
          if (current) setError(e.message);
        });
    return () => {
      current = false;
    };
  }, [selectedInvoice]);
  function review(item: DocumentResult) {
    setDocument(item);
    setText(item.acceptance?.text ?? item.text);
    setNumber(item.acceptance?.fields.number ?? '');
    setReason(item.acceptance?.reason ?? '');
  }
  async function upload(file?: File) {
    if (!file) return;
    setError('');
    if (
      file.size > 1000000 ||
      !['application/pdf', 'image/png', 'image/jpeg'].includes(file.type)
    ) {
      setError('Выберите PDF, PNG или JPEG до 1 МБ. В PDF допускается до пяти страниц.');
      return;
    }
    setBusy('document');
    try {
      const result = await post<DocumentResult>('/yandex/documents', {
        content: base64(new Uint8Array(await file.arrayBuffer())),
        mime_type: file.type,
        filename: file.name,
        invoice_id: selectedInvoice || null,
      });
      review(result);
      await reload();
      if (result.status === 'completed') notify('Текст распознан. Сверьте его с оригиналом.');
      else
        setError(
          result.status === 'processing'
            ? 'Запрос уже выполняется или его исход уточняется. Сохранённый запрос повторно не отправляется.'
            : message(result.error_code)
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  async function accept(event: FormEvent) {
    event.preventDefault();
    if (!document) return;
    setBusy('accept');
    setError('');
    try {
      const result = await post<DocumentResult>(`/yandex/documents/${document.id}/accept`, {
        text,
        fields: number.trim() ? { number: number.trim() } : {},
        reason,
      });
      review(result);
      await reload();
      notify('Проверенная версия сохранена в документах дела.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  async function sendTurn(
    body: { audio?: string; text?: string; opening?: boolean },
    invoice: string
  ) {
    setBusy('voice');
    setError('');
    const epoch = generation.current;
    try {
      const result = await post<VoiceTurn>(
        body.opening
          ? '/yandex/voice/opening'
          : body.audio
            ? '/yandex/voice/turn'
            : '/yandex/voice/text',
        {
          ...body,
          opening: undefined,
          identity_confirmed: identityConfirmed,
          invoice_id: invoice,
          request_id: crypto.randomUUID(),
        }
      );
      if (!mounted.current || epoch !== generation.current) return;
      setTurns((previous) => [...previous, result].slice(-20));
      setSpokenId(result.id);
      setTyped('');
      if (result.status !== 'completed') setError(message(result.error_code));
      await reload();
    } catch (e) {
      if (mounted.current && epoch === generation.current) setError((e as Error).message);
    } finally {
      if (mounted.current && epoch === generation.current) setBusy('');
    }
  }
  async function stop() {
    const active = cleanup();
    if (mounted.current) setRecording(false);
    if (!active || !mounted.current) return;
    const bytes = pcm16(active.chunks, active.context.sampleRate);
    if (bytes.length < 3200) {
      setError('Запись слишком короткая. Произнесите реплику и остановите запись.');
      return;
    }
    await sendTurn({ audio: base64(bytes) }, selectedInvoice);
  }
  stopRef.current = () => {
    void stop();
  };
  async function start() {
    if (recorder.current || micPending.current || !selectedInvoice) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
      setError('Микрофон недоступен. Откройте сайт по HTTPS или введите реплику ниже.');
      return;
    }
    setError('');
    setBusy('microphone');
    micPending.current = true;
    const epoch = generation.current;
    let stream: MediaStream | undefined, context: AudioContext | undefined;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        video: false,
      });
      if (!mounted.current || epoch !== generation.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      context = new AudioContext();
      await context.resume();
      if (!mounted.current || epoch !== generation.current) {
        stream.getTracks().forEach((track) => track.stop());
        await context.close();
        return;
      }
      const source = context.createMediaStreamSource(stream),
        processor = context.createScriptProcessor(4096, 1, 1),
        gain = context.createGain();
      gain.gain.value = 0;
      const active: Recording = {
        stream,
        context,
        source,
        processor,
        gain,
        chunks: [],
        samples: 0,
        timer: setTimeout(() => stopRef.current(), 20000),
        clock: setInterval(() => setSeconds((n) => Math.min(20, n + 1)), 1000),
      };
      recorder.current = active;
      processor.onaudioprocess = (event) => {
        if (recorder.current !== active) return;
        const input = event.inputBuffer.getChannelData(0),
          remaining = Math.max(0, Math.floor(active.context.sampleRate * 20) - active.samples);
        if (remaining) {
          const chunk = input.slice(0, remaining);
          active.chunks.push(chunk);
          active.samples += chunk.length;
        }
      };
      source.connect(processor);
      processor.connect(gain);
      gain.connect(context.destination);
      setSeconds(0);
      setRecording(true);
    } catch (e) {
      cleanup();
      stream?.getTracks().forEach((track) => track.stop());
      if (context && context.state !== 'closed') void context.close().catch(() => {});
      if (mounted.current)
        setError(
          (e as DOMException).name === 'NotAllowedError'
            ? 'Доступ к микрофону не разрешён. Измените разрешение браузера или введите текст.'
            : 'Не удалось включить микрофон. Проверьте устройство или введите текст.'
        );
    } finally {
      micPending.current = false;
      if (mounted.current) setBusy('');
    }
  }
  function changeInvoice(value: string) {
    generation.current++;
    cleanup();
    setRecording(false);
    setSelectedInvoice(value);
    setIdentityConfirmed(false);
    setError('');
  }
  return (
    <div className={`yx-desk yx-mode-${mode}`}>
      <DeskHeading
        eyebrow="РАБОТА СО СЧЁТОМ"
        title={
          mode === 'ocr'
            ? 'Распознавание документов'
            : mode === 'voice'
              ? 'Учебный разговор'
              : 'Документы и разговор'
        }
      >
        {mode === 'ocr'
          ? 'Извлеките текст из скана и проверьте результат перед использованием.'
          : 'Демонстрация разговора об оплате. Действия по долгу требуют отдельного подтверждения.'}
      </DeskHeading>
      <DeskError>{error}</DeskError>
      <label className="field yx-invoice">
        Счёт для документов и диалога
        <select
          value={selectedInvoice}
          onChange={(e) => changeInvoice(e.target.value)}
          disabled={!!busy || recording}
        >
          <option value="">Без привязки к счёту</option>
          {invoices.map((invoice) => (
            <option key={invoice.id} value={invoice.id}>
              {invoice.company} · № {invoice.number}
            </option>
          ))}
        </select>
      </label>
      <div className="yx-columns">
        {mode !== 'voice' && (
          <section className="yx-card" aria-labelledby="yx-documents-title">
            <div className="yx-title">
              <FileCheck2 size={22} />
              <h2 id="yx-documents-title">Документы</h2>
            </div>
            <Connection status={status?.ocr} />
            <p>
              Загрузите договор, акт или счёт. Поддерживаются PDF до пяти страниц, PNG и JPEG до 1
              МБ.
            </p>
            <label
              className={`button button-outline yx-upload ${!status?.ocr.configured || busy ? 'yx-disabled' : ''}`}
            >
              <Upload size={16} />
              {busy === 'document' ? 'Распознаём…' : 'Выбрать документ'}
              <input
                aria-label="Загрузить документ для распознавания"
                type="file"
                accept="application/pdf,image/png,image/jpeg"
                disabled={!status?.ocr.configured || !!busy || recording}
                onChange={(event) => {
                  void upload(event.target.files?.[0]);
                  event.target.value = '';
                }}
              />
            </label>
            <details className="yx-note">
              <summary>Лимит распознавания</summary>
              <p>
                10 страниц в день на сотрудника и 20 на компанию. Неудачные запросы тоже
                учитываются.
              </p>
            </details>
            <ul className="yx-documents">
              {documents
                .filter((item) => !selectedInvoice || item.invoice_id === selectedInvoice)
                .map((item) => (
                  <li key={item.id}>
                    <button className="yx-document-link" onClick={() => review(item)}>
                      {item.filename}
                      <small>
                        {item.acceptance
                          ? 'Проверен человеком'
                          : labels[item.status] || item.status}{' '}
                        · {item.page_count} стр.
                      </small>
                    </button>
                  </li>
                ))}
            </ul>
          </section>
        )}
        {mode !== 'ocr' && (
          <section className="yx-card" aria-labelledby="yx-voice-title">
            <div className="yx-title">
              <Volume2 size={22} />
              <h2 id="yx-voice-title">Разговор по счёту</h2>
            </div>
            <Connection status={status?.voice} />
            <p>
              Ответьте от лица контрагента: Mandato уточнит причину задержки и предложит обсудить
              срок оплаты. Можно говорить или писать.
            </p>
            <p className="yx-note">
              Разговор проходит в браузере, без звонка контрагенту. Запись до 20 секунд
              обрабатывается Яндексом. Итоги сохраняются в стенограмме; долг и условия оплаты не
              меняются.
            </p>
            {!selectedInvoice && (
              <p className="yx-callout">Выберите счёт выше, чтобы начать диалог.</p>
            )}
            <label className="yx-identity">
              <input
                type="checkbox"
                checked={identityConfirmed}
                disabled={!selectedInvoice || !!busy || recording}
                onChange={(event) => setIdentityConfirmed(event.target.checked)}
              />
              Разрешаю использовать сведения выбранного счёта в учебном разговоре от лица
              контрагента.
            </label>
            <div className="yx-actions">
              <button
                type="button"
                className="button button-outline"
                disabled={!selectedInvoice || !status?.voice.configured || !!busy || recording}
                onClick={() => void sendTurn({ opening: true }, selectedInvoice)}
              >
                Начать разговор
              </button>
              <button
                type="button"
                className={`button ${recording ? 'button-dark yx-recording' : 'button-outline'}`}
                disabled={!selectedInvoice || !status?.voice.configured || (!!busy && !recording)}
                onClick={() => (recording ? stopRef.current() : void start())}
              >
                {recording ? (
                  <>
                    <Square size={16} />
                    Остановить и отправить · {seconds} с
                  </>
                ) : (
                  <>
                    <Mic size={16} />
                    {busy === 'microphone' ? 'Включаем микрофон…' : 'Начать запись'}
                  </>
                )}
              </button>
              {recording && (
                <button
                  type="button"
                  className="button button-outline"
                  onClick={() => {
                    cleanup();
                    setRecording(false);
                  }}
                >
                  Отменить запись
                </button>
              )}
            </div>
            <span role="status" aria-live="polite" className="yx-live">
              {recording
                ? 'Микрофон включён. Запись автоматически остановится через 20 секунд.'
                : busy === 'voice'
                  ? 'Mandato обрабатывает реплику…'
                  : ''}
            </span>
            <form
              className="yx-text-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (typed.trim()) void sendTurn({ text: typed.trim() }, selectedInvoice);
              }}
            >
              <label className="field">
                Или введите реплику
                <textarea
                  maxLength={1000}
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  placeholder="Например: оплатим счёт в пятницу"
                  disabled={!!busy || recording}
                />
              </label>
              <button
                className="button button-outline"
                disabled={
                  !typed.trim() ||
                  !selectedInvoice ||
                  !status?.voice.configured ||
                  !!busy ||
                  recording
                }
              >
                Ответить Mandato
              </button>
            </form>
            <p className="yx-note">До 10 реплик в день на сотрудника и 20 на компанию.</p>
            <ol className="yx-transcript" aria-label="История диалога">
              {turns.map((turn, index) => (
                <li key={turn.id}>
                  {!turn.opening && (
                    <>
                      <span className="yx-turn-label">Вы · {index + 1}</span>
                      <p>{turn.transcript || 'Речь не распознана'}</p>
                    </>
                  )}
                  <span className="yx-turn-label">Mandato</span>
                  <p>{turn.reply || message(turn.error_code)}</p>
                  <TurnAudio turn={turn} autoplay={turn.id === spokenId} />
                  {turn.handoff_required && (
                    <p className="yx-callout">
                      Нужен разбор сотрудником. Запрос сохранён в стенограмме; действия в деле
                      требуют отдельного рассмотрения.
                    </p>
                  )}
                  {turn.status !== 'completed' && turn.reply && (
                    <p role="status" className="yx-warning">
                      Озвучивание не завершено: {message(turn.error_code)}
                    </p>
                  )}
                  {turn.intent_source === 'rules_fallback' && (
                    <small>Модель недоступна. Ответ составлен по правилам разговора.</small>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
      {document && (
        <section className="yx-card yx-review" aria-labelledby="yx-review-title">
          <div className="yx-title">
            <h2 id="yx-review-title">Проверка: {document.filename}</h2>
            <a
              className="button button-outline"
              href={`/api/yandex/documents/${document.id}/original`}
              download
            >
              Скачать оригинал
            </a>
          </div>
          <p className="yx-note">
            {document.page_count} стр. Сверьте текст и реквизиты с оригиналом. Сохранение документа
            не меняет сумму долга.
          </p>
          {document.status !== 'completed' && (
            <p className="yx-warning">
              {document.status === 'processing'
                ? 'Распознавание ещё не завершено. Откройте документ позже.'
                : message(document.error_code)}
            </p>
          )}
          <form onSubmit={(event) => void accept(event)}>
            <label className="field">
              Распознанный текст — исправьте ошибки
              <textarea
                className="yx-ocr-text"
                value={text}
                maxLength={30000}
                readOnly={!!document.acceptance}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <div className="yx-review-fields">
              <label className="field">
                Проверенный номер документа
                <input
                  value={number}
                  maxLength={1000}
                  readOnly={!!document.acceptance}
                  onChange={(e) => setNumber(e.target.value)}
                />
              </label>
              <label className="field">
                Что проверено по оригиналу
                <input
                  required
                  value={reason}
                  maxLength={1000}
                  readOnly={!!document.acceptance}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
            </div>
            {document.acceptance ? (
              <p role="status">Проверенная версия сохранена.</p>
            ) : (
              <button
                className="button button-dark"
                disabled={!!busy || document.status !== 'completed' || !reason.trim()}
              >
                Сохранить проверенную версию
              </button>
            )}
          </form>
        </section>
      )}
    </div>
  );
}
function Connection({ status }: { status?: ServiceStatus }) {
  if (!status)
    return (
      <p className="yx-connection" role="status">
        Проверяем настройки подключения…
      </p>
    );
  return (
    <div className={`yx-connection ${status.configured ? '' : 'yx-connection-missing'}`}>
      <strong>{labels[status.status] || status.status}</strong>
      <span>
        {status.status === 'unconfigured'
          ? 'Для работы нужно подключить сервис. Обратитесь к администратору Mandato.'
          : status.status === 'not_checked'
            ? 'Подключение будет проверено при первом запросе.'
            : status.status === 'permission_required'
              ? 'Нужно проверить доступ к сервису. Обратитесь к администратору Mandato.'
              : status.status === 'processing'
                ? 'Обработка запроса ещё не завершена.'
                : status.status === 'unavailable'
                  ? 'Обработка не завершена. Попробуйте позже.'
                  : status.status === 'completed'
                    ? 'Последний запрос обработан успешно.'
                    : status.message}
      </span>
      {['unconfigured', 'permission_required'].includes(status.status) &&
        status.required_roles.length > 0 && (
          <details>
            <summary>Настройки для администратора</summary>
            <small>Роли в Yandex Cloud: {status.required_roles.join(', ')}</small>
          </details>
        )}
    </div>
  );
}
