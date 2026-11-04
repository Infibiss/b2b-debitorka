import { useState, type ReactNode } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  FileText,
  ShieldCheck,
  Clock3,
  Landmark,
  Mail,
  Database,
  ChevronDown,
} from 'lucide-react';
import './public-story-pages.css';

export type PublicStoryKind = 'product' | 'solutions' | 'integrations';

function StoryLink({
  children,
  href = '/demo',
  secondary = false,
}: {
  children: ReactNode;
  href?: string;
  secondary?: boolean;
}) {
  return (
    <a className={`story-button${secondary ? ' story-button-secondary' : ''}`} href={href}>
      {children}
      <ArrowUpRight size={18} aria-hidden="true" />
    </a>
  );
}
function StoryEnd({ title, text }: { title: string; text: string }) {
  return (
    <section className="story-end">
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
      <StoryLink>Обсудить на демонстрации</StoryLink>
    </section>
  );
}
const caseSteps = [
  {
    title: 'Собрать основание',
    status: 'Проверка документов',
    amount: '600 000 ₽',
    label: 'Остаток по счёту',
    event: 'Счёт и договор собраны в одном деле',
    detail:
      'Проверьте сумму, срок оплаты и документы, которые подтверждают поставку или оказание услуг.',
    next: 'Уточнить недостающие документы',
    note: 'Основание долга',
    icon: FileText,
  },
  {
    title: 'Договориться',
    status: 'Обещание оплаты',
    amount: '600 000 ₽',
    label: 'Остаток по счёту',
    event: '«Оплатим 200 000 ₽ до 18 ноября»',
    detail:
      'Сумма и дата обещания сохраняются отдельно от оплаты. Срок за пределами полномочий передаётся сотруднику.',
    next: 'Проверить поступление к обещанной дате',
    note: 'Ответ покупателя',
    icon: Mail,
  },
  {
    title: 'Сверить поступление',
    status: 'Частичная оплата',
    amount: '400 000 ₽',
    label: 'Остаток после сверки',
    event: 'Поступление 200 000 ₽ сопоставлено со счётом',
    detail:
      'Загрузите выписку, проверьте платёж и подтвердите распределение. Только после этого меняется остаток.',
    next: 'Продолжить работу с остатком',
    note: 'Банковская выписка',
    icon: Landmark,
  },
  {
    title: 'Передать юристу',
    status: 'Проверка специалиста',
    amount: '400 000 ₽',
    label: 'Сумма основного долга',
    event: 'Документы и история готовы к проверке',
    detail:
      'Юрист проверяет основания и расчёт требований. Подача в суд выполняется специалистом и фиксируется в деле.',
    next: 'Согласовать дальнейшие действия',
    note: 'Юридическое дело',
    icon: ShieldCheck,
  },
];
function CaseJourney() {
  const [active, setActive] = useState(0);
  const step = caseSteps[active];
  const Icon = step.icon;
  return (
    <div className="story-journey">
      <div className="story-step-nav" aria-label="Выберите этап дела">
        {caseSteps.map((item, i) => (
          <button
            key={item.title}
            aria-pressed={i === active}
            aria-controls="story-case-preview"
            onClick={() => setActive(i)}
          >
            <span>0{i + 1}</span>
            {item.title}
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        ))}
      </div>
      <div className="story-case" id="story-case-preview" aria-live="polite" aria-atomic="true">
        <div className="story-case-top">
          <span>ООО «Северстрой»</span>
          <span className="story-status">{step.status}</span>
        </div>
        <div className="story-case-body" key={active}>
          <div className="story-case-value">
            <span>Счёт № 417 · договор поставки</span>
            <strong>{step.amount}</strong>
            <p>{step.label}</p>
            <div className="story-case-file">
              <FileText size={18} aria-hidden="true" />
              <span>Договор и подтверждение поставки</span>
            </div>
          </div>
          <div className="story-case-event">
            <div className="story-case-source">
              <Icon size={20} aria-hidden="true" />
              {step.note}
            </div>
            <h3>{step.event}</h3>
            <p>{step.detail}</p>
            <div className="story-case-next">
              <Clock3 size={17} aria-hidden="true" />
              <span>{step.next}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
function ProductStory() {
  return (
    <div className="story-page story-product">
      <section className="story-hero">
        <p className="story-kicker">Продукт Mandato</p>
        <h1>
          У каждого долга —<br />
          <span>понятный следующий шаг</span>
        </h1>
        <p className="story-lead">
          От первого напоминания до юридического дела: счета, переписка, обещания и поступления
          связаны в одном рабочем процессе.
        </p>
        <div className="story-actions">
          <StoryLink>Посмотреть в работе</StoryLink>
          <a className="story-text-link" href="#case-journey">
            Пройти путь одного дела <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
      </section>
      <section className="story-section story-journey-section" id="case-journey">
        <div className="story-section-heading">
          <div>
            <p className="story-kicker">Один долг, вся история</p>
            <h2>
              Не теряйте контекст
              <br />
              между этапами
            </h2>
          </div>
          <p>
            Выберите этап и посмотрите, что меняется в деле. Суммы и названия в примере условные.
          </p>
        </div>
        <CaseJourney />
      </section>
      <section className="story-white">
        <div className="story-section story-authority">
          <div>
            <p className="story-kicker">Работа в пределах мандата</p>
            <h2>
              Вы задаёте правила.
              <br />
              Mandato следует им.
            </h2>
            <p className="story-body-copy">
              Мандат — это согласованные полномочия для работы с покупателем: допустимые контакты,
              сроки и условия. Когда ситуация выходит за эти рамки, решение остаётся за вашей
              командой.
            </p>
            <a className="story-text-link" href="/security">
              Как устроен контроль <ArrowRight size={18} aria-hidden="true" />
            </a>
          </div>
          <div className="story-rule-sheet">
            <div className="story-sheet-heading">
              <ShieldCheck size={22} aria-hidden="true" />
              <h3>Правила по покупателю</h3>
            </div>
            <div>
              <span>Напоминание по сроку</span>
              <strong>
                <Check size={16} aria-hidden="true" />
                По правилам
              </strong>
            </div>
            <div>
              <span>Обещание в допустимый срок</span>
              <strong>
                <Check size={16} aria-hidden="true" />В рамках мандата
              </strong>
            </div>
            <div>
              <span>Скидка или новая рассрочка</span>
              <strong className="story-rule-review">На согласование</strong>
            </div>
            <div>
              <span>Спор по поставке</span>
              <strong className="story-rule-review">Сотруднику</strong>
            </div>
            <p>
              Автоматическая обработка ответов и каналы связи требуют отдельной настройки для
              организации.
            </p>
          </div>
        </div>
      </section>
      <section className="story-section">
        <div className="story-section-heading">
          <div>
            <p className="story-kicker">Три опоры процесса</p>
            <h2>
              Факты отдельно.
              <br />
              Решения под контролем.
            </h2>
          </div>
          <p>
            ИИ помогает разобрать ответ покупателя. Расчёт долга, проверка полномочий и
            подтверждение оплаты опираются на данные и правила.
          </p>
        </div>
        <div className="story-principles">
          <article>
            <span>01</span>
            <h3>Обещание — ещё не оплата</h3>
            <p>
              Договорённость получает сумму и срок. Поступление подтверждается отдельно, по
              банковскому источнику.
            </p>
          </article>
          <article>
            <span>02</span>
            <h3>У каждого действия есть история</h3>
            <p>
              В деле сохраняются переписка, изменения, документы и согласования. Коллега продолжает
              работу с тем же контекстом.
            </p>
          </article>
          <article>
            <span>03</span>
            <h3>Судебный этап ведёт специалист</h3>
            <p>
              Система помогает собрать документы и расчёты. Юрист проверяет пакет, а подача и
              исполнение фиксируются по подтверждающим материалам.
            </p>
          </article>
        </div>
      </section>
      <StoryEnd
        title="Разберите один долг вместе с нами"
        text="На демонстрации покажем, как собрать дело, согласовать правила и проверить поступление. Начать можно с реестра счетов."
      />
    </div>
  );
}
const roles = [
  {
    name: 'Руководителю',
    title: 'Видеть деньги и решения, которые нельзя откладывать',
    text: 'Портфель показывает задолженность и ход работы по покупателям. Вопросы по условиям оплаты и юридической эскалации приходят на согласование.',
    task: 'Покупатель просит изменить условия',
    action: 'Решить, допустима ли новая рассрочка',
    evidence: [
      'Текущий остаток и обещания',
      'История контактов',
      'Предложение и причина согласования',
    ],
  },
  {
    name: 'Бухгалтерии',
    title: 'Сверять поступления, сохраняя связь со счётом',
    text: 'Загрузите счета и выписку, проверьте совпадения и распределите частичные оплаты. Нераспределённый платёж остаётся отдельной задачей.',
    task: 'В выписке появился входящий платёж',
    action: 'Проверить источник и распределить сумму',
    evidence: [
      'Плательщик и назначение платежа',
      'Счета и текущие остатки',
      'История подтверждённых распределений',
    ],
  },
  {
    name: 'Менеджеру',
    title: 'Продолжать разговор с покупателем с нужного места',
    text: 'В карточке дела видны предыдущие обращения, ответ покупателя и ближайший срок. Спор или просьбу об особых условиях можно передать ответственному.',
    task: 'Покупатель назвал новую дату оплаты',
    action: 'Проверить обещание и следующий срок',
    evidence: [
      'Новый ответ и история переписки',
      'Сумма и дата обещанного платежа',
      'Правила работы с покупателем',
    ],
  },
  {
    name: 'Юристу',
    title: 'Начинать с материалов дела, а не с поиска переписки',
    text: 'Основание долга, документы, расчёт требований и досудебная история собраны вместе. Проверьте пакет и зафиксируйте этапы судебной работы.',
    task: 'Досудебный срок прошёл без оплаты',
    action: 'Проверить основания и согласовать пакет',
    evidence: [
      'Договор и подтверждение исполнения',
      'Расчёт требований и оплаты',
      'Претензия и подтверждающие материалы',
    ],
  },
];
function TeamRoles() {
  const [active, setActive] = useState(0);
  const role = roles[active];
  return (
    <div className="story-roles">
      <div className="story-role-switch" aria-label="Выберите роль команды">
        {roles.map((r, i) => (
          <button
            key={r.name}
            aria-pressed={active === i}
            aria-controls="story-role-content"
            onClick={() => setActive(i)}
          >
            {r.name}
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        ))}
      </div>
      <div
        className="story-role-content"
        id="story-role-content"
        aria-live="polite"
        aria-atomic="true"
        key={active}
      >
        <div>
          <h3>{role.title}</h3>
          <p>{role.text}</p>
        </div>
        <div className="story-role-task">
          <span className="story-kicker">Рабочая задача</span>
          <h4>{role.task}</h4>
          <ul>
            {role.evidence.map((item) => (
              <li key={item}>
                <Check size={16} aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
          <p>
            <ArrowRight size={18} aria-hidden="true" />
            {role.action}
          </p>
        </div>
      </div>
    </div>
  );
}
function SolutionsStory() {
  return (
    <div className="story-page story-solutions">
      <section className="story-hero">
        <p className="story-kicker">Для команд, которые продают с отсрочкой</p>
        <h1>
          Общая работа с долгом.
          <br />
          <span>Своя задача у каждого.</span>
        </h1>
        <p className="story-lead">
          Mandato связывает бухгалтерию, менеджера, руководителя и юриста вокруг одного дела — с
          понятной историей, ответственностью и ближайшим действием.
        </p>
        <div className="story-actions">
          <StoryLink>Показать нашей команде</StoryLink>
          <a className="story-text-link" href="#team-roles">
            Найти свой сценарий <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
      </section>
      <section className="story-section" id="team-roles">
        <div className="story-section-heading">
          <div>
            <p className="story-kicker">Четыре роли, один контекст</p>
            <h2>
              От общего портфеля
              <br />к конкретному решению
            </h2>
          </div>
          <p>
            Выберите роль, чтобы увидеть рабочий сценарий. Состав команды и доступы настраиваются
            под организацию.
          </p>
        </div>
        <TeamRoles />
      </section>
      <section className="story-white">
        <div className="story-section story-fit">
          <div>
            <p className="story-kicker">Где начать</p>
            <h2>
              Когда продажи растут,
              <br />а оплаты задерживаются
            </h2>
            <p className="story-body-copy">
              Основной сценарий — B2B-поставщики товаров и услуг с отсрочкой платежа и регулярной
              просрочкой покупателей.
            </p>
          </div>
          <div className="story-fit-list">
            <article>
              <span>01</span>
              <div>
                <h3>Есть реестр, но нет единой истории</h3>
                <p>
                  Счета — в учёте, договорённости — в почте, сроки — у сотрудников. Соберите их
                  вокруг покупателя и дела.
                </p>
              </div>
            </article>
            <article>
              <span>02</span>
              <div>
                <h3>Частичные оплаты требуют внимания</h3>
                <p>
                  Сверяйте поступления со счетами и продолжайте работу с остатком, не закрывая дело
                  по одному обещанию.
                </p>
              </div>
            </article>
            <article>
              <span>03</span>
              <div>
                <h3>Долг пора передать юристу</h3>
                <p>
                  Сохраните досудебную историю и проверьте комплект документов до выбора дальнейшего
                  порядка взыскания.
                </p>
              </div>
            </article>
          </div>
        </div>
      </section>
      <section className="story-section story-bank">
        <div>
          <p className="story-kicker">Банкам и партнёрам</p>
          <h2>
            Сервис для работы
            <br />с дебиторкой клиентов МСБ
          </h2>
          <p className="story-body-copy">
            Предлагаем обсудить пилот: отобрать подходящие портфели, согласовать процесс и измерить
            эффект на реальных делах. Деньги покупателей поступают на счета клиентов.
          </p>
          <StoryLink href="/demo?kind=custom" secondary>
            Обсудить пилот
          </StoryLink>
        </div>
        <div className="story-pilot">
          <span className="story-status">Предлагаемый формат</span>
          <h3>Сначала проверить эффект</h3>
          <ol>
            <li>
              <span>01</span>
              <div>
                <strong>Выбрать портфель</strong>
                <p>Документально подтверждённые долги без сложного спора.</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>Согласовать правила</strong>
                <p>Полномочия, подключения, безопасность и участие юристов.</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>Сравнить результаты</strong>
                <p>Поступления с учётом расходов, сроки и трудозатраты команды.</p>
              </div>
            </li>
          </ol>
          <p className="story-pilot-note">
            Пилот и партнёрские условия обсуждаются индивидуально. Измеряемые показатели — цели
            проверки, а не достигнутые результаты.
          </p>
        </div>
      </section>
      <StoryEnd
        title="Начните со своего рабочего сценария"
        text="Расскажите, кто ведёт дебиторку, где хранятся счета и что чаще всего тормозит оплату. Покажем подходящий процесс."
      />
    </div>
  );
}
const sources = [
  {
    name: 'Реестр счетов',
    type: 'Импорт файла',
    label: 'Можно начать с файла',
    icon: FileText,
    description: 'Загрузка счетов и задолженности с проверкой данных до подтверждения импорта.',
    requirement: 'Подготовьте реестр с суммами, сроками оплаты и данными покупателей.',
  },
  {
    name: '1С',
    type: 'Учётная система',
    label: 'После настройки',
    icon: Database,
    description:
      'Получение данных из опубликованного интерфейса 1С. Загрузка отдельных счетов зависит от состава полей и настройки вашей базы.',
    requirement:
      'Администратор 1С подключает доступ на чтение. Перед началом работы проверяем пробную загрузку вашей базы.',
  },
  {
    name: 'Диадок',
    type: 'Электронный документооборот',
    label: 'После настройки',
    icon: FileText,
    description:
      'Получение списка и реквизитов входящих документов организации для проверки источника.',
    requirement:
      'Администратор организации подтверждает доступ. Подписанные оригиналы для юридического дела приложите к документам.',
  },
  {
    name: 'Банковская выписка',
    type: 'Файл клиент-банка',
    label: 'Можно начать с файла',
    icon: Landmark,
    description:
      'Загрузка выписки в текстовом формате 1С:Клиент-Банк. Входящие платежи проверяются перед добавлением.',
    requirement:
      'Укажите свой расчётный счёт и загрузите выписку. Подтверждение поступления и распределение по счетам — отдельные действия.',
  },
  {
    name: 'Т-Банк',
    type: 'Выписка через API',
    label: 'После настройки',
    icon: Landmark,
    description:
      'Чтение операций по согласованному счёту и периоду. Проверенные входящие платежи можно добавить для последующей сверки.',
    requirement:
      'Нужны права на чтение выписки и привязка счёта к вашей организации. Работу с вашим банковским аккаунтом проверяем при подключении.',
  },
  {
    name: 'DaData',
    type: 'Сведения о контрагенте',
    label: 'После настройки',
    icon: Database,
    description: 'Проверка наименования и регистрационного статуса организации по точному ИНН.',
    requirement:
      'Нужны настроенный доступ и доступная квота. Сведения из реестра не являются оценкой платёжеспособности.',
  },
  {
    name: 'Почта',
    type: 'Коммуникации с покупателями',
    label: 'После настройки',
    icon: Mail,
    description: 'Отправка писем и обработка входящих ответов по правилам вашей организации.',
    requirement:
      'Подключите рабочий ящик с помощью администратора. До запуска напоминаний проверьте отправку письма и получение ответа.',
  },
];
function IntegrationsStory() {
  return (
    <div className="story-page story-integrations">
      <section className="story-hero">
        <p className="story-kicker">Подключения и источники данных</p>
        <h1>
          Учёт, документы и оплата.
          <br />
          <span>В одном контексте.</span>
        </h1>
        <p className="story-lead">
          Начните с файлов или настройте получение данных из своих систем. Перед добавлением счетов
          и платежей проверьте источник и подтвердите изменения.
        </p>
        <div className="story-actions">
          <StoryLink>Обсудить подключение</StoryLink>
          <a className="story-text-link" href="#story-sources">
            Посмотреть источники <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
      </section>
      <section className="story-section">
        <div className="story-data-flow" aria-label="Порядок работы с данными">
          <div>
            <span>01 · Источник</span>
            <strong>Получить данные</strong>
            <p>Файл или настроенное подключение</p>
          </div>
          <ArrowRight aria-hidden="true" />
          <div>
            <span>02 · Проверка</span>
            <strong>Увидеть, что изменится</strong>
            <p>Состав данных, ошибки и совпадения</p>
          </div>
          <ArrowRight aria-hidden="true" />
          <div>
            <span>03 · Подтверждение</span>
            <strong>Добавить в работу</strong>
            <p>Сохранить основание и историю</p>
          </div>
        </div>
      </section>
      <section className="story-white" id="story-sources">
        <div className="story-section">
          <div className="story-section-heading">
            <div>
              <p className="story-kicker">Что можно использовать</p>
              <h2>
                Выберите источник.
                <br />
                Проверьте условия.
              </h2>
            </div>
            <p>
              Прямые подключения требуют настройки для конкретной организации. Наличие источника в
              списке не означает, что он уже подключён к вашему кабинету.
            </p>
          </div>
          <div className="story-source-list">
            {sources.map((source) => {
              const Icon = source.icon;
              return (
                <details className="story-source" key={source.name}>
                  <summary>
                    <div className="story-source-name">
                      <Icon size={22} aria-hidden="true" />
                      <div>
                        <h3>{source.name}</h3>
                        <span>{source.type}</span>
                      </div>
                    </div>
                    <span
                      className={`story-source-label${source.label === 'Можно начать с файла' ? ' story-source-file' : ''}`}
                    >
                      {source.label}
                    </span>
                    <ChevronDown size={18} className="story-source-chevron" aria-hidden="true" />
                  </summary>
                  <div className="story-source-detail">
                    <p>{source.description}</p>
                    <div>
                      <strong>Для начала работы</strong>
                      <p>{source.requirement}</p>
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
          <p className="story-source-footnote">
            Название внешней системы обозначает источник данных и не означает партнёрство с её
            владельцем. Возможности прямого обмена проверяются на вашей конфигурации и с вашими
            разрешениями.
          </p>
        </div>
      </section>
      <section className="story-section story-integration-care">
        <div>
          <p className="story-kicker">Контроль качества данных</p>
          <h2>
            Источник помогает
            <br />
            проверить факт
          </h2>
          <p className="story-body-copy">
            Чтение выписки не закрывает счёт автоматически. Сначала поступление проходит проверку,
            затем вы подтверждаете его связь с задолженностью.
          </p>
          <a className="story-text-link" href="/product">
            Как устроено дело <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
        <div className="story-checklist">
          <article>
            <Check size={19} aria-hidden="true" />
            <div>
              <h3>Неполная выгрузка видна</h3>
              <p>
                Ограниченный объём данных не выдаётся за полный портфель. Состав полученного
                источника нужно проверить.
              </p>
            </div>
          </article>
          <article>
            <Check size={19} aria-hidden="true" />
            <div>
              <h3>Повторы проверяются</h3>
              <p>
                Повторная загрузка не должна становиться новым поступлением. Изменённые данные
                требуют отдельного внимания.
              </p>
            </div>
          </article>
          <article>
            <Check size={19} aria-hidden="true" />
            <div>
              <h3>Доступ выдаётся организации</h3>
              <p>
                Параметры прямого подключения настраиваются для вашего кабинета. Регистрация сама по
                себе не открывает внешние источники.
              </p>
            </div>
          </article>
        </div>
      </section>
      <StoryEnd
        title="Начните с того, что уже есть"
        text="Для первого разбора достаточно понять, где хранятся счета и в каком виде доступна выписка. Остальные подключения спланируем под ваш процесс."
      />
    </div>
  );
}
export function PublicStoryPages({ kind }: { kind: PublicStoryKind }) {
  if (kind === 'product') return <ProductStory />;
  if (kind === 'solutions') return <SolutionsStory />;
  return <IntegrationsStory />;
}
