import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { api, del, post } from '../../api';
import { t } from '../../i18n';
import type { Notify } from './types';

type Column = { key: string; label: string };
type Member = { id: string; name: string };
type Schedule = {
  id: string;
  name: string;
  columns: string[];
  weekdays: number[];
  month_day: number | null;
  hour: number;
  last_sent_on: string | null;
  last_status: string;
};
const days = [t('Пн'), t('Вт'), t('Ср'), t('Чт'), t('Пт'), t('Сб'), t('Вс')];
const blank = {
  name: '',
  stage: '',
  weekdays: [4] as number[],
  monthDay: '',
  hour: '15',
  columns: ['name', 'inn', 'stage', 'status', 'balance', 'days'],
  recipients: [] as string[],
};

export function ReportSchedules({ notify }: { notify: Notify }) {
  const [items, setItems] = useState<Schedule[]>([]);
  const [mailReady, setMailReady] = useState(true);
  const [columns, setColumns] = useState<Column[]>([]);
  const [team, setTeam] = useState<Member[]>([]);
  const [form, setForm] = useState<typeof blank | null>(null);
  const load = useCallback(
    () =>
      api<{ items: Schedule[]; mail_ready: boolean }>('/recovery/report-schedules')
        .then((result) => {
          setItems(result.items);
          setMailReady(result.mail_ready);
        })
        .catch((error) => notify(error.message, true)),
    [notify]
  );
  useEffect(() => {
    void load();
    api<{ items: Column[] }>('/recovery/report/columns').then((result) => setColumns(result.items));
    api<{ members: Member[] }>('/workflow/team').then((result) => setTeam(result.members));
  }, [load]);
  const toggle = <T,>(list: T[], value: T) =>
    list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  function submit(event: FormEvent) {
    event.preventDefault();
    const data = form!;
    post('/recovery/report-schedules', {
      name: data.name,
      stage: data.stage,
      weekdays: data.weekdays,
      month_day: data.monthDay ? Number(data.monthDay) : null,
      hour: Number(data.hour),
      columns: data.columns,
      recipients: data.recipients,
    })
      .then(() => {
        setForm(null);
        notify(t('Расписание сохранено'));
        return load();
      })
      .catch((error) => notify(error.message, true));
  }
  return (
    <section className="rc-card">
      <div className="rc-card-head">
        <h2>{t('Отчёты по расписанию')}</h2>
        {!form && (
          <button
            className="button button-outline"
            disabled={team.length === 0}
            onClick={() => setForm({ ...blank, recipients: team.slice(0, 1).map((m) => m.id) })}
          >
            {t('Новое расписание')}
          </button>
        )}
      </div>
      {!mailReady && (
        <p className="rc-note">{t('Почта сервиса пока не настроена: отчёты не будут уходить.')}</p>
      )}
      <ul className="rc-documents">
        {items.map((row) => (
          <li key={row.id}>
            <span>
              <strong>{row.name}</strong> · {row.weekdays.map((day) => days[day]).join(', ')}
              {row.month_day ? ` · ${t('{0} число', [row.month_day])}` : ''} · {row.hour}:00
              {row.last_status && <small>{`${row.last_sent_on}: ${t(row.last_status)}`}</small>}
            </span>
            <button
              className="wf-text-button"
              onClick={() =>
                void del(`/recovery/report-schedules/${row.id}`)
                  .then(load)
                  .catch((error) => notify(error.message, true))
              }
            >
              {t('Удалить')}
            </button>
          </li>
        ))}
      </ul>
      {form && (
        <form className="rc-settings" onSubmit={submit}>
          <div className="rc-grid">
            <label>
              {t('Название')}
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label>
              {t('Час отправки')}
              <input
                type="number"
                min={0}
                max={23}
                value={form.hour}
                onChange={(e) => setForm({ ...form, hour: e.target.value })}
              />
            </label>
            <label>
              {t('Число месяца (необязательно)')}
              <input
                type="number"
                min={1}
                max={28}
                value={form.monthDay}
                onChange={(e) => setForm({ ...form, monthDay: e.target.value })}
              />
            </label>
          </div>
          <div className="rc-weekdays">
            {days.map((label, index) => (
              <label key={label} className="rc-check">
                <input
                  type="checkbox"
                  checked={form.weekdays.includes(index)}
                  onChange={() => setForm({ ...form, weekdays: toggle(form.weekdays, index) })}
                />
                {label}
              </label>
            ))}
          </div>
          <h3>{t('Кому')}</h3>
          <div className="rc-report-columns">
            {team.map((member) => (
              <label key={member.id} className="rc-check">
                <input
                  type="checkbox"
                  checked={form.recipients.includes(member.id)}
                  onChange={() =>
                    setForm({ ...form, recipients: toggle(form.recipients, member.id) })
                  }
                />
                {member.name}
              </label>
            ))}
          </div>
          <h3>{t('Колонки')}</h3>
          <div className="rc-report-columns">
            {columns.map((column) => (
              <label key={column.key} className="rc-check">
                <input
                  type="checkbox"
                  checked={form.columns.includes(column.key)}
                  onChange={() => setForm({ ...form, columns: toggle(form.columns, column.key) })}
                />
                {t(column.label)}
              </label>
            ))}
          </div>
          <div className="rc-action-buttons">
            <button className="button button-dark">{t('Сохранить')}</button>
            <button type="button" className="button button-outline" onClick={() => setForm(null)}>
              {t('Отмена')}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
