import { useEffect, useState, type FormEvent } from 'react';
import { Check, Plus } from 'lucide-react';
import { api, money, post } from '../../api';
import { t } from '../../i18n';
import type { Notify } from './types';

type Org = { id: string; company: string; role: string };
type Summary = { id: string; company: string; debtors: number; balance: number; overdue: number };

export function OrganizationMenu({ notify, onAdd }: { notify: Notify; onAdd: () => void }) {
  const [items, setItems] = useState<Org[]>([]);
  const [active, setActive] = useState('');
  useEffect(() => {
    api<{ active: string; items: Org[] }>('/organizations')
      .then((result) => {
        setItems(result.items);
        setActive(result.active);
      })
      .catch((error) => notify(error.message, true));
  }, [notify]);
  return (
    <div className="org-menu" role="group" aria-label={t('Организация')}>
      <p>{t('Организация')}</p>
      {items.map((item) => (
        <button
          key={item.id}
          role="menuitemradio"
          aria-checked={item.id === active}
          onClick={() =>
            item.id !== active &&
            void post(`/organizations/${item.id}/switch`)
              .then(() => location.assign('/app'))
              .catch((error) => notify(error.message, true))
          }
        >
          <span className="org-mark">
            {item.id === active && <Check size={14} aria-hidden="true" />}
          </span>
          {item.company}
        </button>
      ))}
      <button role="menuitem" onClick={onAdd}>
        <span className="org-mark">
          <Plus size={14} aria-hidden="true" />
        </span>
        {t('Добавить организацию')}
      </button>
    </div>
  );
}

export function OrganizationDialog({ notify, onClose }: { notify: Notify; onClose: () => void }) {
  const [company, setCompany] = useState('');
  const [inn, setInn] = useState('');
  function submit(event: FormEvent) {
    event.preventDefault();
    post('/organizations', { company, inn })
      .then(() => location.assign('/app'))
      .catch((error) => notify(error.message, true));
  }
  return (
    <div className="org-dialog" role="dialog" aria-modal="true" aria-label={t('Новая организация')}>
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
        <p className="rc-muted">{t('У каждой организации свои должники, настройки и тариф.')}</p>
        <div className="rc-action-buttons">
          <button className="button button-dark">{t('Создать')}</button>
          <button type="button" className="button button-outline" onClick={onClose}>
            {t('Отмена')}
          </button>
        </div>
      </form>
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
