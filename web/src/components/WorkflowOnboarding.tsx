import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Bot,
  CircleCheck,
  FileCheck2,
  Files,
  PlugZap,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { Dialog } from './Dialog';
import './workflow.css';

type Progress = { dismissed: boolean; completed: boolean; step: number };
const initial: Progress = { dismissed: false, completed: false, step: 0 };
const steps = [
  {
    title: 'Mandato ведёт работу, вы управляете решениями',
    description:
      'Здесь видны дела, которым нужно ваше внимание, работа агента и подтверждённые результаты. Начните с реестра — все действия останутся в одном пространстве.',
    icon: Bot,
    tab: 'workflow',
    target: 'workflow',
    points: [
      'Загрузите свои счета или подключите источник',
      'Проверьте документы, контакты и договоры',
      'Запускайте работу по утверждённым правилам',
    ],
  },
  {
    title: 'Дела вместо разрозненных счетов',
    description:
      'Дело объединяет контрагента и договор. Откройте карточку, чтобы увидеть счета, документы, переписку и следующий шаг. Если договор неизвестен, Mandato попросит его уточнить.',
    icon: Files,
    tab: 'workflow',
    target: 'workflow-board',
    points: [
      'Доска и таблица показывают одни и те же дела',
      'Требующие решения вопросы всегда на виду',
      'Закрытие долга подтверждается финансовым реестром',
    ],
  },
  {
    title: 'Проверьте основания и поступления',
    description:
      'Аудит помогает найти пробелы в документах и расхождения. Поступления проверяются и распределяются по счетам: обещание оплаты само по себе не уменьшает долг.',
    icon: FileCheck2,
    tab: 'audit',
    target: 'audit',
    points: [
      'Проверьте качество исходного реестра',
      'Добавьте документы и условия оплаты',
      'Неоднозначные данные требуют вашего решения',
    ],
  },
  {
    title: 'Подключите рабочие источники',
    description:
      'В подключениях собраны доступные каналы и учётные системы. Подключение показывает состояние доступа и результаты синхронизации. Настраивайте только нужные вашей команде источники.',
    icon: PlugZap,
    tab: 'connections',
    target: 'connections',
    points: [
      'Проверьте доступ к источнику',
      'Просмотрите данные перед принятием',
      'Возвращайтесь к истории синхронизаций',
    ],
  },
  {
    title: 'Установите правила и пригласите команду',
    description:
      'Руководитель включает автоматические напоминания, задаёт расписание и приглашает бухгалтера. После этого можно запускать отдельные дела. Исключения остаются под вашим контролем.',
    icon: ShieldCheck,
    tab: 'management',
    target: 'workflow-policy',
    points: [
      'Автоматизация изначально выключена',
      'Скидки и рассрочки согласует руководитель',
      'Обучение можно повторить в любой момент',
    ],
  },
];
function readProgress(userId: string): Progress {
  try {
    const stored = JSON.parse(localStorage.getItem(`mandato-onboarding:${userId}`) || 'null');
    if (stored && Number.isInteger(stored.step))
      return {
        dismissed: !!stored.dismissed,
        completed: !!stored.completed,
        step: Math.max(0, Math.min(steps.length - 1, stored.step)),
      };
  } catch {
    /* Storage may be unavailable. */
  }
  return initial;
}
export function WorkflowOnboarding({
  userId,
  replayToken,
  onNavigate,
}: {
  userId: string;
  replayToken: number;
  onNavigate: (tab: string) => void;
}) {
  const [progress, setProgress] = useState<Progress>(() => readProgress(userId));
  const [open, setOpen] = useState(false);
  const previousReplay = useRef(replayToken);
  const navigate = useRef(onNavigate);
  navigate.current = onNavigate;
  const current = steps[progress.step];
  function save(next: Progress) {
    setProgress(next);
    try {
      localStorage.setItem(`mandato-onboarding:${userId}`, JSON.stringify(next));
    } catch {
      /* Learning remains available when storage is blocked. */
    }
  }
  useEffect(() => {
    setProgress(readProgress(userId));
    setOpen(false);
  }, [userId]);
  useEffect(() => {
    if (previousReplay.current !== replayToken) {
      previousReplay.current = replayToken;
      save({ dismissed: true, completed: false, step: 0 });
      setOpen(true);
    }
  }, [replayToken]);
  useEffect(() => {
    if (!open) return;
    navigate.current(current.tab);
    const frame = requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>(`[data-tour="${current.target}"]`);
      target?.classList.add('wf-tour-highlight');
    });
    return () => {
      cancelAnimationFrame(frame);
      document
        .querySelectorAll('.wf-tour-highlight')
        .forEach((element) => element.classList.remove('wf-tour-highlight'));
    };
  }, [open, current]);
  function close() {
    save({ ...progress, dismissed: true });
    setOpen(false);
  }
  function finish() {
    save({ ...progress, dismissed: true, completed: true });
    setOpen(false);
    navigate.current('workflow');
  }
  const Icon = current.icon;
  return (
    <>
      {!progress.dismissed && !progress.completed && !open && (
        <aside className="wf-learn-prompt" aria-label="Обучение">
          <div className="wf-learn-prompt-icon">
            <Sparkles size={20} />
          </div>
          <div>
            <strong>Показать, как устроена работа?</strong>
            <p>Короткий маршрут по делам, источникам и правилам Mandato.</p>
          </div>
          <div className="wf-actions">
            <button
              className="button button-dark"
              onClick={() => {
                save({ ...progress, dismissed: true });
                setOpen(true);
              }}
            >
              Начать обучение
              <ArrowRight size={14} />
            </button>
            <button className="wf-text-button" onClick={close}>
              Позже
            </button>
          </div>
        </aside>
      )}
      {progress.dismissed && !progress.completed && progress.step > 0 && !open && (
        <div className="wf-resume-tour">
          <button className="wf-text-button" onClick={() => setOpen(true)}>
            <Sparkles size={13} />
            Продолжить обучение · шаг {progress.step + 1} из {steps.length}
          </button>
        </div>
      )}
      {open && (
        <Dialog title="Знакомство с Mandato" onClose={close}>
          <div className="wf-tour">
            <div
              className="wf-tour-progress"
              aria-label={`Шаг ${progress.step + 1} из ${steps.length}`}
            >
              {steps.map((step, index) => (
                <span key={step.title} className={index <= progress.step ? 'complete' : ''} />
              ))}
            </div>
            <span className="wf-tour-step">
              ШАГ {progress.step + 1} ИЗ {steps.length}
            </span>
            <div className="wf-tour-illustration">
              <span className="wf-tour-orbit" />
              <span className="wf-tour-icon">
                <Icon size={35} />
              </span>
              <span className="wf-tour-check">
                <CircleCheck size={21} />
              </span>
            </div>
            <h3>{current.title}</h3>
            <p>{current.description}</p>
            <ul>
              {current.points.map((point) => (
                <li key={point}>
                  <CircleCheck size={14} />
                  {point}
                </li>
              ))}
            </ul>
            <div className="wf-tour-footer">
              <button className="wf-text-button" onClick={finish}>
                Завершить обучение
              </button>
              {progress.step < steps.length - 1 ? (
                <button
                  className="button button-dark"
                  onClick={() => save({ ...progress, step: progress.step + 1 })}
                >
                  Далее
                  <ArrowRight size={15} />
                </button>
              ) : (
                <button className="button button-dark" onClick={finish}>
                  К работе
                  <ArrowRight size={15} />
                </button>
              )}
            </div>
            <small className="wf-tour-note">Если закроете окно, сохранится текущий шаг.</small>
          </div>
        </Dialog>
      )}
    </>
  );
}
