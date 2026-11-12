import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { api, del, money, put } from '../../api';
import { language, t } from '../../i18n';
import type { Notify } from './types';

type ChartKind = 'number' | 'columns' | 'bars' | 'line';
export type Tile = {
  id: string;
  title: string;
  chart: ChartKind;
  measure: string;
  group: string;
  stage: string;
  width: 1 | 2;
};
type TileData = {
  id: string;
  unit: 'money' | 'count';
  value?: number;
  note?: string;
  months?: boolean;
  rows?: { label: string; value: number }[];
};
type Home = {
  scope: 'current' | 'all';
  tiles: Tile[];
  data: TileData[];
  measures: Record<string, string>;
  groups: Record<string, string>;
  charts: Record<string, string>;
  several_organizations: boolean;
};

const stages: [string, string][] = [
  ['', t('Все открытые')],
  ['pretrial', t('Досудебная работа')],
  ['court', t('Суд')],
  ['enforcement', t('Исполнение')],
  ['closed', t('Закрыто')],
];
const short = (value: number, unit: string) =>
  unit === 'money' ? money(value, true) : String(value);
const monthLabel = (key: string) =>
  new Date(`${key}-15`).toLocaleDateString(language === 'en' ? 'en-GB' : 'ru-RU', {
    month: 'short',
  });

function Empty({ payments }: { payments: boolean }) {
  return (
    <p className="ch-empty">
      {payments
        ? t(
            'Поступлений пока нет. Они появятся, когда вы отметите оплату или загрузите выписку банка.'
          )
        : t('Пока нет данных. График заполнится после загрузки должников.')}
    </p>
  );
}

function Columns({
  rows,
  unit,
  months,
}: {
  rows: { label: string; value: number }[];
  unit: string;
  months?: boolean;
}) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <div
      className="ch-columns"
      style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(0, 1fr))` }}
    >
      {rows.map((row) => {
        const label = months ? monthLabel(row.label) : t(row.label);
        return (
          <div
            key={row.label}
            className="ch-col"
            tabIndex={0}
            aria-label={`${label}: ${short(row.value, unit)}`}
          >
            <span className="ch-tip">
              {label}: {short(row.value, unit)}
            </span>
            <b className="ch-col-value">{row.value ? short(row.value, unit) : ''}</b>
            <div className="ch-col-track">
              <i style={{ height: row.value ? `max(4px, ${(row.value / max) * 100}%)` : 0 }} />
            </div>
            <small>{label}</small>
          </div>
        );
      })}
    </div>
  );
}

function Bars({
  rows,
  unit,
  months,
}: {
  rows: { label: string; value: number }[];
  unit: string;
  months?: boolean;
}) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <ul className="ch-bars">
      {rows.map((row) => (
        <li key={row.label}>
          <span>{months ? monthLabel(row.label) : t(row.label)}</span>
          <div className="ch-bar-track">
            <i style={{ width: row.value ? `max(4px, ${(row.value / max) * 100}%)` : 0 }} />
          </div>
          <strong>{short(row.value, unit)}</strong>
        </li>
      ))}
    </ul>
  );
}

function Line({
  rows,
  unit,
  months,
}: {
  rows: { label: string; value: number }[];
  unit: string;
  months?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...rows.map((row) => row.value), 1);
  const width = 600;
  const height = 180;
  const step = rows.length > 1 ? width / (rows.length - 1) : width;
  const points = rows.map((row, index) => [
    index * step,
    height - (row.value / max) * (height - 12) - 6,
  ]);
  const path = points
    .map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ');
  const label = (row: { label: string }) => (months ? monthLabel(row.label) : t(row.label));
  return (
    <div className="ch-line" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <line x1="0" x2={width} y1={height - 0.5} y2={height - 0.5} className="ch-axis" />
        <path d={`${path} L${width},${height} L0,${height} Z`} className="ch-area" />
        <path d={path} className="ch-stroke" vectorEffect="non-scaling-stroke" />
      </svg>
      {hover !== null && (
        <span
          className="ch-dot"
          style={{
            left: `${(points[hover][0] / width) * 100}%`,
            top: `${(points[hover][1] / height) * 100}%`,
          }}
        />
      )}
      <div
        className="ch-hits"
        style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(0, 1fr))` }}
      >
        {rows.map((row, index) => (
          <button
            key={row.label}
            type="button"
            aria-label={`${label(row)}: ${short(row.value, unit)}`}
            onMouseEnter={() => setHover(index)}
            onFocus={() => setHover(index)}
          >
            {hover === index && (
              <span className="ch-tip">
                {label(row)}: {short(row.value, unit)}
              </span>
            )}
          </button>
        ))}
      </div>
      <div
        className="ch-x"
        style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(0, 1fr))` }}
      >
        {rows.map((row) => (
          <small key={row.label}>{label(row)}</small>
        ))}
      </div>
    </div>
  );
}

function Chart({ tile, data }: { tile: Tile; data?: TileData }) {
  if (!data) return <p className="ch-empty">{t('Загружаем…')}</p>;
  if (tile.chart === 'number')
    return (
      <p className="ch-number">
        {short(data.value ?? 0, data.unit)}
        {data.note && <small>{t(data.note)}</small>}
      </p>
    );
  const rows = data.rows ?? [];
  if (!rows.some((row) => row.value > 0)) return <Empty payments={Boolean(data.months)} />;
  if (tile.chart === 'line') return <Line rows={rows} unit={data.unit} months={data.months} />;
  if (tile.chart === 'columns')
    return <Columns rows={rows} unit={data.unit} months={data.months} />;
  return <Bars rows={rows} unit={data.unit} months={data.months} />;
}

function TileSettings({
  tile,
  home,
  onChange,
}: {
  tile: Tile;
  home: Home;
  onChange: (next: Tile) => void;
}) {
  const set = (patch: Partial<Tile>) => {
    const next = { ...tile, ...patch };
    // Payments are counted by month; debts are counted per debtor.
    if (patch.measure === 'collected') next.group = 'month';
    if (patch.group === 'month') next.measure = 'collected';
    if (patch.measure && patch.measure !== 'collected' && next.group === 'month')
      next.group = 'stage';
    onChange(next);
  };
  return (
    <div className="ch-settings">
      <label>
        {t('Название')}
        <input value={tile.title} onChange={(e) => set({ title: e.target.value })} />
      </label>
      <label>
        {t('Вид')}
        <select value={tile.chart} onChange={(e) => set({ chart: e.target.value as ChartKind })}>
          {Object.entries(home.charts).map(([key, label]) => (
            <option key={key} value={key}>
              {t(label)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('Что считать')}
        <select value={tile.measure} onChange={(e) => set({ measure: e.target.value })}>
          {Object.entries(home.measures).map(([key, label]) => (
            <option key={key} value={key}>
              {t(label)}
            </option>
          ))}
        </select>
      </label>
      {tile.chart !== 'number' && (
        <label>
          {t('Разбить по')}
          <select value={tile.group} onChange={(e) => set({ group: e.target.value })}>
            {Object.entries(home.groups)
              .filter(([key]) => key !== 'organization' || home.several_organizations)
              .map(([key, label]) => (
                <option key={key} value={key}>
                  {t(label)}
                </option>
              ))}
          </select>
        </label>
      )}
      {tile.group !== 'month' && (
        <label>
          {t('Этап')}
          <select value={tile.stage} onChange={(e) => set({ stage: e.target.value })}>
            {stages.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="rc-check">
        <input
          type="checkbox"
          checked={tile.width === 2}
          onChange={(e) => set({ width: e.target.checked ? 2 : 1 })}
        />
        {t('Во всю ширину')}
      </label>
    </div>
  );
}

export function HomeCharts({
  editing,
  notify,
  refreshKey,
}: {
  editing: boolean;
  notify: Notify;
  refreshKey: number;
}) {
  const [home, setHome] = useState<Home | null>(null);
  const fail = useCallback((error: Error) => notify(error.message, true), [notify]);
  useEffect(() => {
    api<Home>('/recovery/home').then(setHome).catch(fail);
  }, [refreshKey, fail]);
  if (!home) return null;
  function save(tiles: Tile[], scope = home!.scope) {
    setHome({ ...home!, tiles, scope });
    put<Home>('/recovery/home', {
      name: t('Главная'),
      scope,
      tiles: tiles.map((tile) => ({ ...tile, title: tile.title.trim() || t('График') })),
    })
      .then(setHome)
      .catch(fail);
  }
  function move(index: number, step: number) {
    const tiles = [...home!.tiles];
    const [tile] = tiles.splice(index, 1);
    tiles.splice(index + step, 0, tile);
    save(tiles);
  }
  return (
    <section className="ch-board" aria-label={t('Графики')}>
      {editing && (
        <div className="ch-board-tools">
          <button
            type="button"
            className="button button-outline"
            onClick={() =>
              save([
                ...home.tiles,
                {
                  id: crypto.randomUUID().slice(0, 12),
                  title: t('Новый график'),
                  chart: 'bars',
                  measure: 'debt',
                  group: 'stage',
                  stage: '',
                  width: 1,
                },
              ])
            }
          >
            <Plus size={15} aria-hidden="true" />
            {t('Добавить график')}
          </button>
          {home.several_organizations && (
            <label className="rc-check">
              <input
                type="checkbox"
                checked={home.scope === 'all'}
                onChange={(e) => save(home.tiles, e.target.checked ? 'all' : 'current')}
              />
              {t('По всем организациям')}
            </label>
          )}
          <button
            type="button"
            className="wf-text-button"
            onClick={() =>
              del<Home>('/recovery/home')
                .then((result) => result && setHome(result as Home))
                .catch(fail)
            }
          >
            <RotateCcw size={14} aria-hidden="true" />
            {t('Вернуть графики по умолчанию')}
          </button>
        </div>
      )}
      <div className="ch-grid">
        {home.tiles.map((tile, index) => (
          <article key={tile.id} className={`rc-card ch-card ${tile.width === 2 ? 'ch-wide' : ''}`}>
            <div className="rc-card-head">
              <h2>{t(tile.title)}</h2>
              {editing && (
                <div className="rc-tile-tools">
                  <button
                    type="button"
                    aria-label={t('Левее')}
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                  >
                    <ArrowLeft size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    aria-label={t('Правее')}
                    disabled={index === home.tiles.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    <ArrowRight size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    aria-label={t('Удалить график')}
                    onClick={() => save(home.tiles.filter((item) => item.id !== tile.id))}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              )}
            </div>
            {editing && (
              <TileSettings
                tile={tile}
                home={home}
                onChange={(next) =>
                  save(home.tiles.map((item) => (item.id === tile.id ? next : item)))
                }
              />
            )}
            <Chart tile={tile} data={home.data.find((row) => row.id === tile.id)} />
          </article>
        ))}
      </div>
    </section>
  );
}
