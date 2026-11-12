import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Gavel, Landmark, MailCheck, Check, X } from 'lucide-react';
import { t } from '../i18n';
import { post } from '../api';
import { LanguageSwitch } from './LanguageSwitch';
import { legalEntityLine } from './PublicLegal';
import './landing.css';

const mainNav = [
  [t('Продукт'), '/product'],
  [t('Для команд'), '/solutions'],
  [t('Подключения'), '/integrations'],
  [t('Цены'), '/pricing'],
];
const CONTACT_EVENT = 'mandato:contact';
const openContact = () => window.dispatchEvent(new Event(CONTACT_EVENT));

type Smooth = {
  raf: (time: number) => void;
  destroy: () => void;
  stop: () => void;
  start: () => void;
};
let smooth: Smooth | null = null;

function lockScroll(locked: boolean) {
  document.documentElement.classList.toggle('scroll-locked', locked);
  if (locked) smooth?.stop();
  else smooth?.start();
}

function Mark() {
  return (
    <svg viewBox="0 0 32 32" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M20.3 3.8C13.2 1.3 5.5 5.4 3.5 12.7C1.3 20.7 6.8 28.8 14.9 29.6C23.1 30.4 29.8 24.3 29.8 16.3C29.8 12.2 28.1 8.5 25.2 6.1C24.4 5.4 23.3 5.5 22.6 6.2L19.4 9.5C18.8 10.1 19.2 11.1 20.1 11.2L23.4 11.5C24.2 12.9 24.7 14.6 24.7 16.4C24.7 21.7 20.3 25.8 15 25.1C9.6 24.5 6.1 19.3 7.6 14.1C9.1 8.8 14.8 5.7 20.3 3.8Z M23.5 8.4a.85.85 0 1 0 1.7 0a.85.85 0 1 0-1.7 0Z"
      />
    </svg>
  );
}

function Arrow({ back = false }: { back?: boolean }) {
  return (
    <svg
      className={back ? 'arrow arrow-back' : 'arrow'}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function Pill({
  children,
  variant = 'light',
  href,
  onClick,
}: {
  children: ReactNode;
  variant?: 'light' | 'solid' | 'outline';
  href?: string;
  onClick?: () => void;
}) {
  const className = `pill pill-${variant}`;
  const inner = (
    <>
      {children}
      <Arrow />
    </>
  );
  return href ? (
    <a className={className} href={href}>
      {inner}
    </a>
  ) : (
    <button type="button" className={className} onClick={onClick}>
      {inner}
    </button>
  );
}

function Eyebrow({ children, light = false }: { children: ReactNode; light?: boolean }) {
  return <span className={`eyebrow ${light ? 'eyebrow-light' : ''}`}>{children}</span>;
}

function useReveal(scope: string) {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-in');
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.08 }
    );
    document
      .querySelectorAll(`${scope} :is(.reveal, .stack, .words)`)
      .forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [scope]);
}

function ContactModal() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState('');
  const [error, setError] = useState('');
  const [formKey, setFormKey] = useState(0);
  const name = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener(CONTACT_EVENT, show);
    return () => window.removeEventListener(CONTACT_EVENT, show);
  }, []);
  useEffect(() => {
    if (!open) return;
    lockScroll(true);
    const timer = window.setTimeout(() => name.current?.focus(), 120);
    const key = (event: KeyboardEvent) => event.key === 'Escape' && close();
    document.addEventListener('keydown', key);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('keydown', key);
      lockScroll(false);
    };
  }, [open]);
  function close() {
    setOpen(false);
    window.setTimeout(() => {
      setDone('');
      setError('');
      setFormKey((old) => old + 1);
    }, 350);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError('');
    try {
      await post('/commercial/requests', {
        kind: 'demo',
        name: data.get('name'),
        email: data.get('email'),
        company: data.get('company') || '',
        note: data.get('note') || '',
        consent: data.get('consent') === 'on',
      });
      setDone(String(data.get('name')).trim().split(' ')[0]);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (typeof document === 'undefined' || !open) return null;
  return createPortal(
    <div className="modal">
      <div className="modal-back" onClick={close} />
      <div className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="contact-title">
        <div className="modal-head">
          <div>
            <Eyebrow>{t('Демонстрация')}</Eyebrow>
            <h2 id="contact-title">{t('Покажем на вашем реестре')}</h2>
          </div>
          <button type="button" className="icon-close" aria-label={t('Закрыть')} onClick={close}>
            <X aria-hidden="true" />
          </button>
        </div>
        {done ? (
          <div className="modal-done">
            <span>
              <Check aria-hidden="true" />
            </span>
            <strong>{t('Заявка принята')}</strong>
            <p>{t('{0}, мы напишем вам в течение рабочего дня.', [done])}</p>
            <Pill variant="solid" onClick={close}>
              {t('Готово')}
            </Pill>
          </div>
        ) : (
          <form key={formKey} onSubmit={(event) => void submit(event)}>
            <label>
              {t('Имя')}
              <input ref={name} name="name" required maxLength={100} autoComplete="name" />
            </label>
            <label>
              {t('Рабочая почта')}
              <input name="email" type="email" required maxLength={254} autoComplete="email" />
            </label>
            <label>
              {t('Компания')}
              <input name="company" maxLength={200} autoComplete="organization" />
            </label>
            <label>
              {t('Что хотите обсудить')}
              <textarea name="note" rows={3} maxLength={2000} />
            </label>
            <label className="modal-consent">
              <input type="checkbox" name="consent" required />
              <span>
                {t('Даю')}{' '}
                <a href="/consent" target="_blank" rel="noreferrer">
                  {t('согласие на обработку персональных данных')}
                </a>
              </span>
            </label>
            {error && (
              <p className="modal-error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" className="pill pill-solid" disabled={busy}>
              {busy ? t('Отправляем…') : t('Отправить заявку')}
              <Arrow />
            </button>
          </form>
        )}
      </div>
    </div>,
    document.body
  );
}

function Menu({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    lockScroll(true);
    const key = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      lockScroll(false);
    };
  }, [onClose]);
  return createPortal(
    <div className="site-menu" role="dialog" aria-modal="true" aria-label={t('Меню')}>
      <div className="site-menu-top">
        <a className="site-brand" href="/">
          <Mark />
          <span>Mandato</span>
        </a>
        <button
          type="button"
          className="icon-close icon-close-light"
          aria-label={t('Закрыть')}
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </button>
      </div>
      <nav aria-label={t('Меню')}>
        {mainNav.map(([label, href], index) => (
          <a key={href} href={href} style={{ animationDelay: `${120 + index * 70}ms` }}>
            {label}
          </a>
        ))}
      </nav>
      <div className="site-menu-bottom">
        <Pill
          onClick={() => {
            onClose();
            openContact();
          }}
        >
          {t('Заказать демонстрацию')}
        </Pill>
        <a className="site-menu-login" href="/app?mode=login">
          {t('Войти')}
        </a>
        <LanguageSwitch />
      </div>
    </div>,
    document.body
  );
}

export function SiteHeader({ overlay = false }: { overlay?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <header className={`site-header ${overlay ? 'site-header-overlay' : ''}`}>
        <nav className="site-nav-left" aria-label={t('Основная навигация')}>
          {mainNav.map(([label, href]) => (
            <a
              key={href}
              href={href}
              aria-current={location.pathname === href ? 'page' : undefined}
            >
              {label}
            </a>
          ))}
        </nav>
        <a className="site-brand" href="/" aria-label={t('Mandato — на главную')}>
          <Mark />
          <span>Mandato</span>
        </a>
        <div className="site-actions">
          <a className="site-login" href="/app?mode=login">
            {t('Войти')}
          </a>
          <button type="button" className="site-demo" onClick={openContact}>
            {t('Заказать демонстрацию')}
          </button>
          <button
            type="button"
            className="site-burger"
            aria-label={t('Открыть меню')}
            aria-expanded={open}
            onClick={() => setOpen(true)}
          >
            <i />
            <i />
          </button>
        </div>
      </header>
      {open && <Menu onClose={() => setOpen(false)} />}
      <ContactModal />
    </>
  );
}

const footerColumns: [string, [string, string][]][] = [
  [
    t('Продукт'),
    [
      [t('Должники'), '/product#debtors'],
      [t('Досудебная работа'), '/product#pretrial'],
      [t('Суд'), '/product#court'],
      [t('Исполнение'), '/product#enforcement'],
    ],
  ],
  [
    t('Сервис'),
    [
      [t('Цены'), '/pricing'],
      [t('Для команд'), '/solutions'],
      [t('Подключения'), '/integrations'],
      [t('Безопасность'), '/security'],
    ],
  ],
  [
    t('Документы'),
    [
      [t('О компании'), '/company'],
      [t('Конфиденциальность'), '/privacy'],
      [t('Условия использования'), '/terms'],
      [t('Возврат средств'), '/refunds'],
      [t('Файлы cookie'), '/cookies'],
    ],
  ],
];

export function SiteFooter() {
  useReveal('.site-footer');
  return (
    <footer className="site-footer" id="contact">
      <div className="site-footer-cta">
        <div>
          <Eyebrow light>{t('Начать')}</Eyebrow>
          <Stack lines={[t('Готовы начать?')]} tag="p" />
        </div>
        <Reveal className="site-footer-actions" delay={150}>
          <Pill href="/start?plan=trial">{t('Попробовать бесплатно')}</Pill>
          <Pill variant="outline" onClick={openContact}>
            {t('Заказать демонстрацию')}
          </Pill>
        </Reveal>
      </div>
      <div className="site-footer-grid">
        <div>
          <a className="site-brand" href="/">
            <Mark />
            <span>Mandato</span>
          </a>
          <p>{t('Взыскание дебиторской задолженности от первого напоминания до приставов.')}</p>
          <address>
            <a href="mailto:info@mandato.ru">info@mandato.ru</a>
          </address>
        </div>
        {footerColumns.map(([title, links]) => (
          <nav key={title} aria-label={title}>
            <h3>{title}</h3>
            <ul>
              {links.map(([label, href]) => (
                <li key={href}>
                  <a href={href}>{label}</a>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="site-footer-bottom">
        <small>
          © {new Date().getFullYear()} Mandato · {legalEntityLine}
        </small>
        <LanguageSwitch />
      </div>
    </footer>
  );
}

function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <div className={`reveal ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

function SectionHead({
  eyebrow,
  title,
  lead,
  id,
  light = false,
}: {
  eyebrow: string;
  title: string;
  lead: string;
  id: string;
  light?: boolean;
}) {
  return (
    <div className="section-head">
      <div>
        <Eyebrow light={light}>{eyebrow}</Eyebrow>
        <h2 className="stack" id={id}>
          <span className="clip clip-line">
            <span>{title}</span>
          </span>
        </h2>
      </div>
      <Reveal className="section-lead" delay={120}>
        <p>{lead}</p>
      </Reveal>
    </div>
  );
}

function Stack({
  lines,
  tag: Tag = 'h2',
  id,
  stagger = 120,
}: {
  lines: string[];
  tag?: 'h2' | 'p';
  id?: string;
  stagger?: number;
}) {
  return (
    <Tag className="stack" id={id}>
      {lines.map((line, index) => (
        <span className="clip clip-line" key={line}>
          <span style={{ animationDelay: `${index * stagger}ms` }}>{line}</span>
        </span>
      ))}
    </Tag>
  );
}

const stageCards = [
  {
    icon: MailCheck,
    title: t('Досудебная работа'),
    text: t('Письма, обещания, претензии'),
    href: '/product#pretrial',
  },
  { icon: Gavel, title: t('Суд'), text: t('Пошлина, приказ или иск'), href: '/product#court' },
  {
    icon: Landmark,
    title: t('Исполнение'),
    text: t('Банк, приставы, ФНС'),
    href: '/product#enforcement',
  },
];

function Dots({
  count,
  index,
  labels,
  onPick,
  light = false,
}: {
  count: number;
  index: number;
  labels: string[];
  onPick: (position: number) => void;
  light?: boolean;
}) {
  return (
    <div className={`dots ${light ? 'dots-light' : ''}`}>
      {Array.from({ length: count }, (_, position) => (
        <button
          key={labels[position]}
          type="button"
          aria-label={labels[position]}
          aria-current={position === index ? 'true' : undefined}
          onClick={() => onPick(position)}
        >
          <i />
        </button>
      ))}
    </div>
  );
}

function StageSlider() {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const timer = window.setInterval(() => setIndex((old) => (old + 1) % stageCards.length), 3800);
    return () => window.clearInterval(timer);
  }, []);
  const card = stageCards[index];
  const Icon = card.icon;
  return (
    <div className="hero-slider">
      <a className="glass hero-stage" href={card.href} key={card.title}>
        <span className="hero-stage-icon">
          <Icon aria-hidden="true" />
        </span>
        <span>
          <strong>{card.title}</strong>
          <small>{card.text}</small>
        </span>
      </a>
      <Dots
        count={stageCards.length}
        index={index}
        labels={stageCards.map((item) => item.title)}
        onPick={setIndex}
        light
      />
    </div>
  );
}

const slides = [
  {
    words: [t('Претензии'), t('без'), t('ручной'), t('рутины')],
    name: t('Досудебная работа'),
    role: t('Напоминания, обещания, претензии по вашим правилам'),
    rows: [
      [t('Напоминание'), t('отправлено')],
      [t('Обещание'), t('до 14 ноября')],
      [t('Претензия'), t('готова')],
    ],
  },
  {
    words: [t('Суд'), t('без'), t('лишних'), t('бумаг')],
    name: t('Суд'),
    role: t('Маршрут, пошлина и пакет документов для арбитража'),
    rows: [
      [t('Маршрут'), t('приказ')],
      [t('Пошлина'), t('рассчитана')],
      [t('Пакет'), t('у юриста')],
    ],
  },
  {
    words: [t('Взыскание'), t('без'), t('лишних'), t('потерь')],
    name: t('Исполнение'),
    role: t('Банк, приставы и контроль поступлений'),
    rows: [
      [t('Лист'), t('получен')],
      [t('Банк'), t('предъявлен')],
      [t('Остаток'), t('по выписке')],
    ],
  },
];
const ghostDrift = [
  [-3, 3],
  [3, -3],
  [-2, 4],
  [4, -3],
];

function Trust() {
  const [index, setIndex] = useState(0);
  const slide = slides[index];
  const go = (step: number) => setIndex((old) => (old + step + slides.length) % slides.length);
  return (
    <section className="trust" aria-labelledby="trust-title">
      <div className="trust-grid">
        <div className="trust-copy">
          <Eyebrow>{t('Один долг — одна карточка')}</Eyebrow>
          <h2 id="trust-title" className="ghost" key={index}>
            {[0, 2].map((start) => (
              <span className="ghost-row" key={start}>
                {slide.words.slice(start, start + 2).map((word, position) => (
                  <span
                    className={`clip ghost-word ${start === 2 && position === 0 ? 'ghost-ink' : ''}`}
                    key={word}
                    data-from={ghostDrift[start + position][0]}
                    data-to={ghostDrift[start + position][1]}
                  >
                    <span>{word}</span>
                  </span>
                ))}
              </span>
            ))}
          </h2>
          <p className="trust-lead">
            {t(
              'Договор, письма, оплаты и документы суда лежат в одной карточке и переходят с этапа на этап вместе с долгом.'
            )}
          </p>
          <div className="trust-controls">
            <button
              type="button"
              className="round round-outline"
              aria-label={t('Назад')}
              onClick={() => go(-1)}
            >
              <Arrow back />
            </button>
            <Dots
              count={slides.length}
              index={index}
              labels={slides.map((item) => item.name)}
              onPick={setIndex}
            />
            <button
              type="button"
              className="round round-solid"
              aria-label={t('Вперёд')}
              onClick={() => go(1)}
            >
              <Arrow />
            </button>
          </div>
        </div>
        <figure className="trust-card" key={index}>
          <figcaption>
            <small>{t('Этап')}</small>
            <strong>{slide.name}</strong>
          </figcaption>
          <div className="trust-card-rows">
            {slide.rows.map(([label, value]) => (
              <p key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </p>
            ))}
          </div>
          <p className="trust-card-note">{slide.role}</p>
        </figure>
      </div>
    </section>
  );
}

const rows = [
  [
    '01',
    t('Реестр должников'),
    t('Excel или 1С, этапы, статусы, фильтры и действия сразу по списку.'),
    '/product#debtors',
  ],
  [
    '02',
    t('Напоминания и претензии'),
    t(
      'Письма уходят с вашей почты от имени вашей компании: по расписанию, с разным текстом для разных сумм.'
    ),
    '/product#pretrial',
  ],
  [
    '03',
    t('Суд и исполнение'),
    t('Расчёт процентов и пошлины, заявления, ходатайства, запросы приставам и в банки.'),
    '/product#court',
  ],
  [
    '04',
    t('Аналитика и отчёты'),
    t('Сколько должны, сколько вернулось, что мешает. Отчёт в пару кликов.'),
    '/product#analytics',
  ],
];
const views = {
  summary: [
    [t('В работе'), '8,4 млн ₽', t('25 должников')],
    [t('Просрочено'), '6,1 млн ₽', t('в среднем 47 дней')],
    [t('Обещали оплатить'), '1,2 млн ₽', t('в ближайшие 30 дней')],
    [t('Получено'), '2,3 млн ₽', t('+18% к прошлому месяцу')],
  ],
  today: [
    ['4', t('должника нарушили обещание оплатить')],
    ['3', t('можно передавать в суд: срок ответа на претензию истёк')],
    ['2', t('у должников срок давности истекает в ближайшие 40 дней')],
    ['1', t('новый ответ должника ждёт вашей проверки')],
  ],
};

const facts = [
  ['30', t('дней'), t('на ответ по претензии, прежде чем идти в суд')],
  ['750', t('тыс. ₽'), t('предел для судебного приказа')],
  ['3', t('года'), t('срок давности: система предупредит заранее')],
  ['10', t('дней'), t('на возражения по судебному приказу: потом можно взыскивать')],
];
const start = [
  [t('Загрузите реестр'), t('Excel или выгрузка из 1С. Должники сами разойдутся по этапам.')],
  [t('Утвердите правила'), t('С какой суммы, как часто и каким каналом писать.')],
  [t('Следите за оплатами'), t('Видно, кто заплатил после письма, а кому пора претензия.')],
];

export function Landing() {
  const plate = useRef<HTMLDivElement>(null);
  useReveal('.landing');
  useEffect(() => {
    const root = document.documentElement;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const hero = plate.current?.parentElement;
    const trust = document.querySelector<HTMLElement>('.trust');
    let frame = 0;
    let current = 0;
    const words = () => [...document.querySelectorAll<HTMLElement>('.ghost-word')];
    const loop = (time: number) => {
      smooth?.raf(time);
      if (hero && plate.current) {
        const target = Math.min(1, Math.max(0, window.scrollY / hero.offsetHeight)) * 12;
        current += (target - current) * 0.12;
        plate.current.style.transform = `translate3d(0, ${current.toFixed(2)}%, 0)`;
      }
      if (trust) {
        const box = trust.getBoundingClientRect();
        const progress = Math.min(
          1,
          Math.max(0, (innerHeight - box.top) / (innerHeight + box.height))
        );
        words().forEach((word) => {
          const from = Number(word.dataset.from);
          const to = Number(word.dataset.to);
          word.style.transform = `translate3d(${(from + (to - from) * progress).toFixed(2)}%, 0, 0)`;
        });
      }
      frame = requestAnimationFrame(loop);
    };
    let cancelled = false;
    if (!reduced) {
      frame = requestAnimationFrame(loop);
      if (window.innerWidth > 768) {
        void import('lenis').then(({ default: Lenis }) => {
          if (!cancelled) smooth = new Lenis({ smoothWheel: true }) as unknown as Smooth;
        });
      }
    }
    let intro = 0;
    if (!reduced && !root.classList.contains('no-intro')) {
      window.scrollTo(0, 0);
      lockScroll(true);
      intro = window.setTimeout(() => lockScroll(false), 900);
    }
    try {
      sessionStorage.setItem('mandato-intro', '1');
    } catch {
      /* the intro simply plays again */
    }
    return () => {
      cancelled = true;
      window.clearTimeout(intro);
      cancelAnimationFrame(frame);
      smooth?.destroy();
      smooth = null;
    };
  }, []);
  return (
    <div className="landing">
      <div className="intro" aria-hidden="true">
        <p>
          <Mark />
          Mandato
        </p>
        <span className="intro-track">
          <i />
        </span>
      </div>
      <section className="hero">
        <div className="hero-plate" ref={plate}>
          <img
            src="/hero.webp"
            alt=""
            width={1672}
            height={941}
            fetchPriority="high"
            decoding="async"
          />
        </div>
        <SiteHeader overlay />
        <h1 id="hero-title">
          {[t('Долги'), t('в деньги')].map((word, index) => (
            <span className="clip" key={word}>
              <span style={{ animationDelay: `calc(var(--intro) + ${index * 140}ms)` }}>
                {word}
              </span>
            </span>
          ))}
        </h1>
        <div className="hero-bottom">
          <div className="hero-copy">
            <p className="hero-tagline">
              {[t('Взыскание'), t('дебиторки')].map((line, index) => (
                <span className="clip clip-line" key={line}>
                  <span
                    style={{
                      animationDelay: `calc(var(--intro) + ${350 + index * 110}ms)`,
                      animationDuration: '900ms',
                    }}
                  >
                    {line}
                  </span>
                </span>
              ))}
            </p>
            <p className="hero-lead">
              {t(
                'От первого напоминания до приставов. Рутину ведёт система, решения остаются за вами.'
              )}
            </p>
            <Pill href="/start?plan=trial">{t('Попробовать бесплатно')}</Pill>
          </div>
          <div className="hero-cluster">
            <a className="glass hero-trial" href="/pricing">
              <strong>14</strong>
              <small>{t('дней бесплатно, без карты')}</small>
            </a>
            <StageSlider />
          </div>
        </div>
      </section>

      <Trust />

      <section className="programs" id="programs" aria-labelledby="programs-title">
        <SectionHead
          eyebrow={t('Что внутри')}
          title={t('Весь путь долга в одной системе')}
          lead={t(
            'Загрузите реестр, и Mandato поведёт каждого должника от первого письма до приставов.'
          )}
          id="programs-title"
        />
        <ul>
          {rows.map(([index, name, text, href], position) => (
            <li key={index}>
              <a href={href}>
                <Reveal className="program-row" delay={position * 90}>
                  <span className="program-index">{index}</span>
                  <span className="program-text">
                    <strong>{name}</strong>
                    <small>{text}</small>
                  </span>
                  <span className="program-arrow">
                    <Arrow />
                  </span>
                </Reveal>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section className="views" id="facilities" aria-labelledby="views-title">
        <SectionHead
          eyebrow={t('Кабинет')}
          title={t('Ситуация понятна с первого экрана')}
          lead={t(
            'Главная страница отвечает на три вопроса: сколько вам должны, сколько уже вернулось и что сделать сегодня.'
          )}
          id="views-title"
        />
        <div className="views-cards">
          <Reveal className="view-tile view-tile-deep">
            <p className="view-tile-label">{t('Сводка за месяц')}</p>
            <dl>
              {views.summary.map(([label, value, note]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>
                    {value}
                    {note && <small>{note}</small>}
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>
          <Reveal className="view-tile view-tile-brand" delay={140}>
            <p className="view-tile-label">{t('Что сделать сегодня')}</p>
            <ul>
              {views.today.map(([count, text]) => (
                <li key={text}>
                  <strong>{count}</strong>
                  <span>{text}</span>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
        <p className="views-note">{t('Пример экрана. Цифры показаны для наглядности.')}</p>
      </section>

      <section className="stats" aria-labelledby="stats-title">
        <SectionHead
          light
          eyebrow={t('Сроки и суммы')}
          title={t('Система считает сама')}
          lead={t(
            'Сроки по закону, проценты по ставкам ЦБ, госпошлина по Налоговому кодексу. Без таблиц и ручных расчётов.'
          )}
          id="stats-title"
        />
        <dl className="stats-grid">
          {facts.map(([value, unit, text], index) => (
            <Reveal key={text} className="stat-cell" delay={index * 110}>
              <dt className="sr-only">{text}</dt>
              <dd>
                <span className="stat-value">
                  {value} <small>{unit}</small>
                </span>
                <span className="stat-text">{text}</span>
              </dd>
            </Reveal>
          ))}
        </dl>
      </section>

      <section className="start" aria-labelledby="start-title">
        <SectionHead
          eyebrow={t('Как начать')}
          title={t('Запуск за один день')}
          lead={t('Не нужны внедрение и программист: достаточно списка должников в Excel.')}
          id="start-title"
        />
        <ol>
          {start.map(([title, text], index) => (
            <li key={title}>
              <Reveal delay={index * 120} className="start-card">
                <span className="start-number">0{index + 1}</span>
                <h3>{title}</h3>
                <p>{text}</p>
              </Reveal>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
