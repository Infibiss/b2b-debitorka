import { useEffect, useState } from 'react';
import { ArrowUpRight, Check, ChevronRight } from 'lucide-react';
import { api, dateText, money } from '../../api';
import { language, t } from '../../i18n';
import type { Analytics, Dashboard, Notify, Stage } from './types';
import { BoardsBar } from './CustomDashboard';
import { OrganizationsSummary } from './Organizations';

export const stageNames: Record<Stage, string> = {
  pretrial: t('Досудебная работа'),
  court: t('Суд'),
  enforcement: t('Исполнение'),
  closed: t('Закрыто'),
};

const monthName = (key: string) =>
  new Date(`${key}-15`).toLocaleDateString(language === 'en' ? 'en-GB' : 'ru-RU', {
    month: 'short',
  });

function AgingChart({ rows }: { rows: Analytics['aging'] }) {
  const max = Math.max(...rows.map((row) => row.amount), 1);
  return (
    <ul className="rc-aging" aria-label={t('Долг по сроку просрочки')}>
      {rows.map((row, index) => (
        <li key={row.key} title={t('Счетов: {0}', [row.count])}>
          <span>{t(row.label)}</span>
          <div className="rc-aging-track">
            <i
              data-step={index}
              style={{ width: row.amount ? `max(4px, ${(row.amount / max) * 100}%)` : 0 }}
            />
          </div>
          <strong>{money(row.amount, true)}</strong>
        </li>
      ))}
    </ul>
  );
}

function MonthlyChart({ rows }: { rows: Analytics['monthly'] }) {
  const max = Math.max(...rows.map((row) => row.amount), 1);
  const empty = rows.every((row) => row.amount === 0);
  if (empty)
    return (
      <p className="rc-muted">{t('Поступлений пока нет. График появится после первой оплаты.')}</p>
    );
  return (
    <>
      <div className="rc-columns-chart" role="img" aria-label={t('Поступления за 12 месяцев')}>
        {rows.map((row) => (
          <div key={row.month} className="rc-col" tabIndex={0}>
            <span className="rc-col-tip">
              {monthName(row.month)}: {money(row.amount, true)}
            </span>
            <i style={{ height: row.amount ? `max(4px, ${(row.amount / max) * 100}%)` : 0 }} />
            <small>{monthName(row.month)}</small>
          </div>
        ))}
      </div>
      <table className="rc-visually-hidden">
        <caption>{t('Поступления за 12 месяцев')}</caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.month}>
              <th>{row.month}</th>
              <td>{money(row.amount, true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

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
  const [board, setBoard] = useState('');
  useEffect(() => {
    api<Dashboard>('/recovery/dashboard')
      .then(setData)
      .catch((error) => notify(error.message, true));
  }, [refreshKey, notify]);
  if (!data) return <div className="rc-empty">{t('Загружаем…')}</div>;
  const setupDone = data.onboarding.done === data.onboarding.total;
  const insight = data.analytics;
  const attention = insight.attention.filter((item) => item.count > 0);
  const change = insight.collected_this_month - insight.collected_last_month;
  return (
    <div className="rc-page">
      <header className="rc-head">
        <h1>{t('Главная')}</h1>
        <button className="button button-dark" onClick={onImport}>
          {t('Загрузить должников')}
        </button>
      </header>

      <BoardsBar selected={board} onSelect={setBoard} notify={notify} refreshKey={refreshKey} />

      <div className="rc-page" style={board ? { display: 'none' } : undefined}>
        <section className="rc-kpis" aria-label={t('Сводка')}>
          <div className="rc-kpi-hero">
            <span>{t('В работе')}</span>
            <strong>{money(data.totals.balance, true)}</strong>
            <small>{t('{0} должников', [data.totals.debtors])}</small>
          </div>
          <div>
            <span>{t('Просрочено')}</span>
            <strong>{money(data.totals.overdue, true)}</strong>
            <small>{t('в среднем {0} дн.', [insight.average_overdue_days])}</small>
          </div>
          <div>
            <span>{t('Обещано оплатить')}</span>
            <strong>{money(data.totals.promised, true)}</strong>
            <small>{t('за 30 дней: {0}', [money(insight.promised_30_days, true)])}</small>
          </div>
          <div>
            <span>{t('Получено в этом месяце')}</span>
            <strong>{money(insight.collected_this_month, true)}</strong>
            <small>
              {change === 0
                ? t('как в прошлом месяце')
                : t('{0} к прошлому месяцу', [
                    `${change > 0 ? '+' : '−'}${money(Math.abs(change), true)}`,
                  ])}
            </small>
          </div>
        </section>

        {!setupDone && (
          <details className="rc-card rc-setup-card">
            <summary>
              <strong>
                {t('Настройка: {0} из {1}', [data.onboarding.done, data.onboarding.total])}
              </strong>
              <span>{t(data.onboarding.items.find((item) => !item.done)?.label ?? '')}</span>
            </summary>
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
          </details>
        )}

        {attention.length > 0 && (
          <section className="rc-attention" aria-label={t('Требует внимания')}>
            {attention.map((item) => (
              <button key={item.key} onClick={() => onGo(item.target)}>
                <strong>{item.count}</strong>
                <span>{t(item.label)}</span>
                <ArrowUpRight size={15} aria-hidden="true" />
              </button>
            ))}
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
            <h2>{t('Долг по сроку просрочки')}</h2>
            <AgingChart rows={insight.aging} />
          </section>
          <section className="rc-card">
            <h2>{t('Поступления за 12 месяцев')}</h2>
            <MonthlyChart rows={insight.monthly} />
            <p className="rc-chart-foot">
              {t('Всего получено {0} · возвращено {1}%', [
                money(insight.collected_total, true),
                insight.recovery_percent,
              ])}
            </p>
          </section>
        </div>

        <div className="rc-columns">
          <section className="rc-card">
            <h2>{t('Задачи на сегодня: {0}', [data.task_count])}</h2>
            {data.tasks.length === 0 && <p className="rc-muted">{t('Срочных задач нет.')}</p>}
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

        {insight.top.length > 0 && (
          <div className="rc-columns">
            <section className="rc-card">
              <h2>{t('Крупнейшие должники')}</h2>
              <ul className="rc-tasks">
                {insight.top.map((item) => (
                  <li key={item.id}>
                    <button onClick={() => onOpenDebtor(item.id)}>
                      <div>
                        <strong>{item.name}</strong>
                        <small>
                          {t(item.status_label)} · {t('{0} дн.', [item.days_overdue])}
                        </small>
                      </div>
                      <span className="rc-task-amount">{money(item.balance, true)}</span>
                      <ChevronRight size={16} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
            <section className="rc-card">
              <h2>{t('По статусам')}</h2>
              <table className="rc-table rc-table-plain">
                <tbody>
                  {insight.statuses.map((row) => (
                    <tr key={row.status}>
                      <td>{t(row.label)}</td>
                      <td className="rc-num">{row.count}</td>
                      <td className="rc-num">{money(row.amount, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        )}
        <OrganizationsSummary refreshKey={refreshKey} />
      </div>
    </div>
  );
}
