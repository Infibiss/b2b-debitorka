import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import {
  ArrowRight,
  Check,
  Menu,
  X,
  FileText,
  MessagesSquare,
  Landmark,
  Layers,
  ArrowUpRight,
} from 'lucide-react';
import { Brand } from './Brand';
import { api, post, setCsrf, money, ApiError, type Session } from '../api';
import catalog from '../../../server/plan_catalog.json';
import { PublicLegal, type PublicLegalKind } from './PublicLegal';
import './public-site.css';
import { PublicProcess } from './PublicProcess';
import { PublicStoryPages } from './PublicStoryPages';

type Plan = {
  id: string;
  name: string;
  price_monthly: number | null;
  active_invoice_limit: number | null;
  user_limit: number | null;
  features: string[];
};
const plans = catalog.items as Plan[];
const legalRoutes: Record<string, string> = {
  '/privacy': 'privacy',
  '/terms': 'terms',
  '/refunds': 'refunds',
  '/cookies': 'cookies',
  '/company': 'company',
  '/data-request': 'data-request',
};
const nav = [
  ['Продукт', '/product'],
  ['Для вашей команды', '/solutions'],
  ['Подключения', '/integrations'],
  ['Цены', '/pricing'],
];
const features = [
  {
    icon: Layers,
    title: 'Один портфель вместо разрозненных таблиц',
    text: 'Счета, договоры и частичные оплаты собраны по клиенту. Видно, сколько осталось получить и что мешает оплате.',
  },
  {
    icon: MessagesSquare,
    title: 'Напоминания без ежедневной ручной работы',
    text: 'Задайте расписание и правила общения. Mandato следит за сроками, а споры и новые условия передаёт ответственному.',
  },
  {
    icon: Landmark,
    title: 'Оплата подтверждается поступлением',
    text: 'Сверяйте выписку со счетами. Обещание клиента остаётся обещанием, пока деньги не поступят.',
  },
  {
    icon: FileText,
    title: 'Юридическая работа продолжает историю дела',
    text: 'Соберите документы, рассчитайте требования и передайте пакет юристу. Переписку и основания не придётся искать заново.',
  },
];
function Button({
  href,
  children,
  secondary = false,
}: {
  href: string;
  children: ReactNode;
  secondary?: boolean;
}) {
  return (
    <a className={`pub-button ${secondary ? 'pub-secondary' : ''}`} href={href}>
      {children}
      <ArrowUpRight size={18} aria-hidden="true" />
    </a>
  );
}
function Header() {
  const [open, setOpen] = useState(false);
  return (
    <header className="pub-header">
      <Brand />
      <button
        className="pub-mobile-menu"
        aria-label={open ? 'Закрыть меню' : 'Открыть меню'}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? <X /> : <Menu />}
      </button>
      <nav className={open ? 'is-open' : ''} aria-label="Основная навигация">
        {nav.map(([label, href]) => (
          <a key={href} href={href} aria-current={location.pathname === href ? 'page' : undefined}>
            {label}
          </a>
        ))}
        <a className="pub-login" href="/app?mode=login">
          Войти <ArrowUpRight size={16} aria-hidden="true" />
        </a>
        <a className="pub-nav-demo" href="/demo">
          Заказать демонстрацию
        </a>
      </nav>
    </header>
  );
}
function Footer() {
  return (
    <footer className="pub-footer">
      <div>
        <Brand />
        <a href="mailto:info@mandato.ru">info@mandato.ru</a>
      </div>
      <nav aria-label="Информация о сервисе">
        <a href="/security">Безопасность</a>
        <a href="/company">О компании</a>
        <a href="/privacy">Конфиденциальность</a>
        <a href="/terms">Условия использования</a>
        <a href="/refunds">Возврат средств</a>
        <a href="/cookies">Файлы cookie</a>
      </nav>
      <p>© {new Date().getFullYear()} Mandato</p>
    </footer>
  );
}
function CookieNotice() {
  const [visible, setVisible] = useState(() => {
    try {
      return localStorage.getItem('mandato-cookie-notice') !== 'seen';
    } catch {
      return true;
    }
  });
  return visible ? (
    <aside className="pub-cookie" aria-label="Использование cookie">
      <p>
        Используем необходимые cookie для входа и безопасности. <a href="/cookies">Подробнее</a>
      </p>
      <button
        onClick={() => {
          try {
            localStorage.setItem('mandato-cookie-notice', 'seen');
          } catch {
            /* dismissal still works */
          }
          setVisible(false);
        }}
      >
        Понятно
      </button>
    </aside>
  ) : null;
}
function Home() {
  return (
    <>
      <section className="pub-hero">
        <h1>
          Ведите дебиторку
          <br />
          <span>от счёта до оплаты</span>
        </h1>
        <p className="pub-lead">
          Управляйте задолженностью от первого счёта до поступления денег. Mandato связывает
          бухгалтерию, общение с клиентом и юридическую работу в одном процессе.
        </p>
        <div className="pub-actions">
          <Button href="/demo">Заказать демонстрацию</Button>
          <Button href="/start?plan=trial" secondary>
            Попробовать бесплатно
          </Button>
        </div>
        <p className="pub-caption">14 дней без карты и автоматического продления</p>
      </section>
      <PublicProcess />
      <section className="pub-section">
        <div className="pub-section-title">
          <h2>
            Не упускайте деньги
            <br />
            между отделами.
          </h2>
          <p>
            Когда каждый видит свою часть работы, задолженность движется к оплате. Общая история
            помогает команде действовать согласованно.
          </p>
        </div>
        <div className="pub-feature-grid">
          {features.map(({ title, text }) => (
            <article key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="pub-section pub-team">
        <h2>
          Одна система
          <br />
          Понятная роль для каждого
        </h2>
        <div className="pub-three">
          <article>
            <span>Бухгалтерия</span>
            <h3>Точные суммы и документы</h3>
            <p>
              Разбирайте поступления и расхождения, находите недостающие документы и передавайте
              подготовленное дело дальше.
            </p>
          </article>
          <article>
            <span>Руководитель</span>
            <h3>Решения без потери контроля</h3>
            <p>
              Определяйте правила, согласуйте скидки и рассрочки. Видно, какие долги требуют участия
              команды.
            </p>
          </article>
          <article>
            <span>Юрист</span>
            <h3>История, готовая к работе</h3>
            <p>
              Договор, счета, доказательства и переписка собраны вместе. Проверяйте требования и
              ведите дальнейшие этапы взыскания.
            </p>
          </article>
        </div>
      </section>
      <section className="pub-section pub-connections">
        <div>
          <h2>
            Начните с реестра
            <br />
            Подключайте источники по мере готовности
          </h2>
          <p>
            Загрузите таблицу, чтобы увидеть портфель. Для регулярного обмена подключите вашу
            учётную систему, документы и банк.
          </p>
          <a className="pub-text-link" href="/integrations">
            Как устроены подключения <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
        <div className="pub-source-list">
          {[
            ['Excel и CSV', 'Загрузка счетов и выписок'],
            ['1С', 'Данные учёта и сверка'],
            ['Диадок', 'Документы по сделкам'],
            ['Банк', 'Подтверждение поступлений'],
          ].map(([name, text]) => (
            <div key={name}>
              <strong>{name}</strong>
              <span>{text}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="pub-final-cta" aria-labelledby="pub-final-cta-title">
        <div>
          <h2 id="pub-final-cta-title">Начните получать оплату вовремя</h2>
          <p>
            Соберите задолженность в одном реестре, определите следующий шаг и держите
            договорённости с клиентами под контролем.
          </p>
        </div>
        <div className="pub-final-cta-action">
          <p>14 дней бесплатно</p>
          <Button href="/start?plan=trial">Попробовать бесплатно</Button>
          <span>Без карты и автоматического продления</span>
        </div>
      </section>
    </>
  );
}
function Pricing() {
  return (
    <>
      <section className="pub-page-hero pub-pricing-hero">
        <h1>Тарифы для вашей команды</h1>
        <p className="pub-lead">
          Ежемесячная подписка для вашей команды. Начните с 14 дней бесплатно — без карты и
          автоматического списания.
        </p>
        <Button href="/start?plan=trial">Начать бесплатный период</Button>
      </section>
      <section className="pub-pricing-grid" aria-label="Тарифы Mandato">
        {plans.map((plan, i) => (
          <article className={i === 1 ? 'is-featured' : ''} key={plan.id}>
            <div className="pub-plan-name">
              <h2>{plan.name}</h2>
              {i === 1 && <span>Для совместной работы</span>}
            </div>
            <p className="pub-plan-price">
              {plan.price_monthly === null ? 'По договору' : money(plan.price_monthly)}
              {plan.price_monthly !== null && <span>в месяц за организацию</span>}
            </p>
            <p>
              {
                [
                  'Для небольшого портфеля и одного ответственного.',
                  'Для бухгалтерии и руководителя с общей очередью дел.',
                  'Для большой команды и регулярной работы с задолженностью.',
                  'Для группы компаний и особых требований к подключению.',
                ][i]
              }
            </p>
            <p className="pub-plan-capacity">
              {plan.active_invoice_limit
                ? `До ${plan.active_invoice_limit.toLocaleString('ru-RU')} активных счетов · ${plan.user_limit} ${plan.user_limit === 2 ? 'участника' : 'участников'}`
                : 'Объём портфеля и команда — по договору'}
            </p>
            <ul>
              {plan.features.map((f) => (
                <li key={f}>
                  <Check size={17} aria-hidden="true" />
                  {f}
                </li>
              ))}
            </ul>
            <Button
              href={plan.id === 'custom' ? '/demo?kind=custom' : `/start?plan=${plan.id}`}
              secondary={i !== 1}
            >
              {plan.id === 'custom' ? 'Обсудить условия' : `Выбрать «${plan.name}»`}
            </Button>
          </article>
        ))}
      </section>
      <section className="pub-section">
        <div className="pub-section-title">
          <h2>Сравните условия</h2>
          <p>
            В пробном периоде доступны все инструменты. Одна организация — одна подписка. Каждый
            следующий тариф включает предыдущий. Подключение внешних систем и услуги взыскания
            согласуются отдельно до начала работы.
          </p>
        </div>
        <div className="pub-table-scroll">
          <table className="pub-compare">
            <caption>Состав подписки по тарифам</caption>
            <thead>
              <tr>
                <th scope="col">Возможности</th>
                {plans.map((p) => (
                  <th scope="col" key={p.id}>
                    {p.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                [
                  'Активные счета',
                  ...plans.map(
                    (p) => p.active_invoice_limit?.toLocaleString('ru-RU') || 'По договору'
                  ),
                ],
                ['Участники команды', ...plans.map((p) => String(p.user_limit || 'По договору'))],
                ['Реестр, аудит и документы', 'Включено', 'Включено', 'Включено', 'Включено'],
                [
                  'Оплаты, частичные платежи и сверка',
                  'Включено',
                  'Включено',
                  'Включено',
                  'Включено',
                ],
                ['Напоминания и история общения', 'Включено', 'Включено', 'Включено', 'Включено'],
                ['Роли и согласование условий', '—', 'Включено', 'Включено', 'Включено'],
                ['Прогноз поступлений', '—', 'Включено', 'Включено', 'Включено'],
                ['Скидки, отсрочки и рассрочки', '—', 'Включено', 'Включено', 'Включено'],
                ['Юридические дела и расчёт требований', '—', '—', 'Включено', 'Включено'],
                ['Подготовка претензии и судебного пакета', '—', '—', 'Включено', 'Включено'],
                ['Особые требования к внедрению', '—', '—', '—', 'По договору'],
              ].map(([name, ...values]) => (
                <tr key={name}>
                  <th scope="row">{name}</th>
                  {values.map((value, i) => (
                    <td key={i}>{value}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="pub-section pub-extra">
        <h2>Услуги взыскания — отдельно</h2>
        <div className="pub-three">
          <article>
            <h3>6% от поступлений</h3>
            <p>
              После направления претензии и до подачи заявления в суд. Оплата с фактически
              поступивших денег.
            </p>
          </article>
          <article>
            <h3>7 000 / 12 000 ₽</h3>
            <p>
              За подготовленный и поданный пакет судебного приказа или иска, независимо от
              результата взыскания.
            </p>
          </article>
          <article>
            <h3>Адвокату — 12%</h3>
            <p>
              От поступлений после подачи в суд, по прямому соглашению с клиентом. Эта сумма не
              входит в вознаграждение Mandato.
            </p>
          </article>
        </div>
        <p>
          Госпошлина оплачивается отдельно; её возмещение с должника не гарантируется. Заявление в
          банк по исполнительному листу бесплатно. Условия и лимиты голосовых минут фиксируются в
          договоре. Деньги должника поступают напрямую вам.
        </p>
        <a href="/refunds" className="pub-text-link">
          Отмена подписки и возврат средств <ArrowRight size={18} aria-hidden="true" />
        </a>
      </section>
    </>
  );
}
function RequestDemo() {
  const custom = new URLSearchParams(location.search).get('kind') === 'custom';
  const [done, setDone] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d = new FormData(e.currentTarget);
    setBusy(true);
    setError('');
    try {
      const r = await post<{ id: string }>('/commercial/requests', {
        kind: custom ? 'custom' : 'demo',
        name: d.get('name'),
        email: d.get('email'),
        company: d.get('company') || '',
        note: d.get('note') || '',
        consent: d.get('consent') === 'on',
      });
      setDone(r.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="pub-form-layout">
      <div>
        <p className="pub-eyebrow">
          {custom ? 'Индивидуальные условия' : 'Личное знакомство с Mandato'}
        </p>
        <h1>{custom ? 'Подключение под вашу компанию.' : 'Покажем работу на вашем сценарии.'}</h1>
        <p className="pub-lead">
          {custom
            ? 'Обсудим объём портфеля, состав команды и требования к обмену данными.'
            : 'Пройдём путь от загрузки реестра до сверки оплаты. Обсудим работу бухгалтерии, руководителя и юриста.'}
        </p>
        <ul className="pub-check-list">
          <li>
            <Check aria-hidden="true" />
            Как устроена очередь дел
          </li>
          <li>
            <Check aria-hidden="true" />
            Где помогает автоматизация
          </li>
          <li>
            <Check aria-hidden="true" />
            Что нужно для подключения
          </li>
        </ul>
      </div>
      <div className="pub-form-card">
        {done ? (
          <div role="status">
            <Check size={32} aria-hidden="true" />
            <h2>Заявка принята</h2>
            <p>Свяжемся с вами по указанной почте, чтобы согласовать встречу.</p>
            <p className="pub-caption">Номер заявки: {done}</p>
            <Button href="/start?plan=trial">Попробовать самостоятельно</Button>
          </div>
        ) : (
          <form onSubmit={submit}>
            <h2>{custom ? 'Обсудить условия' : 'Заказать демонстрацию'}</h2>
            <label>
              Ваше имя
              <input name="name" autoComplete="given-name" required maxLength={100} />
            </label>
            <label>
              Рабочая почта
              <input name="email" type="email" autoComplete="email" required maxLength={254} />
            </label>
            <label>
              Компания (необязательно)
              <input name="company" autoComplete="organization" maxLength={200} />
            </label>
            <label>
              Что хотите обсудить (необязательно)
              <textarea name="note" maxLength={2000} rows={3} />
            </label>
            <label className="pub-check">
              <input name="consent" type="checkbox" required />
              <span>
                Согласен на обработку данных для ответа на заявку.{' '}
                <a href="/privacy">Политика конфиденциальности</a>
              </span>
            </label>
            {error && (
              <p role="alert" className="pub-error">
                {error}
              </p>
            )}
            <button className="pub-button" disabled={busy}>
              {busy ? 'Сохраняем…' : 'Отправить заявку'}
              <ArrowRight size={18} />
            </button>
            <p className="pub-caption">Без рассылок и обязательств по покупке.</p>
          </form>
        )}
      </div>
    </section>
  );
}
function ContentPage({ kind }: { kind: string }) {
  const content: Record<
    string,
    { title: string; lead: string; items: { title: string; text: string }[] }
  > = {
    product: {
      title: 'Управляйте всем путём к оплате.',
      lead: 'От загрузки задолженности до юридического дела — с общими данными и понятным следующим действием.',
      items: features.map((f) => ({ title: f.title, text: f.text })),
    },
    solutions: {
      title: 'Каждому — своя работа. Всем — общая картина.',
      lead: 'Соберите бухгалтерию, руководителя и юриста вокруг одного дела, не меняя ответственность людей.',
      items: [
        {
          title: 'Для бухгалтера',
          text: 'Сверка остатков, разбор частичных оплат, поиск первичных документов и контроль обещанных дат. Исключения попадают в отдельную очередь.',
        },
        {
          title: 'Для руководителя',
          text: 'Правила общения, согласование новых условий, распределение ответственности и контроль портфеля.',
        },
        {
          title: 'Для юриста',
          text: 'Подтверждающие документы по каждому счёту, расчёт требований, проверка пакета и история судебных этапов.',
        },
      ],
    },
    integrations: {
      title: 'Данные из ваших рабочих систем.',
      lead: 'Начните с файлов. Для постоянного обмена используйте доступы вашей компании и проверку подключения.',
      items: [
        {
          title: 'Excel и CSV',
          text: 'Загружайте счета и банковские выписки. Перед сохранением проверьте ошибки и сопоставление полей.',
        },
        {
          title: '1С',
          text: 'Обмен учётными данными зависит от конфигурации и версии вашей 1С. Подключение проверяется вместе с ответственным за учётную систему.',
        },
        {
          title: 'Диадок',
          text: 'Используйте документы вашей организации по предоставленному доступу. Сначала проверьте организацию и права обмена.',
        },
        {
          title: 'Банк',
          text: 'Загрузите выписку файлом или согласуйте подключение доступного банковского API. Поступление уменьшает долг после сопоставления.',
        },
        {
          title: 'Почта и телефония',
          text: 'Работа через каналы вашей компании требует подключения и проверки. Расписание и границы автоматизации задаёт руководитель.',
        },
      ],
    },
    security: {
      title: 'Доступ и действия под контролем.',
      lead: 'Финансовые данные принадлежат вашей компании. Доступ к ним и внешним действиям должен быть осознанным.',
      items: [
        {
          title: 'Данные организаций разделены',
          text: 'Пользователи работают в пространстве своей организации. Права руководителя и бухгалтера определяют доступные действия.',
        },
        {
          title: 'Шифрованное соединение',
          text: 'Рабочий сайт использует HTTPS. Пароли хранятся в виде хешей; ключи подключений не передаются в браузер.',
        },
        {
          title: 'Внешние источники подключаются отдельно',
          text: 'LLM, распознавание документов, реестры и каналы общения используются в зависимости от настроек вашей организации. Состав обработки описан в политике конфиденциальности.',
        },
        {
          title: 'Подтверждённые финансовые события',
          text: 'Сообщение клиента об оплате не уменьшает долг. Поступление проверяется по данным банка и записывается в историю.',
        },
        {
          title: 'Управление данными',
          text: 'Можно выгрузить реестр и направить запрос на удаление данных. Подробности и ограничения хранения указаны в документах сервиса.',
        },
      ],
    },
  };
  const page = content[kind];
  return (
    <>
      <section className="pub-page-hero">
        <h1>{page.title}</h1>
        <p className="pub-lead">{page.lead}</p>
      </section>
      <section className="pub-section pub-detail-grid">
        {page.items.map((item) => (
          <article key={item.title}>
            <h2>{item.title}</h2>
            <p>{item.text}</p>
          </article>
        ))}
      </section>
    </>
  );
}

type Order = { id: string; plan_id: string; plan_name: string; amount: number; status: string };
type Account = {
  can_manage: boolean;
  status: string;
  plan: Plan | null;
  trial: { available: boolean; ends_at: string | null };
  subscription: { ends_at: string; auto_renew: boolean } | null;
  orders: Order[];
  deletion_request: { id: string; status: string } | null;
};
function Access() {
  const query = new URLSearchParams(location.search),
    accountPage = location.pathname.replace(/\/$/, '') === '/account',
    planId = query.get('plan') || 'trial',
    plan = plans.find((p) => p.id === planId);
  const [session, setSession] = useState<Session | null>(null),
    [checking, setChecking] = useState(true),
    [account, setAccount] = useState<Account | null>(null),
    [login, setLogin] = useState(query.get('mode') === 'login'),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [order, setOrder] = useState<Order | null>(null),
    [complete, setComplete] = useState(false),
    [cancel, setCancel] = useState(false);
  async function load(s: Session) {
    setCsrf(s.csrf_token);
    setSession(s);
    const next = await api<Account>('/commercial/account');
    setAccount(next);
    const requested = next.orders.find(
      (o) => o.id === query.get('order') && o.plan_id === planId && o.status === 'pending'
    );
    if (requested) setOrder(requested);
  }
  useEffect(() => {
    let active = true;
    api<{ session: Session | null }>('/auth/session')
      .then(async ({ session: s }) => {
        if (active && s) await load(s);
      })
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401)) setError((e as Error).message);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, []);
  async function authenticate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError('');
    const d = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await load(
        await post<Session>(
          `/auth/${login ? 'login' : 'register'}`,
          login
            ? { email: d.email, password: d.password }
            : {
                name: d.name,
                company: d.company,
                email: d.email,
                password: d.password,
                terms_accepted: true,
                terms_version: '2026-11-04',
              }
        )
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function checkoutStorageKey() {
    const previous =
      account?.orders.find((o) => o.plan_id === planId && o.status !== 'pending')?.id || 'first';
    return `mandato-order:${session?.user.id}:${planId}:${previous}`;
  }
  async function activate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (planId === 'trial') {
        setAccount(await post<Account>('/commercial/trial'));
        setComplete(true);
      } else {
        const existing = account?.orders.find(
          (o) => o.plan_id === planId && o.status === 'pending'
        );
        let key: string = crypto.randomUUID();
        const storageKey = checkoutStorageKey();
        try {
          key = sessionStorage.getItem(storageKey) || key;
          sessionStorage.setItem(storageKey, key);
        } catch {
          /* backend still protects each operation */
        }
        const next =
          existing ||
          (await post<Order>('/commercial/orders', {
            plan_id: planId,
            consent: true,
            idempotency_key: key,
          }));
        setOrder(next);
        const url = new URL(location.href);
        url.searchParams.set('order', next.id);
        history.replaceState({}, '', url);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!order) return;
    setBusy(true);
    setError('');
    try {
      const result = await post<{ account: Account }>(
        `/commercial/orders/${order.id}/sandbox-confirm`
      );
      setAccount(result.account);
      setComplete(true);
      try {
        sessionStorage.removeItem(checkoutStorageKey());
      } catch {
        /* optional browser state */
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancelAccess() {
    setBusy(true);
    setError('');
    try {
      setAccount(await post<Account>('/commercial/cancel', { consent: true }));
      setCancel(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const date = (s: string | null | undefined) =>
    s ? new Intl.DateTimeFormat('ru-RU').format(new Date(s)) : '—';
  if (checking)
    return (
      <section className="pub-access pub-access-loading" aria-busy="true">
        <div className="pub-access-intro">
          <p className="pub-eyebrow">Начало работы</p>
          <h1>
            {accountPage
              ? 'Тариф и данные компании'
              : planId === 'trial'
                ? 'Попробуйте на своём портфеле'
                : `Mandato ${plan?.name || ''}`}
          </h1>
          <p>
            {planId === 'trial'
              ? '14 дней бесплатно. Карта не нужна, автоматического продления нет.'
              : 'Подписка на месяц для одной организации. Дополнительные услуги согласуются отдельно.'}
          </p>
        </div>
        <div className="pub-form-card pub-loading-card">
          <p role="status">Проверяем вход…</p>
        </div>
      </section>
    );
  if (!accountPage && planId !== 'trial' && (!plan || plan.id === 'custom'))
    return (
      <section className="pub-page-hero">
        <h1>Выберите подходящий тариф</h1>
        <Button href="/pricing">Посмотреть условия</Button>
      </section>
    );
  return (
    <section className="pub-access">
      <div className="pub-access-intro">
        <p className="pub-eyebrow">{accountPage ? 'Ваш аккаунт' : 'Начало работы'}</p>
        <h1>
          {accountPage
            ? 'Тариф и данные компании.'
            : planId === 'trial'
              ? 'Попробуйте на своём портфеле.'
              : `Mandato ${plan?.name}`}
        </h1>
        <p>
          {accountPage
            ? 'Управляйте доступом и обращениями по данным.'
            : planId === 'trial'
              ? '14 дней бесплатно. Карта не нужна, автоматического продления нет.'
              : 'Подписка на месяц для одной организации. Дополнительные услуги согласуются отдельно.'}
        </p>
        {!accountPage && plan && (
          <div className="pub-order-summary">
            <strong>
              {money(plan.price_monthly || 0)} <span>/ месяц</span>
            </strong>
            <p>
              До {plan.active_invoice_limit} активных счетов · до {plan.user_limit} участников
            </p>
            <a href="/pricing">Сравнить тарифы</a>
          </div>
        )}
      </div>
      <div className="pub-form-card">
        {error && (
          <p className="pub-error" role="alert">
            {error}
          </p>
        )}
        {!session ? (
          <form onSubmit={authenticate}>
            <div className="pub-auth-tabs">
              <button
                type="button"
                aria-pressed={!login}
                onClick={() => {
                  setLogin(false);
                  setError('');
                }}
              >
                Создать аккаунт
              </button>
              <button
                type="button"
                aria-pressed={login}
                onClick={() => {
                  setLogin(true);
                  setError('');
                }}
              >
                Войти
              </button>
            </div>
            <h2>{login ? 'Войдите в аккаунт' : 'Создайте рабочее пространство'}</h2>
            {!login && (
              <>
                <label>
                  Ваше имя
                  <input name="name" autoComplete="given-name" required maxLength={100} />
                </label>
                <label>
                  Компания
                  <input name="company" autoComplete="organization" required maxLength={200} />
                </label>
              </>
            )}
            <label>
              Рабочая почта
              <input type="email" name="email" autoComplete="email" required maxLength={254} />
            </label>
            <label>
              Пароль
              <input
                aria-label="Пароль"
                type="password"
                name="password"
                minLength={login ? 1 : 12}
                maxLength={128}
                autoComplete={login ? 'current-password' : 'new-password'}
                required
              />
              {!login && <span className="pub-caption">Не менее 12 символов</span>}
            </label>
            {!login && (
              <label className="pub-check">
                <input type="checkbox" name="terms" required />
                <span>
                  Принимаю <a href="/terms">условия использования</a>. С{' '}
                  <a href="/privacy">политикой конфиденциальности</a> ознакомлен.
                </span>
              </label>
            )}
            <button className="pub-button" disabled={busy}>
              {busy ? 'Продолжаем…' : login ? 'Войти и продолжить' : 'Создать аккаунт и продолжить'}
              <ArrowRight size={18} />
            </button>
            {login && (
              <a href="/app?mode=login" className="pub-text-link">
                Восстановить доступ
              </a>
            )}
          </form>
        ) : !account ? (
          <>
            <h2>Не удалось загрузить условия</h2>
            <p>Повторите загрузку, чтобы проверить тариф и доступ.</p>
            <button
              className="pub-button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError('');
                try {
                  await load(session);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Повторить загрузку
            </button>
          </>
        ) : accountPage ? (
          <>
            <h2>{session.user.company}</h2>
            <p>{session.user.email}</p>
            <dl className="pub-account-details">
              <dt>Тариф</dt>
              <dd>{account?.plan?.name || 'Не выбран'}</dd>
              <dt>Доступ</dt>
              <dd>
                {
                  (
                    {
                      none: 'Не активирован',
                      trial: 'Бесплатный период',
                      trial_expired: 'Бесплатный период завершён',
                      sandbox_active: 'Открыт без оплаты',
                      sandbox_expired: 'Период завершён',
                      canceled: 'Отменён',
                    } as Record<string, string>
                  )[account?.status || 'none']
                }
              </dd>
              <dt>До</dt>
              <dd>{date(account?.subscription?.ends_at || account?.trial.ends_at)}</dd>
              <dt>Автопродление</dt>
              <dd>Выключено</dd>
            </dl>
            <div className="pub-account-actions">
              <a href="/app" className="pub-button">
                Перейти в кабинет <ArrowRight size={18} />
              </a>
              <a href="/pricing" className="pub-text-link">
                Выбрать тариф
              </a>
            </div>
            {account?.can_manage && (
              <>
                <hr />
                <h3>Управление доступом</h3>
                {cancel ? (
                  <div className="pub-confirm">
                    <p>
                      Завершить текущий доступ? Рабочие записи сохранятся. Новых списаний не будет.
                    </p>
                    <div className="pub-inline-actions">
                      <button disabled={busy} onClick={cancelAccess}>
                        Подтвердить отмену
                      </button>
                      <button onClick={() => setCancel(false)}>Вернуться</button>
                    </div>
                  </div>
                ) : (
                  <button className="pub-text-button" onClick={() => setCancel(true)}>
                    Отменить подписку или пробный период
                  </button>
                )}
              </>
            )}
            <hr />
            <h3>Данные организации</h3>
            <p>Запрос на удаление данных можно отправить в настройках рабочего кабинета.</p>
            <a className="pub-text-link" href="/app?mode=login&section=settings#workspace-data">
              Управлять данными в настройках <ArrowRight size={18} aria-hidden="true" />
            </a>
          </>
        ) : complete ||
          (planId === 'trial' && account?.status === 'trial') ||
          (account?.status === 'sandbox_active' && account.plan?.id === planId) ? (
          <div role="status">
            <Check size={32} aria-hidden="true" />
            <h2>Можно начинать работу</h2>
            <p>
              {planId === 'trial'
                ? `Бесплатный период действует до ${date(account?.trial.ends_at)}.`
                : 'Доступ открыт без списания денег. Автоматического продления нет.'}
            </p>
            <div className="pub-account-actions">
              <Button href="/app">Перейти в кабинет</Button>
              <a href="/account">Тариф и данные аккаунта</a>
            </div>
          </div>
        ) : !account?.can_manage ? (
          <>
            <h2>Подпиской управляет руководитель</h2>
            <p>Попросите руководителя организации выбрать тариф.</p>
            <Button href="/app">Открыть кабинет</Button>
          </>
        ) : order ? (
          <>
            <h2>Подтвердите подключение</h2>
            <dl className="pub-account-details">
              <dt>Тариф</dt>
              <dd>{order.plan_name}</dd>
              <dt>Стоимость за месяц</dt>
              <dd>{money(order.amount)}</dd>
              <dt>Продление</dt>
              <dd>Только по вашему решению</dd>
            </dl>
            <div className="pub-notice">
              <strong>Сейчас без списания</strong>
              <p>
                Платёжный сервис ещё не подключён. Продолжая, вы открываете доступ без оплаты.
                Данные карты не нужны.
              </p>
            </div>
            <button className="pub-button" disabled={busy} onClick={confirm}>
              {busy ? 'Открываем доступ…' : 'Продолжить без оплаты'}
              <ArrowRight size={18} />
            </button>
            <a href="/pricing" className="pub-text-link">
              Вернуться к тарифам
            </a>
          </>
        ) : planId === 'trial' && !account.trial.available ? (
          <>
            <h2>Бесплатный период уже использован</h2>
            <p>Посмотрите текущий доступ или выберите тариф для продолжения работы.</p>
            <Button href="/account">Мой аккаунт</Button>
            <a href="/pricing" className="pub-text-link">
              Выбрать тариф
            </a>
          </>
        ) : (
          <form onSubmit={activate}>
            <h2>{planId === 'trial' ? '14 дней бесплатно' : `Подключить «${plan?.name}»`}</h2>
            <p>
              {planId === 'trial'
                ? 'Попробуйте реестр, аудит, сверку и работу команды. По окончании срока деньги не спишутся.'
                : 'На следующем шаге проверите условия подключения. Списаний без подтверждения не будет.'}
            </p>
            <label className="pub-check">
              <input type="checkbox" required />
              <span>
                Принимаю <a href="/terms">условия подключения</a> и{' '}
                <a href="/refunds">правила отмены и возврата</a>.
              </span>
            </label>
            <button className="pub-button" disabled={busy}>
              {busy
                ? 'Подготавливаем…'
                : planId === 'trial'
                  ? 'Начать бесплатный период'
                  : 'Продолжить оформление'}
              <ArrowRight size={18} />
            </button>
            <a href="/account" className="pub-text-link">
              Мой тариф и доступ
            </a>
          </form>
        )}
      </div>
    </section>
  );
}
export function PublicSite() {
  const path = location.pathname.replace(/\/$/, '') || '/';
  const kind = path.slice(1);
  useEffect(() => {
    const names: Record<string, string> = {
      '/': 'Дебиторка от счёта до оплаты',
      '/pricing': 'Цены и тарифы',
      '/demo': 'Демонстрация',
      '/start': 'Начать работу',
      '/account': 'Тариф и аккаунт',
      '/product': 'Продукт',
      '/solutions': 'Для вашей команды',
      '/integrations': 'Подключения',
      '/security': 'Безопасность',
    };
    document.title = `${names[path] || 'Информация о сервисе'} — Mandato`;
  }, [path]);
  useEffect(() => {
    if (
      window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
      !('IntersectionObserver' in window)
    )
      return;
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('pub-revealed');
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.08 }
    );
    document
      .querySelectorAll('#public-main > section, #public-main > .story-page > section')
      .forEach((section) => {
        section.classList.add('pub-reveal');
        observer.observe(section);
      });
    return () => observer.disconnect();
  }, [path]);
  if (legalRoutes[path])
    return (
      <div className="public-site">
        <PublicLegal kind={legalRoutes[path] as PublicLegalKind} />
        <CookieNotice />
      </div>
    );
  return (
    <div className="public-site">
      <a className="pub-skip" href="#public-main">
        К содержимому
      </a>
      <Header />
      <main id="public-main" tabIndex={-1}>
        {path === '/' ? (
          <Home />
        ) : path === '/pricing' ? (
          <Pricing />
        ) : path === '/demo' ? (
          <RequestDemo />
        ) : path === '/start' || path === '/account' ? (
          <Access />
        ) : legalRoutes[path] ? (
          <PublicLegal kind={legalRoutes[path] as PublicLegalKind} />
        ) : kind === 'product' || kind === 'solutions' || kind === 'integrations' ? (
          <PublicStoryPages kind={kind} />
        ) : kind === 'security' ? (
          <ContentPage kind={kind} />
        ) : (
          <section className="pub-page-hero">
            <h1>Страница не найдена</h1>
            <a className="pub-text-link" href="/">
              Вернуться на главную
            </a>
          </section>
        )}
      </main>
      <Footer />
      <CookieNotice />
    </div>
  );
}
