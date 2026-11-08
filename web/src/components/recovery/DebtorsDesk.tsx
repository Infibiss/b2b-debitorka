import { useEffect, useMemo, useState } from 'react';
import { Download, Search, Upload } from 'lucide-react';
import { api, money, post } from '../../api';
import { t } from '../../i18n';
import { stageNames } from './RecoveryHome';
import type { Debtor, Notify, Stage } from './types';

const stages: Stage[] = ['pretrial', 'court', 'enforcement', 'closed'];

export function DebtorsDesk({
  initialStage,
  onOpen,
  onImport,
  onCreate,
  refreshKey,
  notify,
}: {
  initialStage: Stage;
  onOpen: (id: string) => void;
  onImport: () => void;
  onCreate: () => void;
  refreshKey: number;
  notify: Notify;
}) {
  const [items, setItems] = useState<Debtor[] | null>(null);
  const [stage, setStage] = useState<Stage>(initialStage);
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const load = () =>
    api<{ items: Debtor[] }>('/recovery/debtors')
      .then((result) => setItems(result.items))
      .catch((error) => notify(error.message, true));
  useEffect(() => {
    void load();
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setStage(initialStage), [initialStage]);
  const statuses = useMemo(() => {
    const found = new Map<string, string>();
    (items ?? [])
      .filter((i) => i.stage === stage)
      .forEach((i) => found.set(i.status, i.status_label));
    return [...found];
  }, [items, stage]);
  if (!items) return <div className="rc-empty">{t('Загружаем…')}</div>;
  const needle = query.trim().toLowerCase();
  const visible = items.filter(
    (item) =>
      item.stage === stage &&
      (!status || item.status === status) &&
      (!needle || item.name.toLowerCase().includes(needle) || item.inn.includes(needle))
  );
  async function bulk(action: 'start' | 'prepare_claim') {
    setBusy(true);
    try {
      const result = await post<{ done: number; items: { ok: boolean; error?: string }[] }>(
        '/recovery/debtors/bulk',
        { ids: selected, action }
      );
      const failed = result.items.find((row) => !row.ok);
      notify(
        failed
          ? t('Выполнено: {0}. Не удалось: {1}', [result.done, failed.error])
          : t('Выполнено: {0}', [result.done]),
        Boolean(failed)
      );
      setSelected([]);
      await load();
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const allChecked = visible.length > 0 && visible.every((item) => selected.includes(item.id));
  return (
    <div className="rc-page">
      <header className="rc-head">
        <div>
          <h1>{t('Должники')}</h1>
          <p>{t('Каждый должник проходит три этапа. Система подсказывает следующий шаг.')}</p>
        </div>
        <div className="rc-head-actions">
          <a className="button button-outline" href="/api/recovery/report.csv">
            <Download size={15} />
            {t('Выгрузить')}
          </a>
          <button className="button button-outline" onClick={onCreate}>
            {t('Добавить счёт')}
          </button>
          <button className="button button-dark" onClick={onImport}>
            <Upload size={15} />
            {t('Загрузить реестр')}
          </button>
        </div>
      </header>
      <nav className="rc-stage-tabs" aria-label={t('Этапы')}>
        {stages.map((key) => (
          <button
            key={key}
            className={stage === key ? 'active' : ''}
            aria-current={stage === key ? 'page' : undefined}
            onClick={() => {
              setStage(key);
              setStatus('');
              setSelected([]);
            }}
          >
            {stageNames[key]}
            <span>{items.filter((i) => i.stage === key).length}</span>
          </button>
        ))}
      </nav>
      <div className="rc-toolbar">
        <label className="rc-search">
          <Search size={15} aria-hidden="true" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('Название или ИНН')}
            aria-label={t('Поиск должника')}
          />
        </label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label={t('Фильтр по статусу')}
        >
          <option value="">{t('Все статусы')}</option>
          {statuses.map(([key, label]) => (
            <option key={key} value={key}>
              {t(label)}
            </option>
          ))}
        </select>
        {selected.length > 0 && stage === 'pretrial' && (
          <div className="rc-bulk">
            <span>{t('Выбрано: {0}', [selected.length])}</span>
            <button
              className="button button-outline"
              disabled={busy}
              onClick={() => void bulk('start')}
            >
              {t('Начать работу')}
            </button>
            <button
              className="button button-outline"
              disabled={busy}
              onClick={() => void bulk('prepare_claim')}
            >
              {t('Подготовить претензии')}
            </button>
          </div>
        )}
      </div>
      {visible.length === 0 ? (
        <div className="rc-empty">
          {items.length === 0
            ? t('Пока нет должников. Загрузите реестр в Excel, и система разложит долги по этапам.')
            : t('На этом этапе никого нет.')}
        </div>
      ) : (
        <div className="rc-table-wrap">
          <table className="rc-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label={t('Выбрать всех')}
                    checked={allChecked}
                    onChange={() => setSelected(allChecked ? [] : visible.map((i) => i.id))}
                  />
                </th>
                <th>{t('Должник')}</th>
                <th>{t('Статус')}</th>
                <th className="rc-num">{t('Остаток')}</th>
                <th className="rc-num">{t('Просрочка')}</th>
                <th>{t('Документы')}</th>
                <th>{t('Следующий шаг')}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={t('Выбрать {0}', [item.name])}
                      checked={selected.includes(item.id)}
                      onChange={() =>
                        setSelected((old) =>
                          old.includes(item.id)
                            ? old.filter((x) => x !== item.id)
                            : [...old, item.id]
                        )
                      }
                    />
                  </td>
                  <td>
                    <button className="rc-link" onClick={() => onOpen(item.id)}>
                      {item.name}
                    </button>
                    <small>{item.inn ? t('ИНН {0}', [item.inn]) : t('ИНН не указан')}</small>
                  </td>
                  <td>
                    <span className={`rc-status rc-status-${item.next_step?.urgency ?? 'closed'}`}>
                      {t(item.status_label)}
                    </span>
                    {item.custom_status && <small>{item.custom_status}</small>}
                  </td>
                  <td className="rc-num">{money(item.balance, true)}</td>
                  <td className="rc-num">{t('{0} дн.', [item.days_overdue])}</td>
                  <td>
                    <span
                      className={item.evidence_score < 100 ? 'rc-chip rc-chip-warn' : 'rc-chip'}
                    >
                      {item.evidence_score}%
                    </span>
                  </td>
                  <td className="rc-next">{t(item.next_step?.label || 'Ожидание')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
