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
        text: 'Импортируйте счета или добавьте один вручную. Суммы портфеля появятся над делами.',
        target: 'work-import',
      },
      {
        title: 'Откройте дело',
        text: 'Счета одного контрагента по одному договору собраны вместе. В карточке — документы, переписка и следующий шаг.',
        target: 'workflow-board',
      },
      {
        title: 'Разберите исключения',
        text: 'В очереди «Требует решения» — вопросы к бухгалтеру и руководителю. Обычные напоминания агент ведёт по вашим правилам.',
        target: 'workflow-queues',
      },
    ],
  },
  audit: {
    name: 'Аудит',
    steps: [
      {
        title: 'Соберите аудит',
        text: 'Загрузите портфель и запустите проверку. Аудит покажет расхождения, сроки и недостающие документы.',
        target: 'audit-actions',
      },
      {
        title: 'Выберите замечание',
        text: 'Найдите контрагента или отфильтруйте замечания по важности. Откройте строку, чтобы увидеть основание проверки.',
        target: 'audit-findings',
      },
      {
        title: 'Исправьте причину',
        text: 'Из замечания можно открыть счёт, добавить документ или сверить поступление. После изменений обновите аудит.',
        target: 'audit-findings',
      },
    ],
  },
  connections: {
    name: 'Подключения',
    steps: [
      {
        title: 'Выберите источник',
        text: 'Откройте 1С, ЭДО, банк, реестры или почту. У каждого источника свой статус и свои действия.',
        target: 'connections-content',
      },
      {
        title: 'Проверьте доступ',
        text: 'Если доступ ещё не настроен, откройте задание для IT-специалиста внутри выбранного источника.',
        target: 'connections-content',
      },
      {
        title: 'Проверьте полученные данные',
        text: 'Перед сохранением счетов и поступлений просмотрите строки. История загрузок остаётся у соответствующего источника.',
        target: 'connections-content',
      },
    ],
  },
  management: {
    name: 'Управление',
    steps: [
      {
        title: 'Задайте правила',
        text: 'Руководитель выбирает расписание и частоту напоминаний. Автоматизацию можно включить после подключения почты.',
        target: 'workflow-policy',
      },
      {
        title: 'Пригласите бухгалтера',
        text: 'Создайте приглашение для сотрудника. Бухгалтер разбирает документы и поступления, руководитель согласует новые условия.',
        target: 'workflow-team',
      },
      {
        title: 'Запустите нужные дела',
        text: 'Вернитесь в «Работу» и включите агента для выбранного дела. Любое дело можно поставить на паузу.',
        target: 'workflow-policy',
      },
    ],
  },
};
type SectionProgress = { step: number; dismissed: boolean; completed: boolean };
type Progress = {
  enabled: boolean | null;
  sections: Partial<Record<LearningSection, SectionProgress>>;
};
const initialSection: SectionProgress = { step: 0, dismissed: false, completed: false };
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
        const value = stored.sections[section];
        if (value && Number.isInteger(value.step))
          sections[section] = {
            step: Math.max(0, Math.min(lessons[section].steps.length - 1, value.step)),
            dismissed: !!value.dismissed,
            completed: !!value.completed,
          };
      }
      return { enabled: stored.enabled, sections };
    }
    const old = JSON.parse(localStorage.getItem(`mandato-onboarding:${userId}`) || 'null');
    if (old?.dismissed || old?.completed) return { enabled: false, sections: {} };
  } catch {
    /* Learning works when browser storage is unavailable. */
  }
  return { enabled: null, sections: {} };
}
export function WorkflowOnboarding({
  userId,
  section,
  contextKey,
  replayToken,
}: {
  userId: string;
  section: LearningSection;
  contextKey: string;
  replayToken: number;
}) {
  const [progress, setProgress] = useState<Progress>(() => readProgress(userId));
  const [open, setOpen] = useState(false);
  const previousReplay = useRef(replayToken);
  const lesson = lessons[section];
  const current = progress.sections[section] || initialSection;
  const step = lesson.steps[current.step];
  function save(next: Progress) {
    setProgress(next);
    try {
      localStorage.setItem(`mandato-learning:v2:${userId}`, JSON.stringify(next));
    } catch {
      /* Optional persistence. */
    }
  }
  function update(next: Partial<SectionProgress>) {
    save({ ...progress, sections: { ...progress.sections, [section]: { ...current, ...next } } });
  }
  function close() {
    update({ dismissed: true });
    setOpen(false);
  }
  function start() {
    save({
      ...progress,
      enabled: true,
      sections: { ...progress.sections, [section]: { ...current, dismissed: true } },
    });
    setOpen(true);
  }
  useEffect(() => {
    setProgress(readProgress(userId));
    setOpen(false);
  }, [userId]);
  useEffect(() => {
    setOpen(false);
  }, [contextKey]);
  useEffect(() => {
    if (previousReplay.current === replayToken) return;
    previousReplay.current = replayToken;
    setProgress((value) => {
      const next = {
        ...value,
        sections: { ...value.sections, [section]: { step: 0, dismissed: true, completed: false } },
      };
      try {
        localStorage.setItem(`mandato-learning:v2:${userId}`, JSON.stringify(next));
      } catch {
        /* Optional persistence. */
      }
      return next;
    });
    setOpen(true);
  }, [replayToken, section, userId]);
  useEffect(() => {
    if (!open) return;
    let target: HTMLElement | null = null;
    const frame = requestAnimationFrame(() => {
      target = document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`);
      target?.classList.add('wf-tour-highlight');
    });
    return () => {
      cancelAnimationFrame(frame);
      target?.classList.remove('wf-tour-highlight');
    };
  }, [open, step]);
  const offer =
    contextKey === section &&
    !open &&
    (progress.enabled === null || (progress.enabled && !current.dismissed && !current.completed));
  return (
    <>
      {offer && (
        <aside className="wf-learn-prompt" aria-label="Обучение">
          <strong>
            {progress.enabled === null
              ? 'Показать, как устроена работа?'
              : `Показать раздел «${lesson.name}»?`}
          </strong>
          <div className="wf-actions">
            <button className="button button-dark" onClick={start}>
              Начать обучение
              <ArrowRight size={14} />
            </button>
            <button
              className="wf-text-button"
              onClick={() => {
                save({
                  ...progress,
                  enabled: progress.enabled === null ? false : progress.enabled,
                  sections: { ...progress.sections, [section]: { ...current, dismissed: true } },
                });
              }}
            >
              Позже
            </button>
          </div>
        </aside>
      )}
      {open && (
        <aside
          className="wf-coach"
          aria-label={`Обучение: ${lesson.name}`}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.stopPropagation();
              close();
            }
          }}
        >
          <div className="wf-coach-top">
            <span>
              {lesson.name} · {current.step + 1} / {lesson.steps.length}
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
              disabled={current.step === 0}
              onClick={() => update({ step: current.step - 1 })}
            >
              <ArrowLeft size={14} />
              Назад
            </button>
            {current.step < lesson.steps.length - 1 ? (
              <button
                className="button button-dark"
                onClick={() => update({ step: current.step + 1 })}
              >
                Далее
                <ArrowRight size={14} />
              </button>
            ) : (
              <button
                className="button button-dark"
                onClick={() => {
                  update({ dismissed: true, completed: true });
                  setOpen(false);
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
