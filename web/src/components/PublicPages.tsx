import { useEffect, type ReactNode } from 'react';
import { ArrowRight } from 'lucide-react';
import { t } from '../i18n';
import './public-pages.css';

export type PublicPageKind = 'product' | 'solutions' | 'integrations';

function Block({
  id,
  title,
  lead,
  items,
}: {
  id?: string;
  title: string;
  lead?: string;
  items: string[];
}) {
  return (
    <section className="page-block" id={id}>
      <div>
        <h2>{title}</h2>
        {lead && <p>{lead}</p>}
      </div>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function Page({ title, lead, children }: { title: string; lead: string; children: ReactNode }) {
  useEffect(() => {
    // Anchors point below the hero; the prerendered page has no scroll position yet.
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  }, []);
  return (
    <div className="page">
      <header className="page-hero">
        <h1>{title}</h1>
        <p>{lead}</p>
        <a className="pill pill-dark" href="/start?plan=trial">
          {t('Попробовать бесплатно')}
          <ArrowRight aria-hidden="true" />
        </a>
      </header>
      {children}
    </div>
  );
}

function Product() {
  return (
    <Page
      title={t('Весь путь долга')}
      lead={t(
        'От просроченного счёта до денег на расчётном счёте: досудебная работа, суд и исполнение в одной системе.'
      )}
    >
      <Block
        id="debtors"
        title={t('Должники')}
        lead={t('Реестр, который сам подсказывает следующий шаг.')}
        items={[
          t('Загрузка из Excel и 1С'),
          t('Этапы, статусы и свой статус'),
          t('Фильтры по сумме, просрочке, контактам, документам и ответственному'),
          t('Действия сразу по списку: письма, документы, пауза, ответственный, архив'),
          t('Проверка должника по ИНН'),
        ]}
      />
      <Block
        id="pretrial"
        title={t('Досудебная работа')}
        lead={t('Письма идут по вашим правилам, ответы разбирает система.')}
        items={[
          t('Расписание, пороги сумм и пауза между письмами'),
          t('Три уровня текста в зависимости от суммы долга'),
          t('Контроль обещаний: нет оплаты в срок — следующий шаг'),
          t('Разбор ответов должника и споров'),
          t('Претензия, расчёт процентов, соглашение о погашении, акт сверки'),
        ]}
      />
      <Block
        id="court"
        title={t('Суд')}
        lead={t('Приказ или иск выбирается по сумме и наличию спора.')}
        items={[
          t('Проценты по ст. 395 ГК РФ с учётом ставок ЦБ и моратория'),
          t('Расчёт госпошлины и реестр на оплату для бухгалтера'),
          t('Заявление о приказе, иск, иск после отмены приказа'),
          t('Ходатайства: уточнение требований, отказ, ускорение, возврат и зачёт пошлины'),
          t('События дела и контроль сроков'),
          t('Распознавание судебных актов и платёжек из PDF'),
        ]}
      />
      <Block
        id="enforcement"
        title={t('Исполнение')}
        lead={t('Лист получен — дальше банк, ФНС или приставы.')}
        items={[
          t('Заявления в банк и ФССП, запрос счетов в ФНС'),
          t('Арест, розыск имущества, повторное предъявление, отзыв листа'),
          t('Жалобы на бездействие и окончание производства'),
          t('Учёт исполнительных производств и счетов должника'),
          t('Намерение о банкротстве при достаточной сумме'),
        ]}
      />
      <Block
        id="analytics"
        title={t('Аналитика и отчёты')}
        lead={t('Первый экран кабинета показывает ситуацию целиком.')}
        items={[
          t('Сумма в работе, просрочка, обещания и поступления'),
          t('Долг по срокам и этапам, динамика за 12 месяцев'),
          t('Что требует внимания сегодня'),
          t('Свой отчёт: выберите колонки и этап'),
          t('Свои панели с плитками и показателями'),
          t('Отчёты на почту по расписанию'),
          t('Несколько организаций в одном кабинете'),
        ]}
      />
    </Page>
  );
}

function Solutions() {
  return (
    <Page
      title={t('Для всей команды')}
      lead={t('Каждый видит свою работу, а данные по долгу общие.')}
    >
      <Block
        title={t('Руководителю')}
        items={[
          t('Картина по деньгам на одном экране'),
          t('Правила работы утверждает один человек'),
          t('Решение о суде и списании остаётся за вами'),
        ]}
      />
      <Block
        title={t('Бухгалтеру')}
        items={[
          t('Сверка выписки со счетами'),
          t('Частичные оплаты закрывают долг автоматически'),
          t('Реестр госпошлин одним файлом'),
        ]}
      />
      <Block
        title={t('Юристу')}
        items={[
          t('Документы и переписка уже в карточке'),
          t('Готовые заявления в редактируемом DOCX'),
          t('Сроки считаются сами'),
          t('Свои шаблоны с переменными'),
        ]}
      />
    </Page>
  );
}

function Integrations() {
  return (
    <Page title={t('Подключения')} lead={t('Работает с тем, что у вас уже есть.')}>
      <Block
        title={t('Данные о долгах')}
        items={[t('Excel и CSV'), t('Выгрузка из 1С'), t('Банковская выписка')]}
      />
      <Block
        title={t('Связь с должником')}
        items={[t('Ваша корпоративная почта'), t('SMS и голосовые звонки подключаются по заявке')]}
      />
      <Block
        title={t('Проверка контрагентов')}
        items={[t('Статус компании, ликвидация и банкротство по ИНН')]}
      />
    </Page>
  );
}

export function PublicPages({ kind }: { kind: PublicPageKind }) {
  if (kind === 'product') return <Product />;
  if (kind === 'solutions') return <Solutions />;
  return <Integrations />;
}
