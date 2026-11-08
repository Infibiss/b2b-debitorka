import { t } from '../i18n';
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
      <StoryLink>{t('Обсудить на демонстрации')}</StoryLink>
    </section>
  );
}
const caseSteps = [
  {
    title: t('Собрать основание'),
    status: t('Проверка документов'),
    amount: '600 000 ₽',
    label: t('Остаток по счёту'),
    event: t('Счёт и договор собраны в одном деле'),
    detail: t(
      'Проверьте сумму, срок оплаты и документы, которые подтверждают поставку или оказание услуг.'
    ),
    next: t('Уточнить недостающие документы'),
    note: t('Основание долга'),
    icon: FileText,
  },
  {
    title: t('Договориться'),
    status: t('Обещание оплаты'),
    amount: '600 000 ₽',
    label: t('Остаток по счёту'),
    event: t('«Оплатим 200 000 ₽ до 18 ноября»'),
    detail: t(
      'Сумма и дата обещания сохраняются отдельно от оплаты. Срок за пределами полномочий передаётся сотруднику.'
    ),
    next: t('Проверить поступление к обещанной дате'),
    note: t('Ответ покупателя'),
    icon: Mail,
  },
  {
    title: t('Сверить поступление'),
    status: t('Частичная оплата'),
    amount: '400 000 ₽',
    label: t('Остаток после сверки'),
    event: t('Поступление 200 000 ₽ сопоставлено со счётом'),
    detail: t(
      'Загрузите выписку, проверьте платёж и подтвердите распределение. Только после этого меняется остаток.'
    ),
    next: t('Продолжить работу с остатком'),
    note: t('Банковская выписка'),
    icon: Landmark,
  },
  {
    title: t('Передать юристу'),
    status: t('Проверка специалиста'),
    amount: '400 000 ₽',
    label: t('Сумма основного долга'),
    event: t('Документы и история готовы к проверке'),
    detail: t(
      'Юрист проверяет основания и расчёт требований. Подача в суд выполняется специалистом и фиксируется в деле.'
    ),
    next: t('Согласовать дальнейшие действия'),
    note: t('Юридическое дело'),
    icon: ShieldCheck,
  },
];
function CaseJourney() {
  const [active, setActive] = useState(0);
  const step = caseSteps[active];
  const Icon = step.icon;
  return (
    <div className="story-journey">
      <div className="story-step-nav" aria-label={t('Выберите этап дела')}>
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
          <span>{t('ООО «Северстрой»')}</span>
          <span className="story-status">{step.status}</span>
        </div>
        <div className="story-case-body" key={active}>
          <div className="story-case-value">
            <span>{t('Счёт № 417 · договор поставки')}</span>
            <strong>{step.amount}</strong>
            <p>{step.label}</p>
            <div className="story-case-file">
              <FileText size={18} aria-hidden="true" />
              <span>{t('Договор и подтверждение поставки')}</span>
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
        <p className="story-kicker">{t('Продукт Mandato')}</p>
        <h1>
          {t('У каждого долга —')}
          <br />
          <span>{t('понятный следующий шаг')}</span>
        </h1>
        <p className="story-lead">
          {t(
            'От первого напоминания до юридического дела: счета, переписка, обещания и поступления связаны в одном рабочем процессе.'
          )}
        </p>
        <div className="story-actions">
          <StoryLink>{t('Посмотреть в работе')}</StoryLink>
          <a className="story-text-link" href="#case-journey">
            {t('Пройти путь одного дела')} <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
      </section>
      <section className="story-section story-journey-section" id="case-journey">
        <div className="story-section-heading">
          <div>
            <p className="story-kicker">{t('Один долг, вся история')}</p>
            <h2>
              {t('Не теряйте контекст')}
              <br />
              {t('между этапами')}
            </h2>
          </div>
          <p>
            {t(
              'Выберите этап и посмотрите, что меняется в деле. Суммы и названия в примере условные.'
            )}
          </p>
        </div>
        <CaseJourney />
      </section>
      <section className="story-white">
        <div className="story-section story-authority">
          <div>
            <p className="story-kicker">{t('Работа в пределах мандата')}</p>
            <h2>
              {t('Вы задаёте правила.')}
              <br />
              {t('Mandato следует им.')}
            </h2>
            <p className="story-body-copy">
              {t(
                'Мандат — это согласованные полномочия для работы с покупателем: допустимые контакты, сроки и условия. Когда ситуация выходит за эти рамки, решение остаётся за вашей командой.'
              )}
            </p>
            <a className="story-text-link" href="/security">
              {t('Как устроен контроль')} <ArrowRight size={18} aria-hidden="true" />
            </a>
          </div>
          <div className="story-rule-sheet">
            <div className="story-sheet-heading">
              <ShieldCheck size={22} aria-hidden="true" />
              <h3>{t('Правила по покупателю')}</h3>
            </div>
            <div>
              <span>{t('Напоминание по сроку')}</span>
              <strong>
                <Check size={16} aria-hidden="true" />
                {t('По правилам')}
              </strong>
            </div>
            <div>
              <span>{t('Обещание в допустимый срок')}</span>
              <strong>
                <Check size={16} aria-hidden="true" />
                {t('В рамках мандата')}
              </strong>
            </div>
            <div>
              <span>{t('Скидка или новая рассрочка')}</span>
              <strong className="story-rule-review">{t('На согласование')}</strong>
            </div>
            <div>
              <span>{t('Спор по поставке')}</span>
              <strong className="story-rule-review">{t('Сотруднику')}</strong>
            </div>
            <p>
              {t(
                'Автоматическая обработка ответов и каналы связи требуют отдельной настройки для организации.'
              )}
            </p>
          </div>
        </div>
      </section>
      <section className="story-section">
        <div className="story-section-heading">
          <div>
            <p className="story-kicker">{t('Три опоры процесса')}</p>
            <h2>
              {t('Факты отдельно.')}
              <br />
              {t('Решения под контролем.')}
            </h2>
          </div>
          <p>
            {t(
              'ИИ помогает разобрать ответ покупателя. Расчёт долга, проверка полномочий и подтверждение оплаты опираются на данные и правила.'
            )}
          </p>
        </div>
        <div className="story-principles">
          <article>
            <span>01</span>
            <h3>{t('Обещание — ещё не оплата')}</h3>
            <p>
              {t(
                'Договорённость получает сумму и срок. Поступление подтверждается отдельно, по банковскому источнику.'
              )}
            </p>
          </article>
          <article>
            <span>02</span>
            <h3>{t('У каждого действия есть история')}</h3>
            <p>
              {t(
                'В деле сохраняются переписка, изменения, документы и согласования. Коллега продолжает работу с тем же контекстом.'
              )}
            </p>
          </article>
          <article>
            <span>03</span>
            <h3>{t('Судебный этап ведёт специалист')}</h3>
            <p>
              {t(
                'Система помогает собрать документы и расчёты. Юрист проверяет пакет, а подача и исполнение фиксируются по подтверждающим материалам.'
              )}
            </p>
          </article>
        </div>
      </section>
      <StoryEnd
        title={t('Разберите один долг вместе с нами')}
        text={t(
          'На демонстрации покажем, как собрать дело, согласовать правила и проверить поступление. Начать можно с реестра счетов.'
        )}
      />
    </div>
  );
}
const roles = [
  {
    name: t('Руководителю'),
    title: t('Видеть деньги и решения, которые нельзя откладывать'),
    text: t(
      'Портфель показывает задолженность и ход работы по покупателям. Вопросы по условиям оплаты и юридической эскалации приходят на согласование.'
    ),
    task: t('Покупатель просит изменить условия'),
    action: t('Решить, допустима ли новая рассрочка'),
    evidence: [
      t('Текущий остаток и обещания'),
      t('История контактов'),
      t('Предложение и причина согласования'),
    ],
  },
  {
    name: t('Бухгалтерии'),
    title: t('Сверять поступления, сохраняя связь со счётом'),
    text: t(
      'Загрузите счета и выписку, проверьте совпадения и распределите частичные оплаты. Нераспределённый платёж остаётся отдельной задачей.'
    ),
    task: t('В выписке появился входящий платёж'),
    action: t('Проверить источник и распределить сумму'),
    evidence: [
      t('Плательщик и назначение платежа'),
      t('Счета и текущие остатки'),
      t('История подтверждённых распределений'),
    ],
  },
  {
    name: t('Менеджеру'),
    title: t('Продолжать разговор с покупателем с нужного места'),
    text: t(
      'В карточке дела видны предыдущие обращения, ответ покупателя и ближайший срок. Спор или просьбу об особых условиях можно передать ответственному.'
    ),
    task: t('Покупатель назвал новую дату оплаты'),
    action: t('Проверить обещание и следующий срок'),
    evidence: [
      t('Новый ответ и история переписки'),
      t('Сумма и дата обещанного платежа'),
      t('Правила работы с покупателем'),
    ],
  },
  {
    name: t('Юристу'),
    title: t('Начинать с материалов дела, а не с поиска переписки'),
    text: t(
      'Основание долга, документы, расчёт требований и досудебная история собраны вместе. Проверьте пакет и зафиксируйте этапы судебной работы.'
    ),
    task: t('Досудебный срок прошёл без оплаты'),
    action: t('Проверить основания и согласовать пакет'),
    evidence: [
      t('Договор и подтверждение исполнения'),
      t('Расчёт требований и оплаты'),
      t('Претензия и подтверждающие материалы'),
    ],
  },
];
function TeamRoles() {
  const [active, setActive] = useState(0);
  const role = roles[active];
  return (
    <div className="story-roles">
      <div className="story-role-switch" aria-label={t('Выберите роль команды')}>
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
          <span className="story-kicker">{t('Рабочая задача')}</span>
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
        <p className="story-kicker">{t('Для команд, которые продают с отсрочкой')}</p>
        <h1>
          {t('Общая работа с долгом.')}
          <br />
          <span>{t('Своя задача у каждого.')}</span>
        </h1>
        <p className="story-lead">
          {t(
            'Mandato связывает бухгалтерию, менеджера, руководителя и юриста вокруг одного дела — с понятной историей, ответственностью и ближайшим действием.'
          )}
        </p>
        <div className="story-actions">
          <StoryLink>{t('Показать нашей команде')}</StoryLink>
          <a className="story-text-link" href="#team-roles">
            {t('Найти свой сценарий')} <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
      </section>
      <section className="story-section" id="team-roles">
        <div className="story-section-heading">
          <div>
            <p className="story-kicker">{t('Четыре роли, один контекст')}</p>
            <h2>
              {t('От общего портфеля')}
              <br />
              {t('к конкретному решению')}
            </h2>
          </div>
          <p>
            {t(
              'Выберите роль, чтобы увидеть рабочий сценарий. Состав команды и доступы настраиваются под организацию.'
            )}
          </p>
        </div>
        <TeamRoles />
      </section>
      <section className="story-white">
        <div className="story-section story-fit">
          <div>
            <p className="story-kicker">{t('Где начать')}</p>
            <h2>
              {t('Когда продажи растут,')}
              <br />
              {t('а оплаты задерживаются')}
            </h2>
            <p className="story-body-copy">
              {t(
                'Основной сценарий — B2B-поставщики товаров и услуг с отсрочкой платежа и регулярной просрочкой покупателей.'
              )}
            </p>
          </div>
          <div className="story-fit-list">
            <article>
              <span>01</span>
              <div>
                <h3>{t('Есть реестр, но нет единой истории')}</h3>
                <p>
                  {t(
                    'Счета — в учёте, договорённости — в почте, сроки — у сотрудников. Соберите их вокруг покупателя и дела.'
                  )}
                </p>
              </div>
            </article>
            <article>
              <span>02</span>
              <div>
                <h3>{t('Частичные оплаты требуют внимания')}</h3>
                <p>
                  {t(
                    'Сверяйте поступления со счетами и продолжайте работу с остатком, не закрывая дело по одному обещанию.'
                  )}
                </p>
              </div>
            </article>
            <article>
              <span>03</span>
              <div>
                <h3>{t('Долг пора передать юристу')}</h3>
                <p>
                  {t(
                    'Сохраните досудебную историю и проверьте комплект документов до выбора дальнейшего порядка взыскания.'
                  )}
                </p>
              </div>
            </article>
          </div>
        </div>
      </section>
      <section className="story-section story-bank">
        <div>
          <p className="story-kicker">{t('Банкам и партнёрам')}</p>
          <h2>
            {t('Сервис для работы')}
            <br />
            {t('с дебиторкой клиентов МСБ')}
          </h2>
          <p className="story-body-copy">
            {t(
              'Предлагаем обсудить пилот: отобрать подходящие портфели, согласовать процесс и измерить эффект на реальных делах. Деньги покупателей поступают на счета клиентов.'
            )}
          </p>
          <StoryLink href="/demo?kind=custom" secondary>
            {t('Обсудить пилот')}
          </StoryLink>
        </div>
        <div className="story-pilot">
          <span className="story-status">{t('Предлагаемый формат')}</span>
          <h3>{t('Сначала проверить эффект')}</h3>
          <ol>
            <li>
              <span>01</span>
              <div>
                <strong>{t('Выбрать портфель')}</strong>
                <p>{t('Документально подтверждённые долги без сложного спора.')}</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>{t('Согласовать правила')}</strong>
                <p>{t('Полномочия, подключения, безопасность и участие юристов.')}</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>{t('Сравнить результаты')}</strong>
                <p>{t('Поступления с учётом расходов, сроки и трудозатраты команды.')}</p>
              </div>
            </li>
          </ol>
          <p className="story-pilot-note">
            {t(
              'Пилот и партнёрские условия обсуждаются индивидуально. Измеряемые показатели — цели проверки, а не достигнутые результаты.'
            )}
          </p>
        </div>
      </section>
      <StoryEnd
        title={t('Начните со своего рабочего сценария')}
        text={t(
          'Расскажите, кто ведёт дебиторку, где хранятся счета и что чаще всего тормозит оплату. Покажем подходящий процесс.'
        )}
      />
    </div>
  );
}
const sources = [
  {
    name: t('Реестр счетов'),
    type: t('Импорт файла'),
    label: t('Можно начать с файла'),
    icon: FileText,
    description: t('Загрузка счетов и задолженности с проверкой данных до подтверждения импорта.'),
    requirement: t('Подготовьте реестр с суммами, сроками оплаты и данными покупателей.'),
  },
  {
    name: t('1С'),
    type: t('Учётная система'),
    label: t('После настройки'),
    icon: Database,
    description: t(
      'Получение данных из опубликованного интерфейса 1С. Загрузка отдельных счетов зависит от состава полей и настройки вашей базы.'
    ),
    requirement: t(
      'Администратор 1С подключает доступ на чтение. Перед началом работы проверяем пробную загрузку вашей базы.'
    ),
  },
  {
    name: t('Диадок'),
    type: t('Электронный документооборот'),
    label: t('После настройки'),
    icon: FileText,
    description: t(
      'Получение списка и реквизитов входящих документов организации для проверки источника.'
    ),
    requirement: t(
      'Администратор организации подтверждает доступ. Подписанные оригиналы для юридического дела приложите к документам.'
    ),
  },
  {
    name: t('Банковская выписка'),
    type: t('Файл клиент-банка'),
    label: t('Можно начать с файла'),
    icon: Landmark,
    description: t(
      'Загрузка выписки в текстовом формате 1С:Клиент-Банк. Входящие платежи проверяются перед добавлением.'
    ),
    requirement: t(
      'Укажите свой расчётный счёт и загрузите выписку. Подтверждение поступления и распределение по счетам — отдельные действия.'
    ),
  },
  {
    name: t('Т-Банк'),
    type: t('Выписка через API'),
    label: t('После настройки'),
    icon: Landmark,
    description: t(
      'Чтение операций по согласованному счёту и периоду. Проверенные входящие платежи можно добавить для последующей сверки.'
    ),
    requirement: t(
      'Нужны права на чтение выписки и привязка счёта к вашей организации. Работу с вашим банковским аккаунтом проверяем при подключении.'
    ),
  },
  {
    name: 'DaData',
    type: t('Сведения о контрагенте'),
    label: t('После настройки'),
    icon: Database,
    description: t('Проверка наименования и регистрационного статуса организации по точному ИНН.'),
    requirement: t(
      'Нужны настроенный доступ и доступная квота. Сведения из реестра не являются оценкой платёжеспособности.'
    ),
  },
  {
    name: t('Почта'),
    type: t('Коммуникации с покупателями'),
    label: t('После настройки'),
    icon: Mail,
    description: t('Отправка писем и обработка входящих ответов по правилам вашей организации.'),
    requirement: t(
      'Подключите рабочий ящик с помощью администратора. До запуска напоминаний проверьте отправку письма и получение ответа.'
    ),
  },
];
function IntegrationsStory() {
  return (
    <div className="story-page story-integrations">
      <section className="story-hero">
        <p className="story-kicker">{t('Подключения и источники данных')}</p>
        <h1>
          {t('Учёт, документы и оплата.')}
          <br />
          <span>{t('В одном контексте.')}</span>
        </h1>
        <p className="story-lead">
          {t(
            'Начните с файлов или настройте получение данных из своих систем. Перед добавлением счетов и платежей проверьте источник и подтвердите изменения.'
          )}
        </p>
        <div className="story-actions">
          <StoryLink>{t('Обсудить подключение')}</StoryLink>
          <a className="story-text-link" href="#story-sources">
            {t('Посмотреть источники')} <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
      </section>
      <section className="story-section">
        <div className="story-data-flow" aria-label={t('Порядок работы с данными')}>
          <div>
            <span>{t('01 · Источник')}</span>
            <strong>{t('Получить данные')}</strong>
            <p>{t('Файл или настроенное подключение')}</p>
          </div>
          <ArrowRight aria-hidden="true" />
          <div>
            <span>{t('02 · Проверка')}</span>
            <strong>{t('Увидеть, что изменится')}</strong>
            <p>{t('Состав данных, ошибки и совпадения')}</p>
          </div>
          <ArrowRight aria-hidden="true" />
          <div>
            <span>{t('03 · Подтверждение')}</span>
            <strong>{t('Добавить в работу')}</strong>
            <p>{t('Сохранить основание и историю')}</p>
          </div>
        </div>
      </section>
      <section className="story-white" id="story-sources">
        <div className="story-section">
          <div className="story-section-heading">
            <div>
              <p className="story-kicker">{t('Что можно использовать')}</p>
              <h2>
                {t('Выберите источник.')}
                <br />
                {t('Проверьте условия.')}
              </h2>
            </div>
            <p>
              {t(
                'Прямые подключения требуют настройки для конкретной организации. Наличие источника в списке не означает, что он уже подключён к вашему кабинету.'
              )}
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
                      <strong>{t('Для начала работы')}</strong>
                      <p>{source.requirement}</p>
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
          <p className="story-source-footnote">
            {t(
              'Название внешней системы обозначает источник данных и не означает партнёрство с её владельцем. Возможности прямого обмена проверяются на вашей конфигурации и с вашими разрешениями.'
            )}
          </p>
        </div>
      </section>
      <section className="story-section story-integration-care">
        <div>
          <p className="story-kicker">{t('Контроль качества данных')}</p>
          <h2>
            {t('Источник помогает')}
            <br />
            {t('проверить факт')}
          </h2>
          <p className="story-body-copy">
            {t(
              'Чтение выписки не закрывает счёт автоматически. Сначала поступление проходит проверку, затем вы подтверждаете его связь с задолженностью.'
            )}
          </p>
          <a className="story-text-link" href="/product">
            {t('Как устроено дело')} <ArrowRight size={18} aria-hidden="true" />
          </a>
        </div>
        <div className="story-checklist">
          <article>
            <Check size={19} aria-hidden="true" />
            <div>
              <h3>{t('Неполная выгрузка видна')}</h3>
              <p>
                {t(
                  'Ограниченный объём данных не выдаётся за полный портфель. Состав полученного источника нужно проверить.'
                )}
              </p>
            </div>
          </article>
          <article>
            <Check size={19} aria-hidden="true" />
            <div>
              <h3>{t('Повторы проверяются')}</h3>
              <p>
                {t(
                  'Повторная загрузка не должна становиться новым поступлением. Изменённые данные требуют отдельного внимания.'
                )}
              </p>
            </div>
          </article>
          <article>
            <Check size={19} aria-hidden="true" />
            <div>
              <h3>{t('Доступ выдаётся организации')}</h3>
              <p>
                {t(
                  'Параметры прямого подключения настраиваются для вашего кабинета. Регистрация сама по себе не открывает внешние источники.'
                )}
              </p>
            </div>
          </article>
        </div>
      </section>
      <StoryEnd
        title={t('Начните с того, что уже есть')}
        text={t(
          'Для первого разбора достаточно понять, где хранятся счета и в каком виде доступна выписка. Остальные подключения спланируем под ваш процесс.'
        )}
      />
    </div>
  );
}
export function PublicStoryPages({ kind }: { kind: PublicStoryKind }) {
  if (kind === 'product') return <ProductStory />;
  if (kind === 'solutions') return <SolutionsStory />;
  return <IntegrationsStory />;
}
