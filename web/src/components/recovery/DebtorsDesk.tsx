import { useEffect, useMemo, useState } from 'react';
import { Download, Search, SlidersHorizontal, Upload } from 'lucide-react';
import { api, money, post } from '../../api';
import { t } from '../../i18n';
import { stageNames } from './RecoveryHome';
import type { Debtor, Meta, Notify, Stage } from './types';

type View = Stage | 'archive';
const views: View[] = ['pretrial', 'court', 'enforcement', 'closed', 'archive'];
type Filters = {
  status: string;
  assignee: string;
  amountFrom: string;
  amountTo: string;
  daysFrom: string;
  daysTo: string;
  contact: string;
  documents: string;
  paused: boolean;
};
const emptyFilters: Filters = {
  status: '',
  assignee: '',
  amountFrom: '',
  amountTo: '',
  daysFrom: '',
  daysTo: '',
  contact: '',
  documents: '',
  paused: false,
};
const optionalColumns = [
  ['documents', t('Документы')],
  ['assignee', t('Ответственный')],
  ['case', t('Дело')],
  ['next', t('Следующий шаг')],
] as const;
type ColumnKey = (typeof optionalColumns)[number][0];
const COLUMNS_KEY = 'mandato-debtor-columns';

function savedColumns(): ColumnKey[] {
  try {
    const value = JSON.parse(localStorage.getItem(COLUMNS_KEY) ?? 'null');
    if (Array.isArray(value)) return value;
  } catch {
    /* the default set still works */
  }
  return ['documents', 'next'];
}

function matches(item: Debtor, f: Filters) {
  const rubles = item.balance / 100;
  return (
    (!f.status || item.status === f.status) &&
    (!f.assignee || item.assignee_id === f.assignee) &&
    (!f.amountFrom || rubles >= Number(f.amountFrom)) &&
    (!f.amountTo || rubles <= Number(f.amountTo)) &&
    (!f.daysFrom || item.days_overdue >= Number(f.daysFrom)) &&
    (!f.daysTo || item.days_overdue <= Number(f.daysTo)) &&
    (!f.contact ||
      (f.contact === 'none'
        ? !item.email && !item.phone
        : f.contact === 'phone'
          ? Boolean(item.phone)
          : Boolean(item.email))) &&
    (!f.documents ||
      (f.documents === 'ready' ? item.evidence_score === 100 : item.evidence_score < 100)) &&
    (!f.paused || item.hold)
  );
}

export function DebtorsDesk({
  initialStage,
  meta,
  isManager,
  onOpen,
  onImport,
  onCreate,
  refreshKey,
  notify,
}: {
  initialStage: Stage;
  meta: Meta | null;
  isManager: boolean;
  onOpen: (id: string) => void;
  onImport: () => void;
  onCreate: () => void;
  refreshKey: number;
  notify: Notify;
}) {
  const [items, setItems] = useState<Debtor[] | null>(null);
  const [team, setTeam] = useState<{ id: string; name: string }[]>([]);
  const [view, setView] = useState<View>(initialStage);
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [columns, setColumns] = useState<ColumnKey[]>(savedColumns);
  const load = () =>
    api<{ items: Debtor[] }>('/recovery/debtors')
      .then((result) => setItems(result.items))
      .catch((error) => notify(error.message, true));
  useEffect(() => {
    void load();
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api<{ members: { id: string; name: string }[] }>('/workflow/team')
      .then((result) => setTeam(result.members))
      .catch(() => setTeam([]));
  }, []);
  useEffect(() => setView(initialStage), [initialStage]);
  const inView = (item: Debtor, key: View) =>
    key === 'archive' ? item.archived : !item.archived && item.stage === key;
  const statuses = useMemo(() => {
    const found = new Map<string, string>();
    (items ?? [])
      .filter((i) => inView(i, view))
      .forEach((i) => found.set(i.status, i.status_label));
    return [...found];
  }, [items, view]);
  if (!items) return <div className="rc-empty">{t('Загружаем…')}</div>;
  const needle = query.trim().toLowerCase();
  const visible = items.filter(
    (item) =>
      inView(item, view) &&
      matches(item, filters) &&
      (!needle ||
        [
          item.name,
          item.inn,
          item.contract,
          item.case_number,
          item.writ_number,
          item.email,
          item.phone,
        ]
          .join(' ')
          .toLowerCase()
          .includes(needle))
  );
  const activeFilters = Object.values(filters).filter(Boolean).length;
  const total = visible.reduce((sum, item) => sum + item.balance, 0);
  const nameOf = (id: string | null) => team.find((member) => member.id === id)?.name ?? '';
  const stageKinds = Object.entries(meta?.document_kinds ?? {}).filter(
    ([, kind]) => kind.stage === view
  );
  async function bulk(action: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    try {
      const result = await post<{ done: number; items: { ok: boolean; error?: string }[] }>(
        '/recovery/debtors/bulk',
        { ids: selected, action, ...extra }
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
  function toggleColumn(key: ColumnKey) {
    const next = columns.includes(key) ? columns.filter((c) => c !== key) : [...columns, key];
    setColumns(next);
    try {
      localStorage.setItem(COLUMNS_KEY, JSON.stringify(next));
    } catch {
      /* applies to this visit only */
    }
  }
  const show = (key: ColumnKey) => columns.includes(key);
  const field = (key: keyof Filters) => ({
    value: filters[key] as string,
    onChange: (e: { target: { value: string } }) =>
      setFilters({ ...filters, [key]: e.target.value }),
  });
  const allChecked = visible.length > 0 && visible.every((item) => selected.includes(item.id));
  return (
    <div className="rc-page">
      <header className="rc-head">
        <h1>{t('Должники')}</h1>
        <div className="rc-head-actions">
          {view === 'court' && (
            <a className="button button-outline" href="/api/recovery/duty-register.csv">
              <Download size={15} />
              {t('Реестр пошлин')}
            </a>
          )}
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
        {views.map((key) => (
          <button
            key={key}
            className={view === key ? 'active' : ''}
            aria-current={view === key ? 'page' : undefined}
            onClick={() => {
              setView(key);
              setFilters(emptyFilters);
              setSelected([]);
            }}
          >
            {key === 'archive' ? t('Архив') : stageNames[key]}
            <span>{items.filter((i) => inView(i, key)).length}</span>
          </button>
        ))}
      </nav>
      <div className="rc-toolbar">
        <label className="rc-search">
          <Search size={15} aria-hidden="true" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('Название, ИНН, договор, номер дела')}
            aria-label={t('Поиск должника')}
          />
        </label>
        <button
          className={`button button-outline ${activeFilters ? 'rc-filter-on' : ''}`}
          aria-expanded={filtersOpen}
          onClick={() => setFiltersOpen(!filtersOpen)}
        >
          <SlidersHorizontal size={15} />
          {activeFilters ? t('Фильтры: {0}', [activeFilters]) : t('Фильтры')}
        </button>
        <details className="rc-columns-menu">
          <summary className="button button-outline">{t('Колонки')}</summary>
          <div>
            {optionalColumns.map(([key, label]) => (
              <label key={key} className="rc-check">
                <input type="checkbox" checked={show(key)} onChange={() => toggleColumn(key)} />
                {label}
              </label>
            ))}
          </div>
        </details>
        <span className="rc-total">{t('{0} · {1}', [visible.length, money(total, true)])}</span>
      </div>
      {filtersOpen && (
        <section className="rc-filters" aria-label={t('Фильтры')}>
          <label>
            {t('Статус')}
            <select {...field('status')} aria-label={t('Фильтр по статусу')}>
              <option value="">{t('Все статусы')}</option>
              {statuses.map(([key, label]) => (
                <option key={key} value={key}>
                  {t(label)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Ответственный')}
            <select {...field('assignee')}>
              <option value="">{t('Все')}</option>
              {team.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Сумма от, ₽')}
            <input inputMode="numeric" {...field('amountFrom')} />
          </label>
          <label>
            {t('Сумма до, ₽')}
            <input inputMode="numeric" {...field('amountTo')} />
          </label>
          <label>
            {t('Просрочка от, дней')}
            <input inputMode="numeric" {...field('daysFrom')} />
          </label>
          <label>
            {t('Просрочка до, дней')}
            <input inputMode="numeric" {...field('daysTo')} />
          </label>
          <label>
            {t('Контакты')}
            <select {...field('contact')}>
              <option value="">{t('Любые')}</option>
              <option value="email">{t('Есть почта')}</option>
              <option value="phone">{t('Есть телефон')}</option>
              <option value="none">{t('Нет контактов')}</option>
            </select>
          </label>
          <label>
            {t('Документы')}
            <select {...field('documents')}>
              <option value="">{t('Любые')}</option>
              <option value="ready">{t('Готовы для суда')}</option>
              <option value="missing">{t('Не хватает')}</option>
            </select>
          </label>
          <label className="rc-check">
            <input
              type="checkbox"
              checked={filters.paused}
              onChange={(e) => setFilters({ ...filters, paused: e.target.checked })}
            />
            {t('Только с паузой уведомлений')}
          </label>
          <button className="wf-text-button" onClick={() => setFilters(emptyFilters)}>
            {t('Сбросить')}
          </button>
        </section>
      )}
      {selected.length > 0 && (
        <div className="rc-bulk" role="group" aria-label={t('Действия с выбранными')}>
          <span>{t('Выбрано: {0}', [selected.length])}</span>
          {view === 'pretrial' && (
            <>
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
              {isManager && (
                <button
                  className="button button-outline"
                  disabled={busy}
                  onClick={() => void bulk('to_court')}
                >
                  {t('Передать в суд')}
                </button>
              )}
            </>
          )}
          {stageKinds.length > 0 && (
            <select
              aria-label={t('Сформировать документ')}
              value=""
              disabled={busy}
              onChange={(e) => e.target.value && void bulk('document', { kind: e.target.value })}
            >
              <option value="">{t('Сформировать документ…')}</option>
              {stageKinds.map(([kind, item]) => (
                <option key={kind} value={kind}>
                  {t(item.title)}
                </option>
              ))}
            </select>
          )}
          <select
            aria-label={t('Назначить ответственного')}
            value=""
            disabled={busy}
            onChange={(e) => e.target.value && void bulk('assign', { assignee_id: e.target.value })}
          >
            <option value="">{t('Назначить ответственного…')}</option>
            {team.map((member) => (
              <option key={member.id} value={member.id}>
                {member.name}
              </option>
            ))}
          </select>
          <button
            className="button button-outline"
            disabled={busy}
            onClick={() => void bulk('hold')}
          >
            {t('Пауза уведомлений')}
          </button>
          <button
            className="button button-outline"
            disabled={busy}
            onClick={() => void bulk('unhold')}
          >
            {t('Снять паузу')}
          </button>
          <button
            className="button button-outline"
            disabled={busy}
            onClick={() => void bulk(view === 'archive' ? 'unarchive' : 'archive')}
          >
            {view === 'archive' ? t('Вернуть из архива') : t('В архив')}
          </button>
        </div>
      )}
      {visible.length === 0 ? (
        <div className="rc-empty">
          {items.length === 0
            ? t('Пока нет должников. Загрузите реестр в Excel, и система разложит долги по этапам.')
            : activeFilters || needle
              ? t('По этим условиям никого нет.')
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
                {show('documents') && <th>{t('Документы')}</th>}
                {show('assignee') && <th>{t('Ответственный')}</th>}
                {show('case') && <th>{t('Дело')}</th>}
                {show('next') && <th>{t('Следующий шаг')}</th>}
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
                    <small>
                      {item.inn ? t('ИНН {0}', [item.inn]) : t('ИНН не указан')}
                      {item.hold ? ` · ${t('пауза')}` : ''}
                    </small>
                  </td>
                  <td>
                    <span className={`rc-status rc-status-${item.next_step?.urgency ?? 'closed'}`}>
                      {t(item.status_label)}
                    </span>
                    {item.custom_status && <small>{item.custom_status}</small>}
                  </td>
                  <td className="rc-num">{money(item.balance, true)}</td>
                  <td className="rc-num">{t('{0} дн.', [item.days_overdue])}</td>
                  {show('documents') && (
                    <td>
                      <span
                        className={item.evidence_score < 100 ? 'rc-chip rc-chip-warn' : 'rc-chip'}
                      >
                        {item.evidence_score}%
                      </span>
                    </td>
                  )}
                  {show('assignee') && <td>{nameOf(item.assignee_id) || '—'}</td>}
                  {show('case') && <td>{item.case_number || item.writ_number || '—'}</td>}
                  {show('next') && (
                    <td className="rc-next">{t(item.next_step?.label || 'Ожидание')}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
