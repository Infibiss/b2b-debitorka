import { useEffect, useState, type FormEvent } from 'react';
import { Plus } from 'lucide-react';
import { api, money, post } from '../../api';
import { t } from '../../i18n';
import type { Notify } from './types';

type Org = { id: string; company: string; role: string };
type Summary = { id: string; company: string; debtors: number; balance: number; overdue: number };

export function OrganizationSwitch({ notify }: { notify: Notify }) {
  const [items, setItems] = useState<Org[]>([]);
  const [active, setActive] = useState('');
  const [adding, setAdding] = useState(false);
  const [company, setCompany] = useState('');
  const [inn, setInn] = useState('');
  useEffect(() => {
    api<{ active: string; items: Org[] }>('/organizations')
      .then((result) => {
        setItems(result.items);
        setActive(result.active);
      })
      .catch((error) => notify(error.message, true));
  }, [notify]);
  function submit(event: FormEvent) {
    event.preventDefault();
    post('/organizations', { company, inn })
      .then(() => location.assign('/app'))
      .catch((error) => notify(error.message, true));
  }
  return (
    <div className="org-switch">
      {items.length > 1 ? (
        <select
          aria-label={t('Организация')}
          value={active}
          onChange={(e) =>
            void post(`/organizations/${e.target.value}/switch`)
              .then(() => location.assign('/app'))
              .catch((error) => notify(error.message, true))
          }
        >
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.company}
            </option>
          ))}
        </select>
      ) : (
        <span className="org-name">{items[0]?.company}</span>
      )}
      <button
        className="org-add"
        aria-label={t('Добавить организацию')}
        title={t('Добавить организацию')}
        onClick={() => setAdding(true)}
      >
        <Plus size={15} aria-hidden="true" />
      </button>
      {adding && (
        <div
          className="org-dialog"
          role="dialog"
          aria-modal="true"
          aria-label={t('Новая организация')}
        >
          <form className="rc-card" onSubmit={submit}>
            <h2>{t('Новая организация')}</h2>
            <label>
              {t('Название')}
              <input
                required
                minLength={2}
                value={company}
                onChange={(e) => setCompany(e.target.value)}
              />
            </label>
            <label>
              {t('ИНН')}
              <input
                inputMode="numeric"
                pattern="\d{10}|\d{12}"
                value={inn}
                onChange={(e) => setInn(e.target.value)}
              />
            </label>
            <p className="rc-muted">
              {t('У каждой организации свои должники, настройки и тариф.')}
            </p>
            <div className="rc-action-buttons">
              <button className="button button-dark">{t('Создать')}</button>
              <button
                type="button"
                className="button button-outline"
                onClick={() => setAdding(false)}
              >
                {t('Отмена')}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export function OrganizationsSummary({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<Summary[]>([]);
  useEffect(() => {
    api<{ items: Summary[] }>('/organizations/summary')
      .then((result) => setItems(result.items))
      .catch(() => setItems([]));
  }, [refreshKey]);
  if (items.length < 2) return null;
  return (
    <section className="rc-card">
      <h2>{t('По организациям')}</h2>
      <div className="rc-table-scroll">
        <table className="rc-table rc-table-plain">
          <thead>
            <tr>
              <th>{t('Организация')}</th>
              <th className="rc-num">{t('Должников')}</th>
              <th className="rc-num">{t('В работе')}</th>
              <th className="rc-num">{t('Просрочено')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                <td>{row.company}</td>
                <td className="rc-num">{row.debtors}</td>
                <td className="rc-num">{money(row.balance, true)}</td>
                <td className="rc-num">{money(row.overdue, true)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
