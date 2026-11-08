import { t } from '../i18n';
import { useState } from 'react';
import { Check, Copy, Download, ExternalLink, ShieldCheck } from 'lucide-react';
import './connection-access.css';

type SourceId = 'one_c' | 'diadoc' | 'tbank' | 'dadata' | 'court' | 'fssp' | 'bankruptcy';
type ConnectionStatus = {
  provider: string;
  configured: boolean;
  status: string;
  checked_at: string | null;
};
type Source = {
  id: SourceId;
  name: string;
  owner: string;
  result: string;
  cost: string;
  requirements: string[];
  fields: string[];
  acceptance: string;
  links: { label: string; url: string }[];
  manual?: boolean;
};
const sources: Source[] = [
  {
    id: 'one_c',
    name: t('1С'),
    owner: t('Администратор 1С и бухгалтер'),
    result: t(
      'Чтение вашей публикации OData. Перенос отдельных счетов доступен после настройки полей и сверки.'
    ),
    cost: t(
      'Нужна действующая 1С и настройка её администратором. Новая лицензия или платная услуга здесь не оформляется.'
    ),
    requirements: [
      t('Определить базу, организацию и конфигурацию 1С; согласовать документы и период сверки.'),
      t(
        'Опубликовать стандартный OData и дать серверу Mandato сетевой доступ к согласованному адресу.'
      ),
      t('Создать отдельного пользователя: только чтение нужных объектов, без записи и проведения.'),
      t(
        'Сопоставить поля фактической конфигурации; проверить рубли, сроки оплаты и остатки с бухгалтером.'
      ),
    ],
    fields: [
      t('Адрес публикации, оканчивающийся на /odata/standard.odata'),
      t('Имя коллекции (entity) и соответствие полей (mapping)'),
      t('Для счетов: компания, номер, дата, срок, сумма и оплачено либо остаток'),
      t('Идентификатор организации Mandato; учётная запись — только по защищённому каналу'),
    ],
    acceptance: t(
      'Сравнить несколько счетов с 1С: номер, срок, полная сумма, начальная оплата и остаток. Сначала просмотр, затем отдельное подтверждение.'
    ),
    links: [
      {
        label: t('Публикация OData · 1С'),
        url: 'https://1c-dn.com/anticrisis/tools-and-technologies/embedded-web-client/setting-up/',
      },
      {
        label: t('Права и состав объектов · 1С'),
        url: 'https://1c-dn.com/library/tutorials/1c_standard_subsystems_library_3_1_11/',
      },
    ],
  },
  {
    id: 'diadoc',
    name: t('Диадок / ЭДО'),
    owner: t('Администратор ЭДО и оператор Диадока'),
    result: t(
      'Чтение реквизитов входящих документов Диадока, до 100 за запрос. Содержимое и подпись не проверяются.'
    ),
    cost: t(
      'Нужны ящик организации, права пользователя и согласованный доступ к API. Условия интеграции и лицензии уточняет оператор; платное подключение требует отдельного решения.'
    ),
    requirements: [
      t(
        'Подтвердить действующий ящик вашей организации в Диадоке и право чтения входящих документов.'
      ),
      t('Согласовать с оператором доступ к API и условия действующего договора или лицензии.'),
      t(
        'Подготовить OAuth access token рабочей площадки Diadoc.PublicAPI для сервисного пользователя и идентификатор нужного ящика.'
      ),
      t(
        'Назначить ответственного за обновление истекающего токена; текущий адаптер сам его не обновляет.'
      ),
    ],
    fields: [
      t('Идентификатор ящика организации (box_id)'),
      t('Сервисный пользователь: чтение входящих; площадка Diadoc.PublicAPI'),
      t('Срок действия OAuth access token и ответственный за обновление'),
      t('Идентификатор организации Mandato; сам токен — только по защищённому каналу'),
    ],
    acceptance: t(
      'Проверить реквизиты нескольких входящих документов в своём ящике. Это не проверка оригиналов, подписи или полного архива.'
    ),
    links: [
      { label: t('Доступ к API · Диадок'), url: 'https://www.diadoc.ru/integrations/api' },
      {
        label: t('OAuth · документация'),
        url: 'https://developer.kontur.ru/doc/diadoc-api/authentication.html',
      },
      { label: t('Условия и тарифы'), url: 'https://www.diadoc.ru/price' },
    ],
  },
  {
    id: 'tbank',
    name: t('Банк'),
    owner: t('Владелец счёта и администратор Т-Бизнеса'),
    result: t(
      'Подключите выписку Т-Банка или загрузите выписку другого банка в формате 1CClientBankExchange.'
    ),
    cost: t(
      'T-API бесплатен; нужен существующий кабинет Т-Бизнеса и расчётный счёт. Обслуживание счёта — по вашему банковскому тарифу.'
    ),
    requirements: [
      t('Подтвердить банк и собственный рублёвый расчётный счёт организации.'),
      t(
        'Выпустить токен в Т-Бизнесе с минимальным доступом к выписке выбранного счёта, без прав на платежи.'
      ),
      t('Указать другие собственные счета, чтобы исключить внутренние переводы из поступлений.'),
      t('Выбрать период до 31 дня и сверить реальные поступления с выпиской банка.'),
    ],
    fields: [
      t('Номер собственного рублёвого расчётного счёта: 20 цифр'),
      t('Другие собственные счета для исключения внутренних переводов'),
      t('Доступ токена к выписке, срок действия и ответственный за отзыв'),
      t('Идентификатор организации Mandato; токен — только по защищённому каналу'),
    ],
    acceptance: t(
      'Проверить период, счёт и суммы входящих операций. Подтверждённые поступления распределить по счетам в «Оплатах и сверке».'
    ),
    links: [
      { label: t('Как получить доступ · T-API'), url: 'https://developer.tbank.ru/docs/api/t-api' },
      {
        label: t('Метод выписки'),
        url: 'https://developer.tbank.ru/docs/api/get-api-v-1-statement',
      },
      { label: t('Условия T-API'), url: 'https://www.tbank.ru/business/open-api/' },
    ],
  },
  {
    id: 'dadata',
    name: t('ЕГРЮЛ / ЕГРИП'),
    owner: t('Администратор DaData'),
    result: t(
      'Точный поиск по ИНН и регистрационный статус из снимка DaData. Судебные дела, ФССП и полный реестр банкротств этим не проверяются.'
    ),
    cost: t(
      'Для метода поиска организации заявлено до 10 000 бесплатных запросов в день; нужен существующий аккаунт с подтверждённой почтой и API-ключ.'
    ),
    requirements: [
      t('Подтвердить право использовать существующий аккаунт DaData для этой организации.'),
      t('Выделить API-ключ и проверить доступный лимит поиска организаций по ИНН.'),
      t('Сверить точный ИНН и дату данных; не считать отсутствие отметки проверкой всех рисков.'),
    ],
    fields: [
      t('Идентификатор организации Mandato и доступный лимит запросов'),
      t('Обычный API-ключ DaData — по защищённому каналу; Secret key не требуется'),
    ],
    acceptance: t(
      'Проверить точный ИНН, наименование и дату состояния записи. Отдельно проверить суды, исполнительные производства и банкротство.'
    ),
    links: [
      { label: t('Метод, доступ и лимиты · DaData'), url: 'https://dadata.ru/api/find-party/' },
    ],
  },
  {
    id: 'court',
    name: t('Судебные дела'),
    owner: t('Юрист'),
    manual: true,
    result: t(
      'Официальная ручная проверка в Картотеке арбитражных дел. Автоматическое чтение в Mandato не реализовано.'
    ),
    cost: t(
      'Открыть официальный поиск можно сейчас. Для автоматизации нужны опубликованный разрешённый API, его условия и отдельный адаптер.'
    ),
    requirements: [
      t('Проверить участника по точным реквизитам и найденные дела в КАД.'),
      t('Зафиксировать номер дела, роль организации, ссылку на карточку и дату проверки.'),
    ],
    fields: [
      t('ИНН и наименование участника, номер дела при наличии'),
      t('Для будущей интеграции: документация разрешённого API и условия доступа'),
    ],
    acceptance: t(
      'Юрист сверяет участника и стадию дела по официальной карточке. Отсутствие результата не означает отсутствие всех судебных споров.'
    ),
    links: [{ label: t('Открыть КАД'), url: 'https://kad.arbitr.ru/' }],
  },
  {
    id: 'fssp',
    name: t('ФССП'),
    owner: t('Юрист'),
    manual: true,
    result: t(
      'Официальная ручная проверка исполнительных производств. Автоматическое чтение в Mandato не реализовано.'
    ),
    cost: t(
      'Текущая доступность бесплатного публичного API не подтверждена. Старый API нельзя считать работающим подключением.'
    ),
    requirements: [
      t('Проверить юридическое лицо в официальном банке данных ФССП.'),
      t(
        'Для автоматизации предоставить актуальную документацию разрешённого API, условия использования и выданный доступ; потребуется отдельный адаптер.'
      ),
    ],
    fields: [
      t('Наименование юридического лица, регион и адрес для ручного поиска'),
      t('Номер исполнительного производства при наличии'),
    ],
    acceptance: t(
      'Зафиксировать точное совпадение должника, номер производства, сумму и дату проверки. CAPTCHA и ограничения сайта не обходятся.'
    ),
    links: [{ label: t('Открыть банк данных ФССП'), url: 'https://fssp.gov.ru/iss/ip' }],
  },
  {
    id: 'bankruptcy',
    name: t('Банкротства'),
    owner: t('Юрист'),
    manual: true,
    result: t(
      'Официальная ручная проверка сообщений ЕФРСБ. Полная автоматическая проверка банкротства в Mandato не реализована.'
    ),
    cost: t(
      'Для автоматизации нужны разрешённый API, условия лицензии и выданный доступ. Платные сервисы здесь не подключаются.'
    ),
    requirements: [
      t('Найти должника по точному ИНН или ОГРН в ЕФРСБ.'),
      t('Проверить публикации и их даты; сохранить ссылки на сообщения.'),
      t(
        'Для автоматизации согласовать источник, лицензию и документацию; потребуется отдельный адаптер.'
      ),
    ],
    fields: [t('ИНН или ОГРН должника'), t('Ссылки на сообщения и дата ручной проверки')],
    acceptance: t(
      'Сверить личность должника и опубликованные сообщения. Регистрационная отметка DaData не заменяет эту проверку.'
    ),
    links: [{ label: t('Открыть ЕФРСБ'), url: 'https://bankrot.fedresurs.ru/' }],
  },
];
const statusLabels: Record<string, string> = {
  unconfigured: t('Доступ не настроен'),
  not_checked: t('Настроено, чтение ещё не проверено'),
  available: t('Доступно'),
  completed: t('Последнее чтение выполнено'),
  partial: t('Прочитана часть данных'),
  no_match: t('Последний поиск без совпадений'),
  stale: t('Результат чтения устарел'),
  unavailable: t('Последнее чтение не удалось'),
};
function statusText(source: Source, status?: ConnectionStatus) {
  if (source.manual) return t('Автоматическое чтение не реализовано');
  if (!status) return t('Статус не получен');
  if (!status.configured) return statusLabels.unconfigured;
  return statusLabels[status.status] ?? t('Настроено; результат чтения требует проверки');
}
function checkedTime(value: string | null | undefined) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' });
}

/** Preparation for the selected source; checklist marks never establish connectivity. */
export function ConnectionAccess({
  selectedSource,
  statuses,
}: {
  selectedSource: 'one_c' | 'diadoc' | 'tbank' | 'dadata';
  statuses: ConnectionStatus[];
}) {
  const [registrySource, setRegistrySource] = useState<SourceId>('dadata');
  const [notice, setNotice] = useState('');
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const source = sources.find(
    (item) => item.id === (selectedSource === 'dadata' ? registrySource : selectedSource)
  )!;
  const status = statuses.find((item) => item.provider === source.id);
  function checklist(item: Source) {
    return item.requirements.map((text, index) => ({
      text,
      prepared: checks[`${item.id}:${index}`] === true,
    }));
  }
  function requestText(item: Source) {
    const current = statuses.find((entry) => entry.provider === item.id);
    return [
      t('Mandato · задание на подключение: {0}', [item.name]),
      t('Ответственный: {0}', [item.owner]),
      t('Состояние по данным Mandato: {0}', [statusText(item, current)]),
      '',
      item.result,
      item.cost,
      '',
      t('Что подготовить:'),
      ...checklist(item).map((step) => `${step.prepared ? '[x]' : '[ ]'} ${step.text}`),
      '',
      t('Состав необходимых сведений (значения и секреты не включены):'),
      ...item.fields.map((field) => `• ${field}`),
      '',
      t('Критерий приёмки:'),
      item.acceptance,
      '',
      t('Официальные материалы:'),
      ...item.links.map((link) => `${link.label}: ${link.url}`),
      '',
      t(
        'Пароли и токены передать администратору по согласованному защищённому каналу. Не включать их в это задание, переписку или репозиторий.'
      ),
      t(
        'Привязать доступ только к нужной организации Mandato. Новые аккаунты, покупки и отправка сообщений этим заданием не разрешаются.'
      ),
      t('Отметки подготовки сделаны вручную и не подтверждают доступ или успешное чтение.'),
    ].join('\n');
  }
  async function copyRequest() {
    setNotice('');
    try {
      await navigator.clipboard.writeText(requestText(source));
      setNotice(t('Задание скопировано.'));
    } catch {
      setNotice(t('Буфер обмена недоступен. Скачайте задание в TXT.'));
    }
  }
  function download(format: 'json' | 'txt') {
    const content =
      format === 'txt'
        ? requestText(source)
        : JSON.stringify(
            {
              schema: 'mandato.connection-access.v1',
              generated_at: new Date().toISOString(),
              contains_credentials: false,
              status_available: statuses.length > 0,
              note: t(
                'Ручные отметки подготовки не подтверждают подключение. configured означает наличие настроек, не успешное чтение.'
              ),
              sources: [source].map((item) => {
                const current = statuses.find((entry) => entry.provider === item.id);
                return {
                  provider: item.id,
                  name: item.name,
                  owner: item.owner,
                  mode: item.manual ? 'manual_only' : 'operator_configured_adapter',
                  configured: item.manual ? false : (current?.configured ?? null),
                  status: statusText(item, current),
                  last_read_at: current?.checked_at ?? null,
                  checklist: checklist(item),
                  required_information: item.fields,
                  scope: item.result,
                  cost: item.cost,
                  acceptance: item.acceptance,
                  official_sources: item.links,
                };
              }),
            },
            null,
            2
          );
    const url = URL.createObjectURL(
      new Blob([content], {
        type: format === 'json' ? 'application/json;charset=utf-8' : 'text/plain;charset=utf-8',
      })
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `mandato-access-${source.id}.${format}`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(t('Задание скачано.'));
  }
  return (
    <section className="connection-access" aria-labelledby="connection-access-title">
      {selectedSource === 'dadata' && (
        <label className="field ca-registry-source">
          {t('Инструкция по источнику')}
          <select
            value={registrySource}
            onChange={(event) => {
              setRegistrySource(event.target.value as SourceId);
              setNotice('');
            }}
          >
            {sources
              .filter((item) => ['dadata', 'court', 'fssp', 'bankruptcy'].includes(item.id))
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </select>
        </label>
      )}
      <div className="ca-provider-heading">
        <h3 id="connection-access-title">{source.name}</h3>
        <span
          className={`ca-status ${!source.manual && status?.configured && ['completed', 'available', 'no_match'].includes(status.status) ? 'ca-configured' : ''}`}
        >
          {statusText(source, status)}
        </span>
      </div>
      <p>{source.result}</p>
      {!source.manual && status?.checked_at && (
        <p className="ca-last-read">
          {t('Последняя попытка чтения:')} {checkedTime(status.checked_at)} {t('МСК')}
        </p>
      )}
      <p className="ca-cost">{source.cost}</p>
      <div className="ca-columns">
        <div>
          <h4>{t('Что подготовить')}</h4>
          <p className="ca-owner">
            {t('Ответственный:')} {source.owner}
          </p>
          <div className="ca-checklist">
            {source.requirements.map((step, index) => (
              <label key={`${source.id}:${index}`}>
                <input
                  type="checkbox"
                  checked={checks[`${source.id}:${index}`] === true}
                  onChange={(event) =>
                    setChecks((value) => ({
                      ...value,
                      [`${source.id}:${index}`]: event.target.checked,
                    }))
                  }
                />
                <span>{step}</span>
              </label>
            ))}
          </div>
          <small className="ca-note">
            {t(
              'Отметки помогают собрать задание, не сохраняются после ухода из раздела и не меняют статус подключения.'
            )}
          </small>
        </div>
        <div className="ca-handoff">
          <h4>
            {source.manual ? t('Сведения для проверки') : t('Состав доступа для администратора')}
          </h4>
          <ul>
            {source.fields.map((field) => (
              <li key={field}>{field}</li>
            ))}
          </ul>
          <p className="ca-secure">
            <ShieldCheck size={18} />{' '}
            {t(
              'Пароли и токены здесь не вводятся. Администратор привязывает их к вашей организации через согласованный защищённый процесс эксплуатации. Самостоятельное сохранение и шифрованное хранилище ключей пока не реализованы.'
            )}
          </p>
        </div>
      </div>
      <div className="ca-acceptance">
        <Check size={18} />
        <p>
          <strong>{t('Как принять подключение.')}</strong> {source.acceptance}
        </p>
      </div>
      <div className="ca-links">
        {source.links.map((link) => (
          <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer">
            {link.label} <ExternalLink size={13} />
          </a>
        ))}
      </div>
      <div className="ca-actions">
        <button type="button" className="button button-dark" onClick={() => void copyRequest()}>
          <Copy size={15} /> {t('Скопировать задание по источнику')}
        </button>
        <button type="button" className="button button-outline" onClick={() => download('txt')}>
          <Download size={15} /> {t('Скачать задание · TXT')}
        </button>
        <button type="button" className="button button-outline" onClick={() => download('json')}>
          <Download size={15} /> {t('Скачать задание · JSON')}
        </button>
      </div>
      <p className="ca-note">
        {t(
          'Наличие настроек не подтверждает успешное чтение. После подключения выполните чтение и сверку выбранного источника. Суды, ФССП и ЕФРСБ пока проверяются вручную.'
        )}
      </p>
      <p className="ca-notice" role="status">
        {notice}
      </p>
    </section>
  );
}
