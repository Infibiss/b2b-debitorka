import { tariff } from '../pricing';
import { LanguageSwitch } from './LanguageSwitch';
import { locale, t } from '../i18n';
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
import { legalEntityLine, PublicLegal, type PublicLegalKind } from './PublicLegal';
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
  '/consent': 'consent',
};
const nav = [
  [t('Продукт'), '/product'],
  [t('Для вашей команды'), '/solutions'],
  [t('Подключения'), '/integrations'],
  [t('Цены'), '/pricing'],
];
const features = [
  {
    icon: Layers,
    title: t('Один портфель вместо разрозненных таблиц'),
    text: t(
      'Счета, договоры и частичные оплаты собраны по клиенту. Видно, сколько осталось получить и что мешает оплате.'
    ),
  },
  {
    icon: MessagesSquare,
    title: t('Напоминания без ежедневной ручной работы'),
    text: t(
      'Задайте расписание и правила общения. Mandato следит за сроками, а споры и новые условия передаёт ответственному.'
    ),
  },
  {
    icon: Landmark,
    title: t('Оплата подтверждается поступлением'),
    text: t(
      'Сверяйте выписку со счетами. Обещание клиента остаётся обещанием, пока деньги не поступят.'
    ),
  },
  {
    icon: FileText,
    title: t('Юридическая работа продолжает историю дела'),
    text: t(
      'Соберите документы, рассчитайте требования и передайте пакет юристу. Переписку и основания не придётся искать заново.'
    ),
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
      <LanguageSwitch />
      <button
        className="pub-mobile-menu"
        aria-label={open ? t('Закрыть меню') : t('Открыть меню')}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? <X /> : <Menu />}
      </button>
      <nav className={open ? 'is-open' : ''} aria-label={t('Основная навигация')}>
        {nav.map(([label, href]) => (
          <a key={href} href={href} aria-current={location.pathname === href ? 'page' : undefined}>
            {label}
          </a>
        ))}
        <a className="pub-login" href="/app?mode=login">
          {t('Войти')} <ArrowUpRight size={16} aria-hidden="true" />
        </a>
        <a className="pub-nav-demo" href="/demo">
          {t('Заказать демонстрацию')}
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
        <small className="pub-legal-line">{legalEntityLine}</small>
      </div>
      <nav aria-label={t('Информация о сервисе')}>
        <a href="/security">{t('Безопасность')}</a>
        <a href="/company">{t('О компании')}</a>
        <a href="/privacy">{t('Конфиденциальность')}</a>
        <a href="/terms">{t('Условия использования')}</a>
        <a href="/refunds">{t('Возврат средств')}</a>
        <a href="/cookies">{t('Файлы cookie')}</a>
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
    <aside className="pub-cookie" aria-label={t('Использование cookie')}>
      <p>
        {t('Используем необходимые cookie для входа и безопасности.')}{' '}
        <a href="/cookies">{t('Подробнее')}</a>
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
        {t('Понятно')}
      </button>
    </aside>
  ) : null;
}
function Home() {
  return (
    <>
      <section className="pub-hero">
        <h1>
          {t('Ведите дебиторку')}
          <br />
          <span>{t('от счёта до оплаты')}</span>
        </h1>
        <p className="pub-lead">
          {t(
            'Управляйте задолженностью от первого счёта до поступления денег. Mandato связывает бухгалтерию, общение с клиентом и юридическую работу в одном процессе.'
          )}
        </p>
        <div className="pub-actions">
          <Button href="/demo">{t('Заказать демонстрацию')}</Button>
          <Button href="/start?plan=trial" secondary>
            {t('Попробовать бесплатно')}
          </Button>
        </div>
        <p className="pub-caption">{t('14 дней без карты и автоматического продления')}</p>
      </section>
      <PublicProcess />
      <section className="pub-section">
        <div className="pub-section-title">
          <h2>
            {t('Не упускайте деньги')}
            <br />
            {t('между отделами.')}
          </h2>
          <p>
            {t(
              'Когда каждый видит свою часть работы, задолженность движется к оплате. Общая история помогает команде действовать согласованно.'
            )}
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
          {t('Одна система')}
          <br />
          {t('Понятная роль для каждого')}
        </h2>
        <div className="pub-three">
          <article>
            <span>{t('Бухгалтерия')}</span>
            <h3>{t('Точные суммы и документы')}</h3>
            <p>
              {t(
                'Разбирайте поступления и расхождения, находите недостающие документы и передавайте подготовленное дело дальше.'
              )}
            </p>
          </article>
          <article>
            <span>{t('Руководитель')}</span>
            <h3>{t('Решения без потери контроля')}</h3>
            <p>
              {t(
                'Определяйте правила, согласуйте скидки и рассрочки. Видно, какие долги требуют участия команды.'
              )}
            </p>
          </article>
          <article>
            <span>{t('Юрист')}</span>
            <h3>{t('История, готовая к работе')}</h3>
            <p>
              {t(
                'Договор, счета, доказательства и переписка собраны вместе. Проверяйте требования и ведите дальнейшие этапы взыскания.'
              )}
            </p>
          </article>
        </div>
      </section>
      <section className="pub-section pub-connections">
        <div>
          <h2>
            {t('Начните с реестра')}
            <br />
            {t('Подключайте источники по мере готовности')}
          </h2>
          <p>
            {t(
              'Загрузите таблицу, чтобы увидеть портфель. Для регулярного обмена подключите вашу учётную систему, документы и банк.'
            )}
          </p>
          <a className="pub-text-link" href="/integrations">
            {t('Как устроены подключения')} <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
        <div className="pub-source-list">
          {[
            [t('Excel и CSV'), t('Загрузка счетов и выписок')],
            [t('1С'), t('Данные учёта и сверка')],
            [t('Диадок'), t('Документы по сделкам')],
            [t('Банк'), t('Подтверждение поступлений')],
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
          <h2 id="pub-final-cta-title">{t('Начните получать оплату вовремя')}</h2>
          <p>
            {t(
              'Соберите задолженность в одном реестре, определите следующий шаг и держите договорённости с клиентами под контролем.'
            )}
          </p>
        </div>
        <div className="pub-final-cta-action">
          <p>{t('14 дней бесплатно')}</p>
          <Button href="/start?plan=trial">{t('Попробовать бесплатно')}</Button>
          <span>{t('Без карты и автоматического продления')}</span>
        </div>
      </section>
    </>
  );
}
function Pricing() {
  return (
    <>
      <section className="pub-page-hero pub-pricing-hero">
        <h1>{t('Тарифы для вашей команды')}</h1>
        <p className="pub-lead">
          {t(
            'Ежемесячная подписка для вашей команды. Начните с 14 дней бесплатно — без карты и автоматического списания.'
          )}
        </p>
        <Button href="/start?plan=trial">{t('Начать бесплатный период')}</Button>
      </section>
      <section className="pub-pricing-grid" aria-label={t('Тарифы Mandato')}>
        {plans.map((plan, i) => (
          <article className={i === 1 ? 'is-featured' : ''} key={plan.id}>
            <div className="pub-plan-name">
              <h2>{plan.name}</h2>
              {i === 1 && <span>{t('Для совместной работы')}</span>}
            </div>
            <p className="pub-plan-price">
              {plan.price_monthly === null ? t('По договору') : money(plan.price_monthly)}
              {plan.price_monthly !== null && <span>{t('в месяц за организацию')}</span>}
            </p>
            <p>
              {
                [
                  t('Для небольшого портфеля и одного ответственного.'),
                  t('Для бухгалтерии и руководителя с общей очередью дел.'),
                  t('Для большой команды и регулярной работы с задолженностью.'),
                  t('Для группы компаний и особых требований к подключению.'),
                ][i]
              }
            </p>
            <p className="pub-plan-capacity">
              {plan.active_invoice_limit
                ? t('До {0} активных счетов · {1} {2}', [
                    plan.active_invoice_limit.toLocaleString(locale),
                    plan.user_limit,
                    plan.user_limit === 2 ? 'участника' : 'участников',
                  ])
                : t('Объём портфеля и команда — по договору')}
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
              {plan.id === 'custom' ? t('Обсудить условия') : t('Выбрать «{0}»', [plan.name])}
            </Button>
          </article>
        ))}
      </section>
      <section className="pub-section">
        <div className="pub-section-title">
          <h2>{t('Сравните условия')}</h2>
          <p>
            {t(
              'В пробном периоде доступны все инструменты. Одна организация — одна подписка. Каждый следующий тариф включает предыдущий. Подключение внешних систем и услуги взыскания согласуются отдельно до начала работы.'
            )}
          </p>
        </div>
        <div className="pub-table-scroll">
          <table className="pub-compare">
            <caption>{t('Состав подписки по тарифам')}</caption>
            <thead>
              <tr>
                <th scope="col">{t('Возможности')}</th>
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
                  t('Активные счета'),
                  ...plans.map(
                    (p) => p.active_invoice_limit?.toLocaleString(locale) || t('По договору')
                  ),
                ],
                [
                  t('Участники команды'),
                  ...plans.map((p) => String(p.user_limit || t('По договору'))),
                ],
                [
                  t('Реестр должников и документы'),
                  t('Включено'),
                  t('Включено'),
                  t('Включено'),
                  t('Включено'),
                ],
                [
                  t('Оплаты, частичные платежи и сверка'),
                  t('Включено'),
                  t('Включено'),
                  t('Включено'),
                  t('Включено'),
                ],
                [
                  t('Напоминания и история общения'),
                  t('Включено'),
                  t('Включено'),
                  t('Включено'),
                  t('Включено'),
                ],
                [
                  t('Роли и согласование условий'),
                  '—',
                  t('Включено'),
                  t('Включено'),
                  t('Включено'),
                ],
                [t('Договорённости и рассрочки'), '—', t('Включено'), t('Включено'), t('Включено')],
                [t('Юридические дела и расчёт требований'), '—', '—', t('Включено'), t('Включено')],
                [
                  t('Подготовка претензии и судебного пакета'),
                  '—',
                  '—',
                  t('Включено'),
                  t('Включено'),
                ],
                [t('Особые требования к внедрению'), '—', '—', '—', t('По договору')],
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
        <h2>{t('Услуги взыскания — отдельно')}</h2>
        <div className="pub-three">
          <article>
            <h3>{t('{0}% от поступлений', [tariff.pretrial_percent])}</h3>
            <p>
              {t(
                'После направления претензии и до подачи заявления в суд. Оплата с фактически поступивших денег.'
              )}
            </p>
          </article>
          <article>
            <h3>
              {(tariff.court_order_amount / 100).toLocaleString(locale)} /{' '}
              {(tariff.statement_of_claim_amount / 100).toLocaleString(locale)} ₽
            </h3>
            <p>
              {t(
                'За подготовленный и поданный пакет судебного приказа или иска, независимо от результата взыскания.'
              )}
            </p>
          </article>
          <article>
            <h3>{t('Адвокату — 12%')}</h3>
            <p>
              {t(
                'От поступлений после подачи в суд, по прямому соглашению с клиентом. Эта сумма не входит в вознаграждение Mandato.'
              )}
            </p>
          </article>
        </div>
        <p>
          {t(
            'Госпошлина оплачивается отдельно; её возмещение с должника не гарантируется. Заявление в банк по исполнительному листу бесплатно. Условия и лимиты голосовых минут фиксируются в договоре. Деньги должника поступают напрямую вам.'
          )}
        </p>
        <a href="/refunds" className="pub-text-link">
          {t('Отмена подписки и возврат средств')} <ArrowRight size={18} aria-hidden="true" />
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
          {custom ? t('Индивидуальные условия') : t('Личное знакомство с Mandato')}
        </p>
        <h1>
          {custom ? t('Подключение под вашу компанию.') : t('Покажем работу на вашем сценарии.')}
        </h1>
        <p className="pub-lead">
          {custom
            ? t('Обсудим объём портфеля, состав команды и требования к обмену данными.')
            : t(
                'Пройдём путь от загрузки реестра до сверки оплаты. Обсудим работу бухгалтерии, руководителя и юриста.'
              )}
        </p>
        <ul className="pub-check-list">
          <li>
            <Check aria-hidden="true" />
            {t('Как устроена очередь дел')}
          </li>
          <li>
            <Check aria-hidden="true" />
            {t('Где помогает автоматизация')}
          </li>
          <li>
            <Check aria-hidden="true" />
            {t('Что нужно для подключения')}
          </li>
        </ul>
      </div>
      <div className="pub-form-card">
        {done ? (
          <div role="status">
            <Check size={32} aria-hidden="true" />
            <h2>{t('Заявка принята')}</h2>
            <p>{t('Свяжемся с вами по указанной почте, чтобы согласовать встречу.')}</p>
            <p className="pub-caption">
              {t('Номер заявки:')} {done}
            </p>
            <Button href="/start?plan=trial">{t('Попробовать самостоятельно')}</Button>
          </div>
        ) : (
          <form onSubmit={submit}>
            <h2>{custom ? t('Обсудить условия') : t('Заказать демонстрацию')}</h2>
            <label>
              {t('Ваше имя')}
              <input name="name" autoComplete="given-name" required maxLength={100} />
            </label>
            <label>
              {t('Рабочая почта')}
              <input name="email" type="email" autoComplete="email" required maxLength={254} />
            </label>
            <label>
              {t('Компания (необязательно)')}
              <input name="company" autoComplete="organization" maxLength={200} />
            </label>
            <label>
              {t('Что хотите обсудить (необязательно)')}
              <textarea name="note" maxLength={2000} rows={3} />
            </label>
            <label className="pub-check">
              <input name="consent" type="checkbox" required />
              <span>
                {t('Даю')}{' '}
                <a href="/consent" target="_blank" rel="noreferrer">
                  {t('согласие на обработку персональных данных')}
                </a>{' '}
                {t('для ответа на заявку.')}
              </span>
            </label>
            {error && (
              <p role="alert" className="pub-error">
                {error}
              </p>
            )}
            <button className="pub-button" disabled={busy}>
              {busy ? t('Сохраняем…') : t('Отправить заявку')}
              <ArrowRight size={18} />
            </button>
            <p className="pub-caption">{t('Без рассылок и обязательств по покупке.')}</p>
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
      title: t('Управляйте всем путём к оплате.'),
      lead: t(
        'От загрузки задолженности до юридического дела — с общими данными и понятным следующим действием.'
      ),
      items: features.map((f) => ({ title: f.title, text: f.text })),
    },
    solutions: {
      title: t('Каждому — своя работа. Всем — общая картина.'),
      lead: t(
        'Соберите бухгалтерию, руководителя и юриста вокруг одного дела, не меняя ответственность людей.'
      ),
      items: [
        {
          title: t('Для бухгалтера'),
          text: t(
            'Сверка остатков, разбор частичных оплат, поиск первичных документов и контроль обещанных дат. Исключения попадают в отдельную очередь.'
          ),
        },
        {
          title: t('Для руководителя'),
          text: t(
            'Правила общения, согласование новых условий, распределение ответственности и контроль портфеля.'
          ),
        },
        {
          title: t('Для юриста'),
          text: t(
            'Подтверждающие документы по каждому счёту, расчёт требований, проверка пакета и история судебных этапов.'
          ),
        },
      ],
    },
    integrations: {
      title: t('Данные из ваших рабочих систем.'),
      lead: t(
        'Начните с файлов. Для постоянного обмена используйте доступы вашей компании и проверку подключения.'
      ),
      items: [
        {
          title: t('Excel и CSV'),
          text: t(
            'Загружайте счета и банковские выписки. Перед сохранением проверьте ошибки и сопоставление полей.'
          ),
        },
        {
          title: t('1С'),
          text: t(
            'Обмен учётными данными зависит от конфигурации и версии вашей 1С. Подключение проверяется вместе с ответственным за учётную систему.'
          ),
        },
        {
          title: t('Диадок'),
          text: t(
            'Используйте документы вашей организации по предоставленному доступу. Сначала проверьте организацию и права обмена.'
          ),
        },
        {
          title: t('Банк'),
          text: t(
            'Загрузите выписку файлом или согласуйте подключение доступного банковского API. Поступление уменьшает долг после сопоставления.'
          ),
        },
        {
          title: t('Почта и телефония'),
          text: t(
            'Работа через каналы вашей компании требует подключения и проверки. Расписание и границы автоматизации задаёт руководитель.'
          ),
        },
      ],
    },
    security: {
      title: t('Доступ и действия под контролем.'),
      lead: t(
        'Финансовые данные принадлежат вашей компании. Доступ к ним и внешним действиям должен быть осознанным.'
      ),
      items: [
        {
          title: t('Данные организаций разделены'),
          text: t(
            'Пользователи работают в пространстве своей организации. Права руководителя и бухгалтера определяют доступные действия.'
          ),
        },
        {
          title: t('Шифрованное соединение'),
          text: t(
            'Рабочий сайт использует HTTPS. Пароли хранятся в виде хешей; ключи подключений не передаются в браузер.'
          ),
        },
        {
          title: t('Внешние источники подключаются отдельно'),
          text: t(
            'Языковые модели, реестры и каналы общения используются в зависимости от настроек вашей организации. Состав обработки описан в политике конфиденциальности.'
          ),
        },
        {
          title: t('Подтверждённые финансовые события'),
          text: t(
            'Сообщение клиента об оплате не уменьшает долг. Поступление проверяется по данным банка и записывается в историю.'
          ),
        },
        {
          title: t('Управление данными'),
          text: t(
            'Можно выгрузить реестр и направить запрос на удаление данных. Подробности и ограничения хранения указаны в документах сервиса.'
          ),
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
                terms_version: '2026-11-08',
                personal_data_consent: true,
                consent_version: '2026-11-08',
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
      const result = await post<{ account: Account }>(`/commercial/orders/${order.id}/confirm`);
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
          <p className="pub-eyebrow">{t('Начало работы')}</p>
          <h1>
            {accountPage
              ? t('Тариф и данные компании')
              : planId === 'trial'
                ? t('Попробуйте на своём портфеле')
                : `Mandato ${plan?.name || ''}`}
          </h1>
          <p>
            {planId === 'trial'
              ? t('14 дней бесплатно. Карта не нужна, автоматического продления нет.')
              : t(
                  'Подписка на месяц для одной организации. Дополнительные услуги согласуются отдельно.'
                )}
          </p>
        </div>
        <div className="pub-form-card pub-loading-card">
          <p role="status">{t('Проверяем вход…')}</p>
        </div>
      </section>
    );
  if (!accountPage && planId !== 'trial' && (!plan || plan.id === 'custom'))
    return (
      <section className="pub-page-hero">
        <h1>{t('Выберите подходящий тариф')}</h1>
        <Button href="/pricing">{t('Посмотреть условия')}</Button>
      </section>
    );
  return (
    <section className="pub-access">
      <div className="pub-access-intro">
        <p className="pub-eyebrow">{accountPage ? t('Ваш аккаунт') : t('Начало работы')}</p>
        <h1>
          {accountPage
            ? t('Тариф и данные компании.')
            : planId === 'trial'
              ? t('Попробуйте на своём портфеле.')
              : `Mandato ${plan?.name}`}
        </h1>
        <p>
          {accountPage
            ? t('Управляйте доступом и обращениями по данным.')
            : planId === 'trial'
              ? t('14 дней бесплатно. Карта не нужна, автоматического продления нет.')
              : t(
                  'Подписка на месяц для одной организации. Дополнительные услуги согласуются отдельно.'
                )}
        </p>
        {!accountPage && plan && (
          <div className="pub-order-summary">
            <strong>
              {money(plan.price_monthly || 0)} <span>{t('/ месяц')}</span>
            </strong>
            <p>
              {t('До')} {plan.active_invoice_limit} {t('активных счетов · до')} {plan.user_limit}{' '}
              {t('участников')}
            </p>
            <a href="/pricing">{t('Сравнить тарифы')}</a>
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
                {t('Создать аккаунт')}
              </button>
              <button
                type="button"
                aria-pressed={login}
                onClick={() => {
                  setLogin(true);
                  setError('');
                }}
              >
                {t('Войти')}
              </button>
            </div>
            <h2>{login ? t('Войдите в аккаунт') : t('Создайте рабочее пространство')}</h2>
            {!login && (
              <>
                <label>
                  {t('Ваше имя')}
                  <input name="name" autoComplete="given-name" required maxLength={100} />
                </label>
                <label>
                  {t('Компания')}
                  <input name="company" autoComplete="organization" required maxLength={200} />
                </label>
              </>
            )}
            <label>
              {t('Рабочая почта')}
              <input type="email" name="email" autoComplete="email" required maxLength={254} />
            </label>
            <label>
              {t('Пароль')}
              <input
                aria-label={t('Пароль')}
                type="password"
                name="password"
                minLength={login ? 1 : 12}
                maxLength={128}
                autoComplete={login ? 'current-password' : 'new-password'}
                required
              />
              {!login && <span className="pub-caption">{t('Не менее 12 символов')}</span>}
            </label>
            {!login && (
              <>
                <label className="pub-check">
                  <input type="checkbox" name="terms" required />
                  <span>
                    {t(
                      'Мне исполнилось 18 лет, я уполномочен работать от имени компании и принимаю'
                    )}{' '}
                    <a href="/terms">{t('условия использования')}</a>.
                  </span>
                </label>
                <label className="pub-check">
                  <input type="checkbox" name="personal_data" required />
                  <span>
                    {t('Даю')}{' '}
                    <a href="/consent" target="_blank" rel="noreferrer">
                      {t('согласие на обработку персональных данных')}
                    </a>
                    .
                  </span>
                </label>
              </>
            )}
            <button className="pub-button" disabled={busy}>
              {busy
                ? t('Продолжаем…')
                : login
                  ? t('Войти и продолжить')
                  : t('Создать аккаунт и продолжить')}
              <ArrowRight size={18} />
            </button>
            {login && (
              <a href="/app?mode=login" className="pub-text-link">
                {t('Восстановить доступ')}
              </a>
            )}
          </form>
        ) : !account ? (
          <>
            <h2>{t('Не удалось загрузить условия')}</h2>
            <p>{t('Повторите загрузку, чтобы проверить тариф и доступ.')}</p>
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
              {t('Повторить загрузку')}
            </button>
          </>
        ) : accountPage ? (
          <>
            <h2>{session.user.company}</h2>
            <p>{session.user.email}</p>
            <dl className="pub-account-details">
              <dt>{t('Тариф')}</dt>
              <dd>{account?.plan?.name || t('Не выбран')}</dd>
              <dt>{t('Доступ')}</dt>
              <dd>
                {
                  (
                    {
                      none: t('Не активирован'),
                      trial: t('Бесплатный период'),
                      trial_expired: t('Бесплатный период завершён'),
                      active: t('Подключён'),
                      expired: t('Период завершён'),
                      canceled: t('Отменён'),
                    } as Record<string, string>
                  )[account?.status || 'none']
                }
              </dd>
              <dt>{t('До')}</dt>
              <dd>{date(account?.subscription?.ends_at || account?.trial.ends_at)}</dd>
              <dt>{t('Автопродление')}</dt>
              <dd>{t('Выключено')}</dd>
            </dl>
            <div className="pub-account-actions">
              <a href="/app" className="pub-button">
                {t('Перейти в кабинет')} <ArrowRight size={18} />
              </a>
              <a href="/pricing" className="pub-text-link">
                {t('Выбрать тариф')}
              </a>
            </div>
            {account?.can_manage && (
              <>
                <hr />
                <h3>{t('Управление доступом')}</h3>
                {cancel ? (
                  <div className="pub-confirm">
                    <p>
                      {t(
                        'Завершить текущий доступ? Рабочие записи сохранятся. Новых списаний не будет.'
                      )}
                    </p>
                    <div className="pub-inline-actions">
                      <button disabled={busy} onClick={cancelAccess}>
                        {t('Подтвердить отмену')}
                      </button>
                      <button onClick={() => setCancel(false)}>{t('Вернуться')}</button>
                    </div>
                  </div>
                ) : (
                  <button className="pub-text-button" onClick={() => setCancel(true)}>
                    {t('Отменить подписку или пробный период')}
                  </button>
                )}
              </>
            )}
            <hr />
            <h3>{t('Данные организации')}</h3>
            <p>{t('Запрос на удаление данных можно отправить в настройках рабочего кабинета.')}</p>
            <a
              className="pub-text-link"
              href="/app?mode=login&section=settings&settingsTab=mail#workspace-data"
            >
              {t('Управлять данными в настройках')} <ArrowRight size={18} aria-hidden="true" />
            </a>
          </>
        ) : complete ||
          (planId === 'trial' && account?.status === 'trial') ||
          (account?.status === 'active' && account.plan?.id === planId) ? (
          <div role="status">
            <Check size={32} aria-hidden="true" />
            <h2>{t('Можно начинать работу')}</h2>
            <p>
              {planId === 'trial'
                ? t('Бесплатный период действует до {0}.', [date(account?.trial.ends_at)])
                : t('Доступ открыт без списания денег. Автоматического продления нет.')}
            </p>
            <div className="pub-account-actions">
              <Button href="/app">{t('Перейти в кабинет')}</Button>
              <a href="/account">{t('Тариф и данные аккаунта')}</a>
            </div>
          </div>
        ) : !account?.can_manage ? (
          <>
            <h2>{t('Подпиской управляет руководитель')}</h2>
            <p>{t('Попросите руководителя организации выбрать тариф.')}</p>
            <Button href="/app">{t('Открыть кабинет')}</Button>
          </>
        ) : order ? (
          <>
            <h2>{t('Подтвердите подключение')}</h2>
            <dl className="pub-account-details">
              <dt>{t('Тариф')}</dt>
              <dd>{order.plan_name}</dd>
              <dt>{t('Стоимость за месяц')}</dt>
              <dd>{money(order.amount)}</dd>
              <dt>{t('Продление')}</dt>
              <dd>{t('Только по вашему решению')}</dd>
            </dl>
            <div className="pub-notice">
              <strong>{t('Оплата по счёту')}</strong>
              <p>
                {t(
                  'Доступ откроется сразу, а счёт для оплаты мы пришлём на почту аккаунта. Данные карты не нужны.'
                )}
              </p>
            </div>
            <button className="pub-button" disabled={busy} onClick={confirm}>
              {busy ? t('Открываем доступ…') : t('Подключить и получить счёт')}
              <ArrowRight size={18} />
            </button>
            <a href="/pricing" className="pub-text-link">
              {t('Вернуться к тарифам')}
            </a>
          </>
        ) : planId === 'trial' && !account.trial.available ? (
          <>
            <h2>{t('Бесплатный период уже использован')}</h2>
            <p>{t('Посмотрите текущий доступ или выберите тариф для продолжения работы.')}</p>
            <Button href="/account">{t('Мой аккаунт')}</Button>
            <a href="/pricing" className="pub-text-link">
              {t('Выбрать тариф')}
            </a>
          </>
        ) : (
          <form onSubmit={activate}>
            <h2>
              {planId === 'trial' ? t('14 дней бесплатно') : t('Подключить «{0}»', [plan?.name])}
            </h2>
            <p>
              {planId === 'trial'
                ? t(
                    'Попробуйте работу с должниками, сверку и работу команды. По окончании срока деньги не спишутся.'
                  )
                : t(
                    'На следующем шаге проверите условия подключения. Списаний без подтверждения не будет.'
                  )}
            </p>
            <label className="pub-check">
              <input type="checkbox" required />
              <span>
                {t('Принимаю')} <a href="/terms">{t('условия подключения')}</a> {t('и')}{' '}
                <a href="/refunds">{t('правила отмены и возврата')}</a>.
              </span>
            </label>
            <button className="pub-button" disabled={busy}>
              {busy
                ? t('Подготавливаем…')
                : planId === 'trial'
                  ? t('Начать бесплатный период')
                  : t('Продолжить оформление')}
              <ArrowRight size={18} />
            </button>
            <a href="/account" className="pub-text-link">
              {t('Мой тариф и доступ')}
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
      '/': t('Дебиторка от счёта до оплаты'),
      '/pricing': t('Цены и тарифы'),
      '/demo': t('Демонстрация'),
      '/start': t('Начать работу'),
      '/account': t('Тариф и аккаунт'),
      '/product': t('Продукт'),
      '/solutions': t('Для вашей команды'),
      '/integrations': t('Подключения'),
      '/security': t('Безопасность'),
    };
    document.title = `${names[path] || t('Информация о сервисе')} — Mandato`;
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
        {t('К содержимому')}
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
            <h1>{t('Страница не найдена')}</h1>
            <a className="pub-text-link" href="/">
              {t('Вернуться на главную')}
            </a>
          </section>
        )}
      </main>
      <Footer />
      <CookieNotice />
    </div>
  );
}
