import { useEffect, useRef, useState } from 'react';
import {
  ArrowUpRight,
  ArrowRight,
  Check,
  Play,
  Pause,
  FileText,
  Settings2,
  Landmark,
  Layers3,
  Clock3,
  Mail,
  CheckCheck,
  ShieldCheck,
  Plus,
  Menu,
  X,
  MoveUpRight,
} from 'lucide-react';
import { Brand } from './Brand';
import { Dialog } from './Dialog';
import { money } from '../api';
import './landing.css';
const steps = [
  {
    label: 'Собираем дело целиком',
    caption:
      'Счета одного покупателя по одному договору — вместе. Суммы, документы и контакты проходят проверку.',
  },
  {
    label: 'Напоминаем по вашим правилам',
    caption:
      'Руководитель задаёт тон, расписание и границы. Mandato ведёт обычные напоминания автоматически.',
  },
  {
    label: 'Следим за договорённостью',
    caption:
      'Ответ покупателя остаётся в деле. Обещание оплаты становится следующим шагом, но не меняет остаток долга.',
  },
  {
    label: 'Учитываем реальные поступления',
    caption:
      'Частичная оплата уменьшает остаток. По погашенным счетам контакт прекращается, по остальным работа продолжается.',
  },
];
const faqs = [
  [
    'Кому подходит Mandato?',
    'Бухгалтерам и финансовым руководителям компаний, которые продают юридическим лицам с отсрочкой платежа. Mandato помогает видеть задолженность по контрагенту и договору, вести напоминания и разбирать исключения в одном рабочем пространстве.',
  ],
  [
    'Как загрузить данные из 1С?',
    'Начните с выгрузки CSV или XLSX: выберите лист, сопоставьте колонки и проверьте суммы, даты и повторы перед сохранением. Для регулярного обмена настройте подключение 1С и проверьте доступ. ОСВ используется для сверки: общий остаток сам по себе не создаёт счета.',
  ],
  [
    'Нужно согласовывать каждое письмо?',
    'Нет. Руководитель утверждает правила и включает автоматическую работу после настройки почты и расписания. Обычные напоминания идут в этих границах. Споры, неоднозначные ответы и оплаты попадают на проверку бухгалтеру; скидка, рассрочка и юридическая эскалация требуют решения руководителя.',
  ],
  [
    'Что делать, если покупатель оспаривает долг?',
    'Поставьте дело на паузу и разберите расхождения. Автоматические напоминания приостанавливаются, документы и история переписки остаются в карточке. Решение о дальнейшем действии принимает ваша команда.',
  ],
  [
    'Mandato принимает деньги покупателей?',
    'Нет. Покупатели платят напрямую вашей компании по вашим реквизитам. Подтверждённое поступление учитывается по конкретным счетам. Частичная оплата уменьшает остаток, а обещание заплатить не считается деньгами.',
  ],
  [
    'Можно начать с небольшой части реестра?',
    'Да. Загрузите несколько счетов, проверьте дела и документы, настройте правила с руководителем. Подключения можно добавлять по мере готовности: для каждого нужны доступ и проверка обмена.',
  ],
];
export function Landing() {
  const [step, setStep] = useState(0),
    [playing, setPlaying] = useState(() => !matchMedia('(prefers-reduced-motion: reduce)').matches),
    [menu, setMenu] = useState(false),
    [openFaq, setOpenFaq] = useState<number | null>(0),
    [amount, setAmount] = useState(3000000),
    [days, setDays] = useState(30),
    [rate, setRate] = useState(20),
    [legal, setLegal] = useState<'privacy' | 'terms' | null>(null);
  const workflow = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!playing || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const timer = setInterval(() => setStep((s) => (s + 1) % 4), 5000);
    return () => clearInterval(timer);
  }, [playing]);
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) e.target.classList.add('visible');
        }),
      { threshold: 0.12 }
    );
    document.querySelectorAll('.reveal').forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  const scrollWorkflow = () =>
    workflow.current?.scrollIntoView({
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    });
  return (
    <div className="landing">
      <a href="#main" className="skip-link">
        К содержимому
      </a>
      <header className="site-header">
        <Brand />
        <nav aria-label="Основная навигация" className={menu ? 'nav-open' : ''}>
          <a href="#how" onClick={() => setMenu(false)}>
            Как это работает
          </a>
          <a href="#value" onClick={() => setMenu(false)}>
            Для вашего бизнеса
          </a>
          <a href="#pricing" onClick={() => setMenu(false)}>
            Стоимость
          </a>
        </nav>
        <div className="header-actions">
          <a href="/app?mode=login" className="login-link">
            Войти <ArrowUpRight size={15} />
          </a>
          <a href="/app" className="button button-dark small">
            Начать работу <ArrowUpRight size={16} />
          </a>
          <button
            className="menu-toggle icon-button"
            aria-label={menu ? 'Закрыть меню' : 'Открыть меню'}
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            {menu ? <X /> : <Menu />}
          </button>
        </div>
      </header>
      <main id="main">
        <section className="hero">
          <div className="hero-shade" />
          <div className="hero-content">
            <h1>
              Просроченные счета.<span>Понятный план возврата.</span>
            </h1>
            <div className="hero-bottom">
              <div>
                <p>
                  Mandato собирает долги по контрагентам и договорам, напоминает по вашим правилам и
                  выводит на вас только то, что требует решения.
                </p>
                <a href="/app" className="button button-lime">
                  Разобрать свой реестр <ArrowUpRight size={20} />
                </a>
                <button className="hero-watch" onClick={scrollWorkflow}>
                  <span>
                    <Play size={12} fill="currentColor" />
                  </span>
                  Посмотреть, как это работает
                </button>
              </div>
            </div>
          </div>
          <aside className="hero-workspace" aria-label="Как устроен рабочий день в Mandato">
            <div className="hero-workspace-title">
              Вы решаете исключения.
              <br />
              <span>Mandato ведёт напоминания.</span>
            </div>
            <div className="hero-workspace-item">
              <span className="hero-workspace-icon">
                <Settings2 size={17} />
              </span>
              <div>
                <strong>В работе у Mandato</strong>
                <p>Напоминания, сроки, ожидание ответа</p>
              </div>
              <span className="hero-workspace-badge">По правилам</span>
            </div>
            <div className="hero-workspace-item">
              <span className="hero-workspace-icon">
                <FileText size={17} />
              </span>
              <div>
                <strong>На проверке у бухгалтера</strong>
                <p>Документы и неоднозначные поступления</p>
              </div>
              <ArrowUpRight size={16} />
            </div>
            <div className="hero-workspace-item">
              <span className="hero-workspace-icon">
                <ShieldCheck size={17} />
              </span>
              <div>
                <strong>На решении у руководителя</strong>
                <p>Скидка, рассрочка, юридический шаг</p>
              </div>
              <ArrowUpRight size={16} />
            </div>
            <div className="hero-workspace-footer">
              <Check size={16} />
              <span>Правила утверждаете вы. История сохраняется.</span>
            </div>
          </aside>
        </section>
        <div className="trust-line">
          <span>Для бухгалтерии и финансового руководителя</span>
          <div>
            <span>ОПТОВАЯ ТОРГОВЛЯ</span>
            <i />
            <span>ПРОИЗВОДСТВО</span>
            <i />
            <span>B2B-УСЛУГИ</span>
          </div>
        </div>
        <section className="intro section-pad reveal" id="value">
          <div className="intro-grid">
            <h2>Счета, документы и переписка — в одном деле.</h2>
            <div className="intro-copy">
              <p className="large-copy">
                Чтобы получить оплату, мало знать сумму. Нужно видеть договор, документы, переписку
                и последнее обещание покупателя.
              </p>
              <p>
                Mandato объединяет это в дело по контрагенту и договору. Бухгалтер проверяет
                исключения, руководитель принимает существенные решения, агент ведёт ежедневную
                работу.
              </p>
              <a href="/app" className="text-link">
                Начать с импорта <ArrowUpRight size={18} />
              </a>
            </div>
          </div>
          <div className="benefit-row">
            <div>
              <h3>История по договору</h3>
              <p>
                Несколько счетов, частичные оплаты,
                <br />
                документы и контакты — в одном деле.
              </p>
            </div>
            <div>
              <h3>Напоминания автоматически</h3>
              <p>
                Тон, расписание и интервалы контакта
                <br />
                определяет ваша компания.
              </p>
            </div>
            <div>
              <h3>Спорные вопросы — вам</h3>
              <p>
                Спор, расхождение или новые условия
                <br />
                не теряются в потоке напоминаний.
              </p>
            </div>
          </div>
        </section>
        <section className="workflow section-pad" id="how" ref={workflow}>
          <div className="workflow-heading">
            <h2>
              От реестра
              <br />
              до поступления.
            </h2>
            <p>
              Проследите работу по одному договору.
              <br />
              Несколько счетов. Один понятный следующий шаг.
            </p>
          </div>
          <div className="workflow-grid">
            <div className="step-list" role="tablist" aria-label="Этапы работы">
              {steps.map((s, i) => (
                <button
                  key={s.label}
                  className={`step ${i === step ? 'active' : ''}`}
                  role="tab"
                  aria-selected={step === i}
                  aria-controls="workflow-panel"
                  id={`step-${i}`}
                  onKeyDown={(event) => {
                    if (
                      !['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(
                        event.key
                      )
                    )
                      return;
                    event.preventDefault();
                    const next =
                      event.key === 'Home'
                        ? 0
                        : event.key === 'End'
                          ? steps.length - 1
                          : (i +
                              (event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : -1) +
                              steps.length) %
                            steps.length;
                    setStep(next);
                    setPlaying(false);
                    document.getElementById(`step-${next}`)?.focus();
                  }}
                  onClick={() => {
                    setStep(i);
                    setPlaying(false);
                  }}
                >
                  <span className="step-number">0{i + 1}</span>
                  <span>
                    <strong>{s.label}</strong>
                    <span className="step-caption">{s.caption}</span>
                  </span>
                  <ArrowUpRight size={19} />
                </button>
              ))}
              <button
                className="playback"
                onClick={() => setPlaying(!playing)}
                aria-label={playing ? 'Приостановить смену этапов' : 'Продолжить смену этапов'}
              >
                {playing ? <Pause size={13} /> : <Play size={13} />}{' '}
                {playing ? 'Остановить' : 'Продолжить'} просмотр
              </button>
            </div>
            <div
              className="scenario"
              role="tabpanel"
              id="workflow-panel"
              aria-labelledby={`step-${step}`}
            >
              <div className="scenario-top">
                <Brand />
                <span>
                  <i className="status-dot" /> КАК ПРОХОДИТ РАБОТА
                </span>
              </div>
              <div className="scenario-body" key={step}>
                <div className="scenario-doc">
                  <div className="doc-label">
                    <span>
                      <Layers3 size={15} /> ДЕЛО ПО ДОГОВОРУ
                    </span>
                    <span className={`pill ${step === 3 ? 'green' : 'orange'}`}>
                      {['Проверено', 'В работе', 'Ожидаем оплату', 'Частично оплачено'][step]}
                    </span>
                  </div>
                  <h3>ООО «Северстрой»</h3>
                  <span className="scenario-sub">Договор поставки № 12 · 3 счёта</span>
                  <div className="case-balance-label">
                    {step === 3 ? 'ОСТАТОК К ПОЛУЧЕНИЮ' : 'К ПОЛУЧЕНИЮ ПО ДОГОВОРУ'}
                  </div>
                  <div className="scenario-amount">
                    {step === 3 ? '300 000' : '480 000'} <span>₽</span>
                  </div>
                  <div className="case-invoices" aria-label="Счета по договору">
                    <div>
                      <span>№ 417 · 12 октября</span>
                      <strong>
                        {step === 3 ? (
                          <>
                            <Check size={12} /> Оплачен
                          </>
                        ) : (
                          '180 000 ₽'
                        )}
                      </strong>
                    </div>
                    <div>
                      <span>№ 428 · 15 октября</span>
                      <strong>160 000 ₽</strong>
                    </div>
                    <div>
                      <span>№ 436 · 19 октября</span>
                      <strong>140 000 ₽</strong>
                    </div>
                  </div>
                  <div className="scenario-state">
                    {step === 0 ? (
                      <div className="case-action">
                        <span className="case-action-label">
                          <FileText size={14} /> ПРОВЕРКА ЗАВЕРШЕНА
                        </span>
                        <strong>Документы и контакт на месте</strong>
                        <p>
                          Счета объединены по договору. Следующее действие — напоминание по
                          утверждённым правилам.
                        </p>
                      </div>
                    ) : step === 1 ? (
                      <div className="message-preview">
                        <span>
                          <Mail size={14} /> ОТПРАВЛЕНО ПО ПРАВИЛАМ КОМПАНИИ
                        </span>
                        <p>
                          Анна, добрый день! По договору № 12 ожидаем 480 000 ₽ по трём счетам.
                          Подскажите, когда сможете провести оплату?
                        </p>
                        <div>
                          <ShieldCheck size={14} /> Деловой тон · в рабочее время
                        </div>
                      </div>
                    ) : step === 2 ? (
                      <div className="promise-preview">
                        <span>
                          <Clock3 size={14} /> ОТВЕТ ПОКУПАТЕЛЯ
                        </span>
                        <strong>28 октября</strong>
                        <p>«Перечислим 180 000 ₽ по счёту № 417»</p>
                        <div>
                          <CheckCheck size={15} /> Обещание записано. Остаток не изменён.
                        </div>
                      </div>
                    ) : (
                      <div className="case-action case-receipt">
                        <span className="case-action-label">
                          <Landmark size={14} /> ПОСТУПЛЕНИЕ ПОДТВЕРЖДЕНО
                        </span>
                        <strong>+180 000 ₽ по счёту № 417</strong>
                        <p>
                          Счёт погашен, напоминания по нему остановлены. По двум оставшимся —
                          следующий контакт по расписанию.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div className="scenario-footer">
                <span>Проверка</span>
                <i className={step >= 1 ? 'done' : ''} />
                <span>Контакт</span>
                <i className={step >= 2 ? 'done' : ''} />
                <span>Ожидание</span>
                <i className={step >= 3 ? 'done' : ''} />
                <span>Поступление</span>
              </div>
            </div>
          </div>
        </section>
        <section className="connections section-pad reveal">
          <div>
            <h2>
              Начните с выгрузки.
              <br />
              <span className="muted">Подключите источники.</span>
            </h2>
            <p>
              Импортируйте CSV или XLSX, проверьте реестр и настройте регулярный обмен с доступными
              вашей компании сервисами.
            </p>
          </div>
          <div className="connection-list">
            <div>
              <span>01</span>
              <strong>1С</strong>
              <p>Счета и сверка задолженности</p>
            </div>
            <div>
              <span>02</span>
              <strong>Диадок</strong>
              <p>Документы по договору</p>
            </div>
            <div>
              <span>03</span>
              <strong>Банк</strong>
              <p>Подтверждение поступлений</p>
            </div>
            <p className="connection-note">
              <ShieldCheck size={15} /> Для обмена нужны ваш доступ и проверка подключения.
            </p>
          </div>
        </section>
        <section className="calculator section-pad reveal">
          <div className="calc-copy">
            <h2>
              Пока деньги ждут,
              <br />
              вы платите.
            </h2>
            <p>
              Посчитайте, сколько стоит финансирование просрочки. Это деньги, которые могли бы
              оставаться в вашем бизнесе.
            </p>
            <div className="calc-formula">Сумма × ставка × дни / 365</div>
          </div>
          <div className="calc-card">
            <div className="calc-input-label">
              <label htmlFor="amount">Сумма просроченных счетов</label>
              <span>{money(amount * 100)}</span>
            </div>
            <input
              id="amount"
              type="range"
              min="100000"
              max="15000000"
              step="100000"
              value={amount}
              onChange={(e) => setAmount(+e.target.value)}
            />
            <div className="calc-fields">
              <label>
                Дней ожидания
                <div>
                  <input
                    type="number"
                    min="1"
                    max="365"
                    value={days}
                    onChange={(e) => setDays(Math.max(1, Math.min(365, +e.target.value)))}
                  />
                  <span>дней</span>
                </div>
              </label>
              <label>
                Стоимость денег в год
                <div>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    value={rate}
                    onChange={(e) => setRate(Math.max(1, Math.min(60, +e.target.value)))}
                  />
                  <span>%</span>
                </div>
              </label>
            </div>
            <div className="calc-result">
              <span>Стоимость ожидания</span>
              <strong>{money(Math.round((amount * rate * days) / 365))}</strong>
              <span>при ваших условиях финансирования</span>
            </div>
          </div>
        </section>
        <section className="control section-pad reveal">
          <h2>Задайте правила работы с клиентами</h2>
          <div className="control-bottom">
            <p>
              Руководитель утверждает политику и включает автоматизацию. Перед контактом Mandato
              проверяет остаток, паузы и полномочия. Спор или расхождение возвращает дело человеку.
            </p>
            <div className="policy-points">
              <span>
                <Check size={16} /> Расписание и частота контактов
              </span>
              <span>
                <Check size={16} /> Пауза при споре
              </span>
              <span>
                <Check size={16} /> Скидка и рассрочка — через руководителя
              </span>
            </div>
          </div>
        </section>
        <section className="pricing section-pad reveal" id="pricing">
          <div className="pricing-head">
            <h2>Стоимость Mandato</h2>
            <p>
              Выберите формат, который подходит
              <br />
              вашей команде.
            </p>
          </div>
          <div className="pricing-grid">
            <article className="price-card">
              <div className="price-label">
                КОНТРОЛЬ <span>ДЛЯ ВАШЕЙ КОМАНДЫ</span>
              </div>
              <h3>
                14 900 ₽ <span>/ месяц</span>
              </h3>
              <p>
                Рабочий кабинет для регулярной
                <br />
                работы с дебиторкой.
              </p>
              <ul>
                {[
                  'Дела по контрагентам и договорам',
                  'Напоминания по утверждённой политике',
                  'Обещания, оплаты и очередь исключений',
                  'Импорт, экспорт и история действий',
                ].map((t) => (
                  <li key={t}>
                    <Check size={17} />
                    {t}
                  </li>
                ))}
              </ul>
              <a href="/app" className="button button-dark">
                Начать работу <ArrowUpRight size={19} />
              </a>
            </article>
            <article className="price-card price-service">
              <div className="price-label">
                СОПРОВОЖДЕНИЕ <span>С ВАШИМИ ПРАВИЛАМИ</span>
              </div>
              <h3>Вместе с вами</h3>
              <p>
                Для компаний, которым нужна помощь
                <br />с организацией процесса.
              </p>
              <ul>
                {[
                  'Разбор структуры задолженности',
                  'Настройка очереди и правил работы',
                  'Подготовка реестра для команды',
                  'Условия по объёму и задачам',
                ].map((t) => (
                  <li key={t}>
                    <Check size={17} />
                    {t}
                  </li>
                ))}
              </ul>
              <a href="/app?intent=service" className="button button-outline">
                Обсудить задачу <ArrowUpRight size={19} />
              </a>
            </article>
          </div>
          <p className="pricing-note">
            Начните с кабинета. Условия подключения и сопровождения согласуем до оплаты.
          </p>
        </section>
        <section className="faq section-pad reveal">
          <div>
            <h2>Вопросы и ответы</h2>
          </div>
          <div className="faq-list">
            {faqs.map(([q, a], i) => (
              <div className="faq-item" key={q}>
                <button
                  aria-expanded={openFaq === i}
                  aria-controls={`faq-${i}`}
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                >
                  {q}
                  <Plus size={20} className={openFaq === i ? 'rotated' : ''} />
                </button>
                {openFaq === i && <p id={`faq-${i}`}>{a}</p>}
              </div>
            ))}
          </div>
        </section>
        <section className="final-cta">
          <h2>Начните со своего реестра</h2>
          <a href="/app" className="button button-lime">
            Разобрать свой реестр <MoveUpRight size={20} />
          </a>
          <div className="cta-decoration" aria-hidden="true">
            ↗
          </div>
        </section>
      </main>
      <footer className="site-footer">
        <div>
          <Brand />
          <p>Деньги возвращаются в дело.</p>
        </div>
        <div className="footer-nav">
          <a href="#how">
            Как это работает <ArrowRight size={14} />
          </a>
          <a href="#pricing">
            Стоимость <ArrowRight size={14} />
          </a>
          <a href="/app?mode=login">
            Личный кабинет <ArrowUpRight size={14} />
          </a>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} Mandato</span>
          <button onClick={() => setLegal('privacy')}>Конфиденциальность</button>
          <button onClick={() => setLegal('terms')}>Условия использования</button>
          <span>Для бизнеса. По-человечески.</span>
        </div>
      </footer>
      {legal && (
        <Dialog
          title={legal === 'privacy' ? 'Конфиденциальность' : 'Условия использования'}
          onClose={() => setLegal(null)}
        >
          <div className="legal-modal">
            {legal === 'privacy' ? (
              <>
                <p>
                  Для работы кабинета сохраняются данные аккаунта, компании, загруженных счетов,
                  переписки и поступлений. Они используются для управления вашей дебиторской
                  задолженностью.
                </p>
                <p>
                  Данные кабинета доступны после входа. Вы можете выгрузить реестр. Пароль хранится
                  в защищённом виде. Отправка писем и передача текста внешней модели возможны только
                  при подключённых сервисах.
                </p>
                <p>
                  Загружайте только сведения, которые ваша компания вправе обрабатывать. Доступ к
                  рабочему пространству предназначен для уполномоченных сотрудников вашей компании.
                </p>
              </>
            ) : (
              <>
                <p>
                  Mandato помогает вести реестр задолженности, готовить письма и учитывать оплаты.
                  Доступ к кабинету не создаёт договор на юридическое представительство или
                  взыскание.
                </p>
                <p>
                  Перед включением автоматизации проверьте реквизиты, контакты и правила работы.
                  Существенные изменения условий требуют решения руководителя. Поступления
                  учитываются на основании платёжных документов.
                </p>
                <p>
                  Стоимость и условия обслуживания согласуются отдельно до оплаты. Доступ к аккаунту
                  предназначен для уполномоченного сотрудника вашей компании.
                </p>
              </>
            )}
            <button className="button button-dark" onClick={() => setLegal(null)}>
              Понятно <Check size={16} />
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
