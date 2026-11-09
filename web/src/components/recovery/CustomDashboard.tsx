import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, Plus, Trash2 } from 'lucide-react';
import { api, del, money, post, put } from '../../api';
import { language, t } from '../../i18n';
import type { Notify } from './types';

type Tile = {
  id: string;
  title: string;
  kind: 'metric' | 'category' | 'timeline';
  measure: string;
  group: string;
  stage: string;
  width: 1 | 2;
};
export type Board = {
  id: string;
  name: string;
  shared: boolean;
  scope: 'current' | 'all';
  mine: boolean;
  tiles: Tile[];
};
type Boards = { items: Board[]; measures: Record<string, string>; groups: Record<string, string> };
type TileData = {
  id: string;
  unit: 'money' | 'count';
  value?: number;
  note?: string;
  rows?: { label: string; value: number }[];
  series?: { month: string; amount: number }[];
};

const stages: [string, string][] = [
  ['', t('Все открытые')],
  ['pretrial', t('Досудебная работа')],
  ['court', t('Суд')],
  ['enforcement', t('Исполнение')],
  ['closed', t('Закрыто')],
];
const blankTile = {
  title: '',
  kind: 'metric',
  measure: 'debt',
  group: 'stage',
  stage: '',
  width: 1,
};
const show = (value: number, unit: string) =>
  unit === 'money' ? money(value, true) : String(value);
const month = (key: string) =>
  new Date(`${key}-15`).toLocaleDateString(language === 'en' ? 'en-GB' : 'ru-RU', {
    month: 'short',
  });

function TileBody({ tile, data }: { tile: Tile; data?: TileData }) {
  if (!data) return <p className="rc-muted">{t('Загружаем…')}</p>;
  if (tile.kind === 'metric') {
    return (
      <p className="rc-tile-value">
        {show(data.value ?? 0, data.unit)}
        {data.note && <small>{t(data.note)}</small>}
      </p>
    );
  }
  if (tile.kind === 'timeline') {
    const series = data.series ?? [];
    const max = Math.max(...series.map((row) => row.amount), 1);
    return (
      <div className="rc-columns-chart" role="img" aria-label={tile.title}>
        {series.map((row) => (
          <div key={row.month} className="rc-col" tabIndex={0}>
            <span className="rc-col-tip">
              {month(row.month)}: {money(row.amount, true)}
            </span>
            <i style={{ height: row.amount ? `max(4px, ${(row.amount / max) * 100}%)` : 0 }} />
            <small>{month(row.month)}</small>
          </div>
        ))}
      </div>
    );
  }
  const rows = data.rows ?? [];
  if (rows.length === 0) return <p className="rc-muted">{t('Пока нет данных.')}</p>;
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <ul className="rc-aging">
      {rows.map((row) => (
        <li key={row.label}>
          <span>{t(row.label)}</span>
          <div className="rc-aging-track">
            <i
              data-step="4"
              style={{ width: row.value ? `max(4px, ${(row.value / max) * 100}%)` : 0 }}
            />
          </div>
          <strong>{show(row.value, data.unit)}</strong>
        </li>
      ))}
    </ul>
  );
}

function TileForm({
  boards,
  onAdd,
  onCancel,
}: {
  boards: Boards;
  onAdd: (tile: Tile) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState(blankTile);
  function submit(event: FormEvent) {
    event.preventDefault();
    onAdd({ ...form, id: crypto.randomUUID().slice(0, 12) } as Tile);
  }
  const set = (key: string, value: string | number) => setForm({ ...form, [key]: value });
  return (
    <form className="rc-details rc-card" onSubmit={submit}>
      <label>
        {t('Название')}
        <input required value={form.title} onChange={(e) => set('title', e.target.value)} />
      </label>
      <label>
        {t('Вид')}
        <select value={form.kind} onChange={(e) => set('kind', e.target.value)}>
          <option value="metric">{t('Показатель')}</option>
          <option value="category">{t('Разбивка')}</option>
          <option value="timeline">{t('Динамика за год')}</option>
        </select>
      </label>
      {form.kind !== 'timeline' && (
        <label>
          {t('Что считать')}
          <select value={form.measure} onChange={(e) => set('measure', e.target.value)}>
            {Object.entries(boards.measures).map(([key, label]) => (
              <option key={key} value={key}>
                {t(label)}
              </option>
            ))}
          </select>
        </label>
      )}
      {form.kind === 'category' && (
        <label>
          {t('Разбить по')}
          <select value={form.group} onChange={(e) => set('group', e.target.value)}>
            {Object.entries(boards.groups).map(([key, label]) => (
              <option key={key} value={key}>
                {t(label)}
              </option>
            ))}
          </select>
        </label>
      )}
      {form.kind !== 'timeline' && (
        <label>
          {t('Этап')}
          <select value={form.stage} onChange={(e) => set('stage', e.target.value)}>
            {stages.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        {t('Ширина')}
        <select value={form.width} onChange={(e) => set('width', Number(e.target.value))}>
          <option value={1}>{t('Обычная')}</option>
          <option value={2}>{t('Двойная')}</option>
        </select>
      </label>
      <div className="rc-action-buttons rc-span">
        <button className="button button-dark">{t('Добавить')}</button>
        <button type="button" className="button button-outline" onClick={onCancel}>
          {t('Отмена')}
        </button>
      </div>
    </form>
  );
}

export function BoardsBar({
  selected,
  onSelect,
  notify,
  refreshKey,
}: {
  selected: string;
  onSelect: (id: string) => void;
  notify: Notify;
  refreshKey: number;
}) {
  const [boards, setBoards] = useState<Boards | null>(null);
  const [data, setData] = useState<TileData[]>([]);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const fail = useCallback((error: Error) => notify(error.message, true), [notify]);
  const load = useCallback(
    () => api<Boards>('/recovery/dashboards').then(setBoards).catch(fail),
    [fail]
  );
  useEffect(() => {
    void load();
  }, [load]);
  const board = boards?.items.find((item) => item.id === selected);
  const loadData = useCallback(() => {
    if (!selected) return;
    api<{ items: TileData[] }>(`/recovery/dashboards/${selected}/data`)
      .then((result) => setData(result.items))
      .catch(fail);
  }, [selected, fail]);
  useEffect(() => {
    setData([]);
    loadData();
  }, [loadData, refreshKey]);
  if (!boards) return null;
  async function create() {
    const result = await post<{ id: string }>('/recovery/dashboards', {
      name: t('Новая панель'),
      tiles: [
        {
          id: 'debt',
          title: t('В работе'),
          kind: 'metric',
          measure: 'debt',
          group: 'stage',
          stage: '',
          width: 1,
        },
        {
          id: 'stages',
          title: t('По этапам'),
          kind: 'category',
          measure: 'debt',
          group: 'stage',
          stage: '',
          width: 1,
        },
      ],
    });
    await load();
    onSelect(result.id);
    setEditing(true);
  }
  function save(patch: Partial<Board>) {
    if (!board) return;
    const next = { ...board, ...patch };
    setBoards({
      ...boards!,
      items: boards!.items.map((item) => (item.id === next.id ? next : item)),
    });
    put(`/recovery/dashboards/${board.id}`, {
      name: next.name || t('Панель'),
      shared: next.shared,
      scope: next.scope,
      tiles: next.tiles,
    })
      .then(loadData)
      .catch(fail);
  }
  function move(index: number, step: number) {
    const tiles = [...board!.tiles];
    const [tile] = tiles.splice(index, 1);
    tiles.splice(index + step, 0, tile);
    save({ tiles });
  }
  return (
    <>
      <nav className="rc-board-tabs" aria-label={t('Панели')}>
        <button
          className={selected ? '' : 'active'}
          aria-current={selected ? undefined : 'page'}
          onClick={() => {
            setEditing(false);
            onSelect('');
          }}
        >
          {t('Обзор')}
        </button>
        {boards.items.map((item) => (
          <button
            key={item.id}
            className={item.id === selected ? 'active' : ''}
            aria-current={item.id === selected ? 'page' : undefined}
            onClick={() => {
              setEditing(false);
              onSelect(item.id);
            }}
          >
            {item.name}
          </button>
        ))}
        <button aria-label={t('Новая панель')} onClick={() => void create().catch(fail)}>
          <Plus size={15} aria-hidden="true" />
          {t('Панель')}
        </button>
      </nav>
      {board && (
        <section className="rc-board" aria-label={board.name}>
          <div className="rc-board-head">
            {editing ? (
              <>
                <input
                  aria-label={t('Название панели')}
                  value={board.name}
                  onChange={(e) => save({ name: e.target.value })}
                />
                <label className="rc-check">
                  <input
                    type="checkbox"
                    checked={board.shared}
                    onChange={(e) => save({ shared: e.target.checked })}
                  />
                  {t('Видна всей команде')}
                </label>
                <label className="rc-check">
                  <input
                    type="checkbox"
                    checked={board.scope === 'all'}
                    onChange={(e) => save({ scope: e.target.checked ? 'all' : 'current' })}
                  />
                  {t('По всем организациям')}
                </label>
              </>
            ) : (
              <span />
            )}
            <div className="rc-action-buttons">
              {editing && (
                <button className="button button-outline" onClick={() => setAdding(true)}>
                  <Plus size={15} aria-hidden="true" />
                  {t('Плитка')}
                </button>
              )}
              <button className="button button-outline" onClick={() => setEditing(!editing)}>
                {editing ? t('Готово') : t('Настроить')}
              </button>
              {editing && (
                <button
                  className="button button-outline"
                  onClick={() =>
                    void del(`/recovery/dashboards/${board.id}`)
                      .then(() => {
                        onSelect('');
                        setEditing(false);
                        return load();
                      })
                      .catch(fail)
                  }
                >
                  {t('Удалить панель')}
                </button>
              )}
            </div>
          </div>
          {adding && (
            <TileForm
              boards={boards}
              onCancel={() => setAdding(false)}
              onAdd={(tile) => {
                setAdding(false);
                save({ tiles: [...board.tiles, tile] });
              }}
            />
          )}
          <div className="rc-tiles">
            {board.tiles.map((tile, index) => (
              <article
                key={tile.id}
                className={`rc-card ${tile.width === 2 ? 'rc-tile-wide' : ''}`}
              >
                <div className="rc-card-head">
                  <h2>{tile.title}</h2>
                  {editing && (
                    <div className="rc-tile-tools">
                      <button
                        aria-label={t('Левее')}
                        disabled={index === 0}
                        onClick={() => move(index, -1)}
                      >
                        <ArrowLeft size={14} aria-hidden="true" />
                      </button>
                      <button
                        aria-label={t('Правее')}
                        disabled={index === board.tiles.length - 1}
                        onClick={() => move(index, 1)}
                      >
                        <ArrowRight size={14} aria-hidden="true" />
                      </button>
                      <button
                        aria-label={t('Удалить плитку')}
                        onClick={() => save({ tiles: board.tiles.filter((x) => x.id !== tile.id) })}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </div>
                  )}
                </div>
                <TileBody tile={tile} data={data.find((row) => row.id === tile.id)} />
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
