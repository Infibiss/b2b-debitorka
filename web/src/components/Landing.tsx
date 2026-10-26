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
    label: 'Проверяем задолженность',
    caption:
      'Счета по одному договору собраны вместе. Видны остаток долга, расхождения и недостающие документы.',
  },
  {
    label: 'Напоминаем по вашим правилам',
    caption:
      'Задайте расписание и подключите почту. Mandato отправит обычные напоминания без ручной подготовки каждого письма.',
  },
  {
    label: 'Следим за обещанной оплатой',
    caption:
      'Ответ клиента и обещанная дата остаются в деле. Если срок прошёл, задолженность снова требует внимания.',
  },
  {
    label: 'Учитываем реальные поступления',
    caption:
      'Поступления сопоставляются со счетами. По оплаченным счетам напоминания прекращаются, по остальным работа продолжается.',
  },
];
const faqs = [
  [
    'Как начать работу?',
    'Загрузите реестр счетов в CSV из Excel или 1С. Mandato соберёт дела по контрагентам и договорам, покажет расхождения и недостающие документы. После проверки можно настроить напоминания.',
  ],
  [
    'Нужно сразу подключать 1С и банк?',
    'Нет. Для начала достаточно выгрузки счетов. Регулярный обмен с 1С, Диадоком и банком можно настроить позже, когда будут доступны ваши подключения.',
  ],
  [
    'Нужно согласовывать каждое письмо?',
    'Нет. После подключения почты и утверждения правил обычные напоминания отправляются автоматически. Споры и расхождения передаются бухгалтеру, а скидка, рассрочка и переход к претензии — руководителю.',
  ],
  [
    'Что делать, если покупатель оспаривает долг?',
    'Напоминания по спорному делу приостанавливаются. Бухгалтер видит причину спора, документы и переписку в карточке и решает, что нужно уточнить у клиента.',
  ],
  [
    'Mandato принимает деньги покупателей?',
    'Нет. Клиенты платят вашей компании по вашим реквизитам. Вы загружаете выписку или подключаете банк, сопоставляете поступления со счетами и видите остаток задолженности.',
  ],
  [
    'Можно начать с небольшой части реестра?',
    'Да. Начните с нескольких договоров, проверьте результат аудита и согласуйте правила напоминаний с руководителем. Затем добавьте остальные счета.',
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
              Получайте оплату.<span>Без ежедневных напоминаний вручную.</span>
            </h1>
            <div className="hero-bottom">
              <div>
                <p>
                  Mandato проверяет задолженность, напоминает клиентам и следит за обещанными
                  сроками. Ваша команда разбирает споры и согласует условия оплаты.
                </p>
                <a href="/app" className="button button-lime">
                  Загрузить реестр <ArrowUpRight size={20} />
                </a>
                <button className="hero-watch" onClick={scrollWorkflow}>
                  <span>
                    <Play size={12} fill="currentColor" />
                  </span>
                  Как это работает
                </button>
              </div>
            </div>
          </div>
          <aside className="hero-workspace" aria-label="Как устроен рабочий день в Mandato">
            <div className="hero-workspace-title">
              Напоминания уходят сами.
              <br />
              <span>Важные решения — за вами.</span>
            </div>
            <div className="hero-workspace-item">
              <span className="hero-workspace-icon">
                <Settings2 size={17} />
              </span>
              <div>
                <strong>Mandato напоминает об оплате</strong>
                <p>Письма и контроль обещанных сроков</p>
              </div>
              <span className="hero-workspace-badge">По правилам</span>
            </div>
            <div className="hero-workspace-item">
              <span className="hero-workspace-icon">
                <FileText size={17} />
              </span>
              <div>
                <strong>Бухгалтер разбирает расхождения</strong>
                <p>Документы, спорные суммы и поступления</p>
              </div>
              <ArrowUpRight size={16} />
            </div>
            <div className="hero-workspace-item">
              <span className="hero-workspace-icon">
                <ShieldCheck size={17} />
              </span>
              <div>
                <strong>Руководитель согласует условия</strong>
                <p>Скидка, рассрочка или претензия</p>
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
            <h2>Вся работа по договору — в одном деле.</h2>
            <div className="intro-copy">
              <p className="large-copy">
                Сразу видно, кто должен, что мешает оплате и когда нужно связаться с клиентом.
              </p>
              <p>
                Счета, документы, переписка и поступления собраны по контрагенту и договору. Не
                нужно искать историю в почте и переносить сроки из одной таблицы в другую.
              </p>
              <a href="/app" className="text-link">
                Загрузить реестр <ArrowUpRight size={18} />
              </a>
            </div>
          </div>
          <div className="benefit-row">
            <div>
              <h3>Понятный остаток долга</h3>
              <p>Счета, частичные оплаты и расхождения видны вместе.</p>
            </div>
            <div>
              <h3>Напоминания автоматически</h3>
              <p>Клиенты получают письма по расписанию и правилам вашей компании.</p>
            </div>
            <div>
              <h3>Споры не теряются</h3>
              <p>Документы, разногласия и запросы на рассрочку попадают к ответственному.</p>
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
            <p>От проверки задолженности до подтверждённой оплаты — с понятным следующим шагом.</p>
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
              Начните с Excel.
              <br />
              <span className="muted">Добавляйте подключения.</span>
            </h2>
            <p>
              Загрузите счета из таблицы. Затем подключите учётную систему, документы и банк, чтобы
              обновлять данные без повторных выгрузок.
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
        <section className="calculator section-pad reveal" aria-label="Стоимость задержки оплаты">
          <div className="calc-copy">
            <h2>Во сколько обходится задержка оплаты</h2>
            <p>
              Если покрываете неоплаченные счета кредитом, посчитайте проценты за время ожидания.
              Укажите сумму и ставку своего кредита.
            </p>
          </div>
          <div className="calc-card">
            <div className="calc-input-label">
              <label htmlFor="amount">Сумма неоплаченных счетов</label>
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
                Задержка оплаты
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
                Ставка по кредиту, годовых
                <div>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    step="0.1"
                    value={rate}
                    onChange={(e) => setRate(Math.max(1, Math.min(60, +e.target.value)))}
                  />
                  <span>%</span>
                </div>
              </label>
            </div>
            <div className="calc-result">
              <span>Проценты за время ожидания</span>
              <output>{money(Math.round((amount * rate * days) / 365))}</output>
              <span>При указанной сумме, сроке и ставке. Без банковских комиссий.</span>
            </div>
          </div>
        </section>
        <section className="control section-pad reveal">
          <h2>Автоматизация, которая следует вашим правилам</h2>
          <div className="control-bottom">
            <p>
              Выберите расписание, частоту и тон писем. После подключения почты руководитель
              включает автоматические напоминания. Споры и новые условия оплаты остаются за вашей
              командой.
            </p>
            <div className="policy-points">
              <span>
                <Check size={16} /> Расписание и частота контактов
              </span>
              <span>
                <Check size={16} /> Остановка напоминаний при споре
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
            <p>Для бухгалтерии, юриста и руководителя — в одном кабинете.</p>
          </div>
          <div className="pricing-grid">
            <article className="price-card">
              <div className="price-label">ДЛЯ ВАШЕЙ КОМАНДЫ</div>
              <h3>
                14 900 ₽ <span>/ месяц</span>
              </h3>
              <p>От загрузки счетов до контроля поступлений.</p>
              <ul>
                {[
                  'Дела по контрагентам и договорам',
                  'Автоматические напоминания по вашим правилам',
                  'Контроль обещаний, оплат и спорных вопросов',
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
              <div className="price-label">ПОМОЩЬ С ЗАПУСКОМ</div>
              <h3>Настроим вместе</h3>
              <p>Поможем подготовить данные и запустить работу команды.</p>
              <ul>
                {[
                  'Разбор структуры задолженности',
                  'Настройка напоминаний и согласований',
                  'Подготовка реестра для команды',
                  'Стоимость по объёму и задачам',
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
        <section className="faq section-pad reveal" aria-label="Вопросы и ответы">
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
        <section className="final-cta" aria-label="Начните со своего реестра">
          <h2>Начните со своего реестра</h2>
          <a href="/app" className="button button-lime">
            Загрузить реестр <MoveUpRight size={20} />
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
