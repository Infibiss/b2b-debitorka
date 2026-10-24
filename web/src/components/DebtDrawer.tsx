import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import {
  X,
  ArrowUpRight,
  Mail,
  Clock3,
  Plus,
  Check,
  FileText,
  Pause,
  AlertCircle,
  Play,
  Send,
  ShieldCheck,
  ChevronDown,
  CheckCheck,
  Download,
  Pencil,
} from 'lucide-react';
import {
  api,
  post,
  patch,
  money,
  dateText,
  today,
  toKopeks,
  type Detail,
  type Invoice,
  type Message,
} from '../api';
import { Dialog } from './Dialog';
import { useDialogFocus } from './useDialogFocus';
export const statusNames: Record<Invoice['status'], string> = {
  open: 'В работе',
  promised: 'Обещание',
  disputed: 'Спор',
  paid: 'Оплачен',
  paused: 'На паузе',
};
export const statusColors: Record<Invoice['status'], string> = {
  open: 'gray',
  promised: 'orange',
  disputed: 'red',
  paid: 'green',
  paused: 'gray',
};
export function DebtDrawer({
  id,
  onClose,
  onChange,
  notify,
}: {
  id: string;
  onClose: () => void;
  onChange: () => void;
  notify: (s: string, error?: boolean) => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [action, setAction] = useState<'promise' | 'payment' | 'contact' | null>(null),
    [tone, setTone] = useState('soft'),
    [selectedMsg, setSelectedMsg] = useState<Message | null>(null);
  const load = useCallback(async () => {
    try {
      setDetail(await api<Detail>(`/invoices/${id}`));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);
  const drawerRef = useRef<HTMLElement>(null);
  useDialogFocus(drawerRef, onClose);
  async function draft() {
    setBusy(true);
    try {
      const msg = await post<Message>(`/invoices/${id}/draft`, { tone });
      setSelectedMsg(msg);
      await load();
      onChange();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function status(value: string) {
    setBusy(true);
    try {
      await post(`/invoices/${id}/status`, { status: value });
      await load();
      onChange();
      notify(
        value === 'disputed'
          ? 'Работа по спорному счёту приостановлена'
          : value === 'paused'
            ? 'Счёт поставлен на паузу'
            : 'Счёт возвращён в работу'
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const inv = detail?.invoice;
  const canContact = inv && inv.balance > 0 && !['disputed', 'paused'].includes(inv.status);
  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside
        ref={drawerRef}
        className="debt-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Карточка счёта"
      >
        <div className="drawer-top">
          <span>
            <FileText size={16} />
            КАРТОЧКА СЧЁТА
          </span>
          <button className="icon-button" onClick={onClose} aria-label="Закрыть карточку">
            <X size={20} />
          </button>
        </div>
        {error ? (
          <div className="empty-state">
            <p className="form-error">{error}</p>
            <button onClick={() => void load()} className="button button-dark">
              Повторить
            </button>
          </div>
        ) : !detail || !inv ? (
          <div className="loading">
            <div className="spinner" />
            Открываем счёт…
          </div>
        ) : (
          <>
            <div className="drawer-main">
              <div className="drawer-invoice-head">
                <span className={`pill ${statusColors[inv.status]}`}>
                  {statusNames[inv.status]}
                </span>
                <span className="drawer-ref">{inv.number}</span>
              </div>
              <h2>{inv.company}</h2>
              <p className="drawer-company">
                {inv.inn ? `ИНН ${inv.inn}` : 'Реквизиты не указаны'}{' '}
                {inv.email && <>· {inv.email}</>}
              </p>
              <button className="drawer-contact-edit" onClick={() => setAction('contact')}>
                Изменить контакт и заметку
                <Pencil size={12} />
              </button>
              {inv.notes && <div className="invoice-notes">{inv.notes}</div>}
              <div className="drawer-balance">
                <span>Осталось к оплате</span>
                <strong>{money(inv.balance)}</strong>
                <div>
                  <span>Сумма счёта {money(inv.amount)}</span>
                  {inv.paid_amount > 0 && (
                    <span className="paid-amount">
                      <Check size={12} />
                      {money(inv.paid_amount)} оплачено
                    </span>
                  )}
                </div>
              </div>
              <div className="invoice-facts">
                <div>
                  <span>Дата счёта</span>
                  <strong>{dateText(inv.issued_on)}</strong>
                </div>
                <div>
                  <span>Оплатить до</span>
                  <strong>{dateText(inv.due_on)}</strong>
                </div>
                <div>
                  <span>{inv.days_overdue > 0 ? 'Просрочка' : 'Срок'}</span>
                  <strong className={inv.days_overdue > 0 && inv.balance > 0 ? 'overdue' : ''}>
                    {inv.balance === 0
                      ? 'Закрыт'
                      : inv.days_overdue > 0
                        ? `${inv.days_overdue} дн.`
                        : 'Не наступил'}
                  </strong>
                </div>
              </div>
              {inv.promise_date && inv.balance > 0 && (
                <div className="promise-banner">
                  <Clock3 size={17} />
                  <div>
                    <strong>Обещание оплаты · {dateText(inv.promise_date)}</strong>
                    <span>Ожидаем {money(inv.balance)} по договорённости</span>
                  </div>
                </div>
              )}
              {inv.priority_reasons.length > 0 && inv.balance > 0 && (
                <div className="priority-reasons">
                  <span>ПОЧЕМУ В ПРИОРИТЕТЕ</span>
                  {inv.priority_reasons.map((r) => (
                    <p key={r}>
                      <i />
                      {r}
                    </p>
                  ))}
                </div>
              )}
              <div className="drawer-actions">
                <button
                  className="button button-dark"
                  onClick={() => void draft()}
                  disabled={busy || !canContact}
                >
                  Подготовить письмо
                  <Mail size={16} />
                </button>
                <button
                  className="button button-outline"
                  onClick={() => setAction('payment')}
                  disabled={inv.balance === 0}
                >
                  Внести оплату
                  <Plus size={16} />
                </button>
                <button
                  className="button button-subtle"
                  onClick={() => setAction('promise')}
                  disabled={!canContact}
                >
                  Обещание оплаты
                  <Clock3 size={15} />
                </button>
                <div className="tone-select">
                  <select
                    aria-label="Тон письма"
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                  >
                    <option value="soft">Мягкое напоминание</option>
                    <option value="firm">Деловое напоминание</option>
                  </select>
                  <ChevronDown size={13} />
                </div>
              </div>
              {!canContact && inv.balance > 0 && (
                <p className="drawer-notice">
                  <Pause size={14} />
                  Подготовка писем приостановлена до возврата счёта в работу.
                </p>
              )}
              <div className="drawer-section-title">
                <h3>Переписка</h3>
                <span>{detail.messages.length}</span>
              </div>
              {selectedMsg && (
                <MessageEditor
                  key={selectedMsg.id}
                  message={selectedMsg}
                  onChange={async (m) => {
                    setSelectedMsg(m);
                    await load();
                    onChange();
                  }}
                  notify={notify}
                />
              )}
              <div className="message-list">
                {detail.messages.length === 0 ? (
                  <p className="quiet-empty">Здесь появятся подготовленные письма покупателю.</p>
                ) : (
                  detail.messages
                    .filter((m) => m.id !== selectedMsg?.id)
                    .map((msg) => (
                      <button
                        key={msg.id}
                        className="message-item"
                        onClick={() => setSelectedMsg(msg)}
                      >
                        <Mail size={15} />
                        <span>
                          <strong>{msg.subject}</strong>
                          <small>
                            {dateText(msg.created_at)} · {msg.recipient || 'Получатель не указан'}
                          </small>
                        </span>
                        <span className={`pill ${msg.status === 'sent' ? 'green' : 'gray'}`}>
                          {msg.status === 'sent'
                            ? 'Отправлено'
                            : msg.status === 'approved'
                              ? 'Согласовано'
                              : msg.status === 'failed'
                                ? 'Ошибка'
                                : 'Черновик'}
                        </span>
                        <ArrowUpRight size={14} />
                      </button>
                    ))
                )}
              </div>
              <div className="drawer-section-title">
                <h3>История работы</h3>
                <span>{detail.events.length}</span>
              </div>
              <div className="event-list">
                {detail.events.map((event, i) => (
                  <div className="event" key={event.id}>
                    <div className={`event-dot ${i === 0 ? 'recent' : ''}`}>
                      <Check size={10} />
                    </div>
                    <div>
                      <strong>{event.title}</strong>
                      <p>{event.detail}</p>
                      <small>
                        {dateText(event.created_at)} ·{' '}
                        {new Date(event.created_at).toLocaleTimeString('ru-RU', {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </small>
                    </div>
                  </div>
                ))}
              </div>
              {inv.balance > 0 && (
                <div className="status-actions">
                  {inv.status === 'paused' || inv.status === 'disputed' ? (
                    <button onClick={() => void status('open')} disabled={busy}>
                      <Play size={14} />
                      Вернуть в работу
                    </button>
                  ) : (
                    <>
                      <button onClick={() => void status('paused')} disabled={busy}>
                        <Pause size={14} />
                        Поставить на паузу
                      </button>
                      <button onClick={() => void status('disputed')} disabled={busy}>
                        <AlertCircle size={14} />
                        Отметить спор
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}
        {action === 'contact' && inv && (
          <ContactForm
            invoice={inv}
            onClose={() => setAction(null)}
            onDone={async () => {
              setAction(null);
              setSelectedMsg(null);
              await load();
              onChange();
              notify('Контакт и заметка сохранены');
            }}
          />
        )}
        {action && action !== 'contact' && inv && (
          <PaymentPromise
            kind={action}
            invoice={inv}
            onClose={() => setAction(null)}
            onDone={async () => {
              setAction(null);
              setSelectedMsg(null);
              await load();
              onChange();
              notify(action === 'payment' ? 'Поступление записано' : 'Обещание оплаты сохранено');
            }}
          />
        )}
      </aside>
    </div>
  );
}
function MessageEditor({
  message,
  onChange,
  notify,
}: {
  message: Message;
  onChange: (m: Message) => Promise<void>;
  notify: (s: string, e?: boolean) => void;
}) {
  const [subject, setSubject] = useState(message.subject),
    [body, setBody] = useState(message.body),
    [busy, setBusy] = useState(false);
  const dirty = subject !== message.subject || body !== message.body;
  const sent = message.status === 'sent';
  async function approve() {
    setBusy(true);
    try {
      if (dirty) await patch(`/messages/${message.id}`, { subject, body });
      const m = await post<Message>(`/messages/${message.id}/approve`);
      await onChange(m);
      notify('Письмо согласовано');
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function send() {
    setBusy(true);
    try {
      const m = await post<Message>(`/messages/${message.id}/send`);
      await onChange(m);
      notify('Письмо принято почтовым сервером');
    } catch (e) {
      notify((e as Error).message, true);
      try {
        const d = await api<Detail>(`/invoices/${message.invoice_id}`);
        const current = d.messages.find((m) => m.id === message.id);
        if (current) await onChange(current);
      } catch {
        /* preserve original error */
      }
    } finally {
      setBusy(false);
    }
  }
  function download() {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(
      new Blob([`${subject}\n\n${body}`], { type: 'text/plain;charset=utf-8' })
    );
    a.download = 'mandato-letter.txt';
    a.click();
    URL.revokeObjectURL(a.href);
  }
  return (
    <section className="message-editor">
      <div className="editor-header">
        <Mail size={15} />
        <span>{sent ? 'Отправленное письмо' : 'Письмо покупателю'}</span>
        <span className={`pill ${message.status === 'approved' ? 'green' : 'gray'}`}>
          {sent
            ? 'Отправлено'
            : message.status === 'approved' && !dirty
              ? 'Согласовано'
              : 'Черновик'}
        </span>
      </div>
      <p className="editor-to">
        Кому: <strong>{message.recipient || 'Укажите email в счёте'}</strong>
      </p>
      <label className="field">
        Тема
        <input
          aria-label="Тема письма"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          readOnly={sent}
          maxLength={250}
        />
      </label>
      <label className="field">
        Текст письма
        <textarea
          aria-label="Текст письма"
          rows={9}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          readOnly={sent}
          maxLength={10000}
        />
      </label>
      <p className="editor-source">
        <ShieldCheck size={12} />
        {message.source === 'yandex'
          ? 'Текст подготовлен с ИИ. Суммы подставлены из счёта.'
          : 'Суммы и сроки подставлены из счёта. Проверьте текст.'}
      </p>
      <div className="editor-actions">
        {!sent && (message.status !== 'approved' || dirty) ? (
          <button
            className="button button-dark"
            disabled={busy || !subject.trim() || !body.trim()}
            onClick={() => void approve()}
          >
            Согласовать письмо
            <CheckCheck size={16} />
          </button>
        ) : !sent ? (
          <button className="button button-dark" disabled={busy} onClick={() => void send()}>
            Отправить письмо
            <Send size={15} />
          </button>
        ) : null}
        <button
          className="icon-button"
          aria-label="Скачать письмо"
          title="Скачать письмо"
          onClick={download}
        >
          <Download size={17} />
        </button>
      </div>
      <p className="editor-safety">Отправка доступна после подключения почты администратором.</p>
    </section>
  );
}
function PaymentPromise({
  kind,
  invoice,
  onClose,
  onDone,
}: {
  kind: 'payment' | 'promise';
  invoice: Invoice;
  onClose: () => void;
  onDone: () => void;
}) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setBusy(true);
    const data = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await post(
        `/invoices/${invoice.id}/${kind === 'payment' ? 'payments' : 'promise'}`,
        kind === 'payment'
          ? { ...data, amount: toKopeks(String(data.amount)) }
          : { date: data.date }
      );
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={kind === 'payment' ? 'Поступление денег' : 'Обещание оплаты'} onClose={onClose}>
      <p className="dialog-intro">
        {invoice.company} · {invoice.number}
        <br />
        Остаток: <strong>{money(invoice.balance)}</strong>
      </p>
      <form className="form-grid" onSubmit={submit}>
        {kind === 'payment' ? (
          <>
            <label className="field full-width">
              Сумма оплаты
              <input
                required
                inputMode="decimal"
                name="amount"
                defaultValue={String(invoice.balance / 100)}
                pattern="[0-9]+([,.][0-9]{1,2})?"
              />
            </label>
            <label className="field">
              Дата поступления
              <input required type="date" name="paid_on" defaultValue={today()} max={today()} />
            </label>
            <label className="field">
              Номер платежа
              <input required name="reference" placeholder="ПП-284" maxLength={100} />
            </label>
            <p className="form-note full-width">
              Укажите номер из выписки. Повторный платёж с тем же номером не будет учтён дважды.
            </p>
          </>
        ) : (
          <>
            <label className="field full-width">
              Дата оплаты
              <input required type="date" name="date" min={today()} defaultValue={today()} />
            </label>
            <p className="form-note full-width">
              Сохраним договорённость и покажем, когда наступит обещанная дата.
            </p>
          </>
        )}
        {error && (
          <p className="form-error full-width" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions full-width">
          <button className="button button-outline" type="button" onClick={onClose}>
            Отмена
          </button>
          <button className="button button-dark" disabled={busy} type="submit">
            {kind === 'payment' ? 'Записать оплату' : 'Сохранить обещание'}
            <Check size={16} />
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function ContactForm({
  invoice,
  onClose,
  onDone,
}: {
  invoice: Invoice;
  onClose: () => void;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setBusy(true);
    const data = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await patch(`/invoices/${invoice.id}/contact`, data);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Контакт и заметка" onClose={onClose}>
      <p className="dialog-intro">
        {invoice.company} · {invoice.number}
      </p>
      <form onSubmit={submit} className="form-grid">
        <label className="field full-width">
          Email покупателя
          <input type="email" name="email" defaultValue={invoice.email} maxLength={254} />
        </label>
        <label className="field full-width">
          Заметка по счёту
          <textarea
            name="notes"
            rows={5}
            maxLength={5000}
            defaultValue={invoice.notes}
            placeholder="Контекст договорённости, нужные документы или следующий шаг"
          />
        </label>
        <p className="form-note full-width">
          Изменения сохранятся в истории. После смены адреса подготовьте письмо заново.
        </p>
        {error && (
          <p className="form-error full-width" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions full-width">
          <button className="button button-outline" type="button" onClick={onClose}>
            Отмена
          </button>
          <button className="button button-dark" type="submit" disabled={busy}>
            Сохранить контакт
            <Check size={16} />
          </button>
        </div>
      </form>
    </Dialog>
  );
}
