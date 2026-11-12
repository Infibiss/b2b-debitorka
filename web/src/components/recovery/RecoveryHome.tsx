import { useEffect, useState } from 'react';
import { ArrowUpRight, Check, ChevronRight, SlidersHorizontal } from 'lucide-react';
import { api, dateText, money } from '../../api';
import { t } from '../../i18n';
import type { Dashboard, Notify, Stage } from './types';
import { HomeCharts } from './HomeCharts';
import { OrganizationsSummary } from './Organizations';

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
  const [editing, setEditing] = useState(false);
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
  const empty = data.totals.debtors === 0;
  return (
    <div className="rc-page">
      <header className="rc-head">
        <h1>{t('Главная')}</h1>
        <div className="rc-head-actions">
          <button
            className={`button button-outline ${editing ? 'rc-filter-on' : ''}`}
            hidden={empty}
            aria-pressed={editing}
            onClick={() => setEditing(!editing)}
          >
            <SlidersHorizontal size={15} aria-hidden="true" />
            {editing ? t('Готово') : t('Настроить графики')}
          </button>
          {!empty && (
            <button className="button button-dark" onClick={onImport}>
              {t('Загрузить должников')}
            </button>
          )}
        </div>
      </header>

      {empty && (
        <section className="rc-welcome">
          <div>
            <h2>{t('Начните с реестра должников')}</h2>
            <p>
              {t(
                'Загрузите Excel или выгрузку из 1С: контрагент, ИНН, номер счёта, срок оплаты и сумма. Mandato разложит долги по этапам и подскажет, с кого начать.'
              )}
            </p>
          </div>
          <button className="button button-dark" onClick={onImport}>
            {t('Загрузить должников')}
          </button>
        </section>
      )}

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
              ? t('оплат пока не было')
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

      <HomeCharts editing={editing} notify={notify} refreshKey={refreshKey} />

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
          {data.deadlines.length === 0 && (
            <p className="rc-muted">{t('В ближайшие 30 дней сроков нет.')}</p>
          )}
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
      )}
      <OrganizationsSummary refreshKey={refreshKey} />
    </div>
  );
}
