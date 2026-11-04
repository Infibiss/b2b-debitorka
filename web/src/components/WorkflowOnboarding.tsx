import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, X } from 'lucide-react';
import './workflow.css';

export type LearningSection =
  | 'workflow'
  | 'audit'
  | 'connections'
  | 'management'
  | 'registry'
  | 'finance'
  | 'messages'
  | 'yandex'
  | 'intelligence'
  | 'legal'
  | 'agent'
  | 'settings';
type Step = { title: string; text: string; target: string };
const lessons: Record<LearningSection, { name: string; steps: Step[] }> = {
  workflow: {
    name: 'Работа',
    steps: [
      {
        title: 'Загрузите реестр',
        text: 'Загрузите счета файлом или добавьте один вручную. Mandato соберёт их по контрагентам и договорам.',
        target: 'work-import',
      },
      {
        title: 'Откройте дело',
        text: 'В карточке дела — счета по договору, документы, переписка и следующий шаг.',
        target: 'workflow-case',
      },
      {
        title: 'Разберите исключения',
        text: 'В очереди «Требует решения» — документы, спорные поступления и новые условия. Напоминания идут по утверждённым правилам.',
        target: 'workflow-queues',
      },
    ],
  },
  audit: {
    name: 'Аудит',
    steps: [
      {
        title: 'Соберите аудит',
        text: 'Запустите проверку загруженного портфеля: расхождения, сроки и недостающие документы.',
        target: 'audit-actions',
      },
      {
        title: 'Выберите замечание',
        text: 'Найдите контрагента или выберите важность замечаний. Откройте строку, чтобы увидеть причину.',
        target: 'audit-findings',
      },
      {
        title: 'Исправьте причину',
        text: 'Добавьте документ или сверьте поступление в связанном счёте. Затем обновите аудит.',
        target: 'audit-findings',
      },
    ],
  },
  connections: {
    name: 'Подключения',
    steps: [
      {
        title: 'Выберите источник',
        text: 'Откройте 1С, ЭДО, банк, реестры или почту. Внутри — состояние подключения и доступные действия.',
        target: 'connections-content',
      },
      {
        title: 'Настройте доступ',
        text: 'Для подключения потребуется доступ к вашей системе. Инструкцию для IT-специалиста можно открыть здесь же.',
        target: 'connections-content',
      },
      {
        title: 'Проверьте загрузку',
        text: 'Просмотрите счета и поступления перед сохранением. История загрузок находится внутри источника.',
        target: 'connections-content',
      },
    ],
  },
  management: {
    name: 'Управление',
    steps: [
      {
        title: 'Задайте правила',
        text: 'Выберите расписание и частоту напоминаний. Для их отправки подключите почту.',
        target: 'workflow-policy',
      },
      {
        title: 'Пригласите команду',
        text: 'Бухгалтер разбирает документы и поступления. Руководитель согласует скидки, рассрочки и юридические шаги.',
        target: 'workflow-team',
      },
      {
        title: 'Запустите нужные дела',
        text: 'Включите агента для выбранного дела в «Работе». При необходимости поставьте дело на паузу.',
        target: 'workflow-policy',
      },
    ],
  },
  registry: {
    name: 'Счета',
    steps: [
      {
        title: 'Добавьте счета',
        text: 'Загрузите реестр или добавьте счёт вручную. Проверьте контрагента, договор, сумму и срок оплаты.',
        target: 'css:#workspace-main .page-heading .button',
      },
      {
        title: 'Найдите задолженность',
        text: 'Найдите счёт по номеру, контрагенту или ИНН. Фильтры показывают просрочку, споры и поставленные на паузу счета.',
        target: 'css:#workspace-main .search-input',
      },
      {
        title: 'Откройте счёт',
        text: 'В карточке — остаток, документы, переписка и действия по задолженности.',
        target: 'css:#workspace-main .invoice-number',
      },
    ],
  },
  finance: {
    name: 'Оплаты и сверка',
    steps: [
      {
        title: 'Выберите операцию',
        text: 'Загрузите выписку, разберите поступления или откройте историю выбранного счёта.',
        target: 'css:#workspace-main .ops-tabs',
      },
      {
        title: 'Сопоставьте оплату',
        text: 'Проверьте плательщика, назначение и сумму. Распределите поступление по счетам; неоднозначные операции оставьте на разбор.',
        target: 'css:#workspace-main .ops-card h2',
      },
      {
        title: 'Проверьте остаток',
        text: 'В истории счёта видны оплаты, корректировки и обещанные даты. Возврат или ошибочную оплату оформляйте отдельной операцией.',
        target: 'css:#workspace-main .ops-tabs',
      },
    ],
  },
  messages: {
    name: 'Переписка',
    steps: [
      {
        title: 'Выберите канал',
        text: 'Откройте историю писем или подготовьте звонок. Для отправки и звонков требуется подключение соответствующего канала.',
        target: 'css:#workspace-main .ops-tabs',
      },
      {
        title: 'Откройте историю счёта',
        text: 'Выберите счёт, чтобы увидеть переписку, договорённости и подтверждённые оплаты.',
        target: 'css:#workspace-main .case-conversation select',
      },
      {
        title: 'Разберите ответ',
        text: 'Зафиксируйте входящее сообщение и проверьте предложенный следующий шаг. Если покупатель сообщает об оплате, откройте сверку.',
        target: 'css:#workspace-main .page-heading .button',
      },
    ],
  },
  yandex: {
    name: 'Документы',
    steps: [
      {
        title: 'Выберите работу с документом',
        text: 'В архиве хранятся договоры и подтверждения. Распознавание извлекает текст из скана.',
        target: 'css:#workspace-main .ops-tabs',
      },
      {
        title: 'Привяжите документ к счёту',
        text: 'Выберите счёт, укажите название документа и загрузите файл. Так документ будет доступен из связанного дела.',
        target: 'css:#workspace-main .documents-add select',
      },
      {
        title: 'Проверьте результат',
        text: 'Проверьте распознанные реквизиты и текст перед использованием в требовании или юридическом деле.',
        target: 'css:#workspace-main .documents-archive h2',
      },
    ],
  },
  intelligence: {
    name: 'Прогноз и условия',
    steps: [
      {
        title: 'Оцените поступления',
        text: 'Прогноз помогает увидеть ожидаемые оплаты и качество исходных данных. Обещанные покупателем даты проверяйте отдельно.',
        target: 'css:#workspace-main .ms-tabs',
      },
      {
        title: 'Задайте допустимые условия',
        text: 'Руководитель определяет пределы рассрочки, скидок и отсрочки. Они ограничивают предложения агента.',
        target: 'css:#workspace-main .ms-card h2',
      },
      {
        title: 'Согласуйте предложение',
        text: 'Проверьте сумму, срок и полномочия. Предложение, согласование и исполнение остаются отдельными действиями.',
        target: 'css:#workspace-main .ms-card .button',
      },
    ],
  },
  legal: {
    name: 'Претензии и суд',
    steps: [
      {
        title: 'Откройте юридическое дело',
        text: 'Выберите задолженность. Дело объединяет счета по договору, документы и историю общения.',
        target: 'css:#workspace-main .page-heading h1',
      },
      {
        title: 'Проверьте основания',
        text: 'Заполните факты по договору и должнику, приложите доказательства и проверьте сроки.',
        target: 'css:#workspace-main .legal-tabs',
      },
      {
        title: 'Подготовьте следующий документ',
        text: 'Выполните расчёт, проверьте комплектность и сформируйте документ. Перед отправкой его проверяет ответственный юрист.',
        target: 'css:#workspace-main .legal-tabs',
      },
    ],
  },
  agent: {
    name: 'Разбор ответов',
    steps: [
      {
        title: 'Выберите счёт и ответ',
        text: 'Укажите счёт и добавьте полученное сообщение покупателя.',
        target: 'css:#workspace-main select',
      },
      {
        title: 'Проверьте факты',
        text: 'Сравните извлечённые сумму, дату и условие с исходным ответом. Спорные условия передаются ответственному.',
        target: 'css:#workspace-main textarea',
      },
      {
        title: 'Продолжите работу по делу',
        text: 'Зафиксируйте согласованное действие. Сообщение об оплате направляется на сверку, а не закрывает долг автоматически.',
        target: 'css:#workspace-main .page-heading h1',
      },
    ],
  },
  settings: {
    name: 'Настройки',
    steps: [
      {
        title: 'Укажите реквизиты',
        text: 'Название компании, отправитель и платёжные реквизиты используются при подготовке писем.',
        target: 'css:#workspace-main .settings-panel h2',
      },
      {
        title: 'Подключите почту',
        text: 'Оставьте заявку на подключение и проверьте отправителя. До подключения можно готовить и скачивать письма.',
        target: 'css:#workspace-main .mail-setup h2',
      },
      {
        title: 'Управляйте данными компании',
        text: 'Здесь можно отправить запрос на удаление рабочего пространства. Сначала потребуется подтвердить полномочия и объём удаления.',
        target: 'css:#workspace-data-title',
      },
    ],
  },
};
const orientation: (Step & { section: LearningSection })[] = [
  {
    title: 'Работа — дела и сроки',
    text: 'Ежедневная очередь: кому напомнить, кто обещал оплатить и где нужно ваше решение. Откройте дело, чтобы увидеть всю историю по договору.',
    target: 'nav-workflow',
    section: 'workflow',
  },
  {
    title: 'Аудит — что мешает оплате',
    text: 'Проверяйте расхождения в суммах, недостающие документы и важные сроки. У каждого замечания есть причина и следующий шаг.',
    target: 'nav-audit',
    section: 'audit',
  },
  {
    title: 'Подключения — откуда приходят данные',
    text: 'Здесь подключаются учётная система, банк, ЭДО, реестры и почта. Для начала можно загрузить файлы.',
    target: 'nav-connections',
    section: 'connections',
  },
  {
    title: 'Управление — правила и команда',
    text: 'Задайте правила напоминаний и пригласите коллег. Руководитель решает, что агент может делать самостоятельно.',
    target: 'nav-management',
    section: 'management',
  },
  {
    title: 'Начните с реестра',
    text: 'Загрузите счета в «Работе», затем откройте «Аудит». Подробный урок каждого раздела доступен по кнопке «Помощь по разделу».',
    target: 'work-import',
    section: 'workflow',
  },
];
type LessonProgress = { step: number; dismissed: boolean; completed: boolean };
type Progress = {
  enabled: boolean | null;
  general: LessonProgress;
  sections: Partial<Record<LearningSection, LessonProgress>>;
};
const initialLesson: LessonProgress = { step: 0, dismissed: false, completed: false };
function restoreLesson(value: unknown, count: number): LessonProgress {
  if (
    !value ||
    typeof value !== 'object' ||
    !('step' in value) ||
    typeof value.step !== 'number' ||
    !Number.isInteger(value.step)
  )
    return { ...initialLesson };
  const stored = value as LessonProgress;
  return {
    step: Math.max(0, Math.min(count - 1, stored.step)),
    dismissed: !!stored.dismissed,
    completed: !!stored.completed,
  };
}
function readProgress(userId: string): Progress {
  try {
    const stored = JSON.parse(localStorage.getItem(`mandato-learning:v2:${userId}`) || 'null');
    if (
      stored &&
      [true, false, null].includes(stored.enabled) &&
      typeof stored.sections === 'object' &&
      stored.sections
    ) {
      const sections: Progress['sections'] = {};
      for (const section of Object.keys(lessons) as LearningSection[]) {
        if (stored.sections[section])
          sections[section] = restoreLesson(
            stored.sections[section],
            lessons[section].steps.length
          );
      }
      return {
        enabled: stored.enabled,
        general: restoreLesson(stored.general, orientation.length),
        sections,
      };
    }
    const old = JSON.parse(localStorage.getItem(`mandato-onboarding:${userId}`) || 'null');
    if (old?.dismissed || old?.completed)
      return { enabled: false, general: { ...initialLesson, dismissed: true }, sections: {} };
  } catch {
    /* Learning remains available when browser storage is unavailable. */
  }
  return { enabled: null, general: { ...initialLesson }, sections: {} };
}
function persistProgress(userId: string, progress: Progress) {
  try {
    localStorage.setItem(`mandato-learning:v2:${userId}`, JSON.stringify(progress));
  } catch {
    /* Optional persistence. */
  }
}
export function WorkflowOnboarding({
  userId,
  section,
  contextKey,
  replayToken,
  generalReplayToken = 0,
  onSectionChange,
}: {
  userId: string;
  section: LearningSection;
  contextKey: string;
  replayToken: number;
  generalReplayToken?: number;
  onSectionChange?: (section: LearningSection) => void;
}) {
  const [progress, setProgress] = useState<Progress>(() => readProgress(userId));
  const [mode, setMode] = useState<'general' | 'section' | null>(null);
  const [caseState, setCaseState] = useState<'visible' | 'filtered' | 'empty'>('empty');
  const previousReplay = useRef(replayToken);
  const previousGeneralReplay = useRef(generalReplayToken);
  const navigateSection = useRef(onSectionChange);
  navigateSection.current = onSectionChange;
  const lesson = lessons[section];
  const current = progress.sections[section] || initialLesson;
  const localCaseStep = mode === 'section' && section === 'workflow' && current.step === 1;
  const baseStep =
    mode === 'general' ? orientation[progress.general.step] : lesson.steps[current.step];
  const step =
    localCaseStep && caseState !== 'visible'
      ? caseState === 'filtered'
        ? {
            ...baseStep,
            title: 'Сбросьте фильтр',
            text: 'Поиск или выбранная очередь скрыли дела. Сбросьте фильтры, затем откройте карточку нужного контрагента.',
          }
        : {
            ...baseStep,
            title: 'Добавьте первое дело',
            text: 'Загрузите реестр или добавьте счёт. После загрузки здесь появятся дела по контрагентам и договорам.',
          }
      : baseStep;
  const stepNumber = mode === 'general' ? progress.general.step : current.step;
  const stepCount = mode === 'general' ? orientation.length : lesson.steps.length;
  const lessonName = mode === 'general' ? 'Mandato' : lesson.name;
  function save(update: (value: Progress) => Progress) {
    setProgress((value) => {
      const next = update(value);
      persistProgress(userId, next);
      return next;
    });
  }
  function updateCurrent(next: Partial<LessonProgress>) {
    save((value) =>
      mode === 'general'
        ? { ...value, general: { ...value.general, ...next } }
        : {
            ...value,
            sections: {
              ...value.sections,
              [section]: { ...(value.sections[section] || initialLesson), ...next },
            },
          }
    );
  }
  function close() {
    updateCurrent({ dismissed: true });
    setMode(null);
  }
  function startGeneral() {
    save((value) => ({
      ...value,
      enabled: true,
      general: { step: 0, dismissed: true, completed: false },
    }));
    setMode('general');
  }
  useEffect(() => {
    setProgress(readProgress(userId));
    setMode(null);
  }, [userId]);
  useEffect(() => {
    setMode((value) => (value === 'section' ? null : value));
  }, [contextKey]);
  useEffect(() => {
    if (previousReplay.current === replayToken) return;
    previousReplay.current = replayToken;
    setProgress((value) => {
      const next = {
        ...value,
        enabled: true,
        sections: {
          ...value.sections,
          [section]: { step: 0, dismissed: true, completed: false },
        },
      };
      persistProgress(userId, next);
      return next;
    });
    setMode('section');
  }, [replayToken, section, userId]);
  useEffect(() => {
    if (previousGeneralReplay.current === generalReplayToken) return;
    previousGeneralReplay.current = generalReplayToken;
    setProgress((value) => {
      const next = {
        ...value,
        enabled: true,
        general: { step: 0, dismissed: true, completed: false },
      };
      persistProgress(userId, next);
      return next;
    });
    setMode('general');
  }, [generalReplayToken, userId]);
  useEffect(() => {
    if (mode === 'general') navigateSection.current?.(orientation[progress.general.step].section);
  }, [mode, progress.general.step]);
  useEffect(() => {
    if (!mode) return;
    let target: HTMLElement | null = null;
    let frame = 0;
    let revealFrame = 0;
    function visibleTarget(name: string) {
      return (
        Array.from(
          document.querySelectorAll<HTMLElement>(
            name.startsWith('css:') ? name.slice(4) : `[data-tour="${name}"]`
          )
        ).find(
          (element) =>
            element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden'
        ) || null
      );
    }
    function revealTarget(element: HTMLElement) {
      if (!element.isConnected) return;
      const sidebar = element.closest<HTMLElement>('.sidebar');
      if (sidebar && getComputedStyle(sidebar).position === 'fixed') return;
      const bounds = element.getBoundingClientRect();
      const coach = document.querySelector<HTMLElement>('.wf-coach')?.getBoundingClientRect();
      const viewportHeight = Math.min(
        window.innerHeight,
        window.visualViewport?.height || window.innerHeight
      );
      const gap = 24;
      const sharesCoachColumn =
        !!coach && bounds.right > coach.left - gap && bounds.left < coach.right + gap;
      const overlapsCoach =
        sharesCoachColumn &&
        !!coach &&
        bounds.bottom > coach.top - gap &&
        bounds.top < coach.bottom + gap;
      const outsideViewport = bounds.top < gap || bounds.bottom > viewportHeight - gap;
      if (!overlapsCoach && !outsideViewport) return;
      const freeBottom = sharesCoachColumn && coach ? coach.top - gap : viewportHeight - gap;
      const freeHeight = Math.max(0, freeBottom - gap);
      const desiredTop = gap + Math.max(0, (freeHeight - bounds.height) / 2);
      window.scrollBy({ top: bounds.top - desiredTop, behavior: 'instant' });
    }
    function highlight() {
      const visibleCase = localCaseStep ? visibleTarget('workflow-case') : null;
      const resetFilter = localCaseStep ? visibleTarget('workflow-filter-empty') : null;
      if (localCaseStep) setCaseState(visibleCase ? 'visible' : resetFilter ? 'filtered' : 'empty');
      const next = localCaseStep
        ? visibleCase ||
          resetFilter ||
          visibleTarget('workflow-empty') ||
          visibleTarget('work-import')
        : visibleTarget(baseStep.target);
      if (target !== next) {
        target?.classList.remove('wf-tour-highlight');
        target = next;
        target?.classList.add('wf-tour-highlight');
        cancelAnimationFrame(revealFrame);
        if (next) revealFrame = requestAnimationFrame(() => revealTarget(next));
      }
    }
    function scheduleHighlight() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(highlight);
    }
    scheduleHighlight();
    const observer = new MutationObserver(scheduleHighlight);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      cancelAnimationFrame(revealFrame);
      observer.disconnect();
      target?.classList.remove('wf-tour-highlight');
    };
  }, [mode, baseStep.target, localCaseStep, contextKey]);
  useEffect(() => {
    if (!mode) return;
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape' && !event.defaultPrevented) {
        updateCurrent({ dismissed: true });
        setMode(null);
      }
    }
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  });
  const offer = contextKey === section && !mode && progress.enabled === null;
  return (
    <>
      {offer && (
        <aside className="wf-learn-prompt" aria-label="Обучение">
          <strong>Показать, как устроена работа?</strong>
          <div className="wf-actions">
            <button className="button button-dark" onClick={startGeneral}>
              Начать обучение
              <ArrowRight size={14} />
            </button>
            <button
              className="wf-text-button"
              onClick={() => {
                save((value) => ({
                  ...value,
                  enabled: false,
                  general: { ...value.general, dismissed: true },
                }));
              }}
            >
              Позже
            </button>
          </div>
        </aside>
      )}
      {mode && (
        <aside className="wf-coach" aria-label={`Обучение: ${lessonName}`}>
          <div className="wf-coach-top">
            <span>
              {lessonName} · {stepNumber + 1} / {stepCount}
            </span>
            <button className="icon-button" aria-label="Закрыть обучение" onClick={close}>
              <X size={17} />
            </button>
          </div>
          <div className="wf-coach-content" aria-live="polite">
            <h3>{step.title}</h3>
            <p>{step.text}</p>
          </div>
          <div className="wf-coach-actions">
            <button
              className="wf-text-button"
              disabled={stepNumber === 0}
              onClick={() => updateCurrent({ step: stepNumber - 1 })}
            >
              <ArrowLeft size={14} />
              Назад
            </button>
            {stepNumber < stepCount - 1 ? (
              <button
                className="button button-dark"
                onClick={() => updateCurrent({ step: stepNumber + 1 })}
              >
                Далее
                <ArrowRight size={14} />
              </button>
            ) : (
              <button
                className="button button-dark"
                onClick={() => {
                  updateCurrent({ dismissed: true, completed: true });
                  setMode(null);
                }}
              >
                Готово
              </button>
            )}
          </div>
        </aside>
      )}
    </>
  );
}
