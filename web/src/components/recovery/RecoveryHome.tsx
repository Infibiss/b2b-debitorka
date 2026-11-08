import { useEffect, useState } from 'react';
import { Check, ChevronRight } from 'lucide-react';
import { api, dateText, money } from '../../api';
import { t } from '../../i18n';
import type { Dashboard, Notify, Stage } from './types';

export const stageNames: Record<Stage, string> = {
  pretrial: t('Досудебная работа'),
  court: t('Суд'),
  enforcement: t('Исполнение'),
  closed: t('Закрыто'),
};

export function RecoveryHome({
  onOpenDebtor,
  onGo,
  onImport,
  refreshKey,
  notify,
}: {
  onOpenDebtor: (id: string) => void;
  onGo: (target: string) => void;
  onImport: () => void;
  refreshKey: number;
  notify: Notify;
}) {
  const [data, setData] = useState<Dashboard | null>(null);
  useEffect(() => {
    api<Dashboard>('/recovery/dashboard')
      .then(setData)
      .catch((error) => notify(error.message, true));
  }, [refreshKey, notify]);
  if (!data) return <div className="rc-empty">{t('Загружаем…')}</div>;
  const setupDone = data.onboarding.done === data.onboarding.total;
  return (
    <div className="rc-page">
      <header className="rc-head">
        <div>
          <h1>{t('Главная')}</h1>
          <p>{t('Что сделать сегодня, чтобы деньги пришли быстрее.')}</p>
        </div>
        <button className="button button-dark" onClick={onImport}>
          {t('Загрузить должников')}
        </button>
      </header>

      <section className="rc-kpis" aria-label={t('Сводка')}>
        <div>
          <span>{t('В работе')}</span>
          <strong>{money(data.totals.balance, true)}</strong>
          <small>{t('{0} должников', [data.totals.debtors])}</small>
        </div>
        <div>
          <span>{t('Просрочено')}</span>
          <strong>{money(data.totals.overdue, true)}</strong>
        </div>
        <div>
          <span>{t('Обещано оплатить')}</span>
          <strong>{money(data.totals.promised, true)}</strong>
        </div>
      </section>

      {!setupDone && (
        <section className="rc-card">
          <h2>{t('Настройка: {0} из {1}', [data.onboarding.done, data.onboarding.total])}</h2>
          <ol className="rc-setup">
            {data.onboarding.items.map((item) => (
              <li key={item.key} className={item.done ? 'is-done' : ''}>
                <span className="rc-setup-mark">{item.done && <Check size={14} />}</span>
                <div>
                  <strong>{t(item.label)}</strong>
                  <small>{t(item.hint)}</small>
                </div>
                {!item.done && (
                  <button className="wf-text-button" onClick={() => onGo(item.target)}>
                    {t('Сделать')}
                  </button>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="rc-pipeline" aria-label={t('Этапы')}>
        {data.stages.map((item) => (
          <button key={item.stage} onClick={() => onGo(`debtors:${item.stage}`)}>
            <span>{stageNames[item.stage]}</span>
            <strong>{item.count}</strong>
            <small>{money(item.amount, true)}</small>
          </button>
        ))}
      </section>

      <div className="rc-columns">
        <section className="rc-card">
          <h2>{t('Задачи на сегодня: {0}', [data.task_count])}</h2>
          {data.tasks.length === 0 && (
            <p className="rc-muted">{t('Срочных задач нет. Загрузите должников, чтобы начать.')}</p>
          )}
          <ul className="rc-tasks">
            {data.tasks.map((item) => (
              <li key={item.id}>
                <button onClick={() => onOpenDebtor(item.id)}>
                  <div>
                    <strong>{item.name}</strong>
                    <small>{t(item.next_step?.reason ?? '')}</small>
                  </div>
                  <span className="rc-task-amount">{money(item.balance, true)}</span>
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className="rc-card">
          <h2>{t('Ближайшие сроки')}</h2>
          {data.deadlines.length === 0 && <p className="rc-muted">{t('Горящих сроков нет.')}</p>}
          <ul className="rc-deadlines">
            {data.deadlines.map((item) => (
              <li key={`${item.debtor_id}-${item.key}`}>
                <button onClick={() => onOpenDebtor(item.debtor_id)}>
                  <strong>{item.name}</strong>
                  <small>
                    {t(item.label)} · {dateText(item.on)}
                  </small>
                </button>
                <span className={item.days_left <= 7 ? 'rc-chip rc-chip-danger' : 'rc-chip'}>
                  {t('{0} дн.', [item.days_left])}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
