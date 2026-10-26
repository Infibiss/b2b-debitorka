import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, X } from 'lucide-react';
import './workflow.css';

export type LearningSection = 'workflow' | 'audit' | 'connections' | 'management';
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
        Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`)).find(
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
