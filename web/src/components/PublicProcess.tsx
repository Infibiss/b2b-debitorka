import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import {
  ArrowDownLeft,
  ArrowRight,
  Check,
  CheckCheck,
  FileCheck2,
  FileText,
  Landmark,
  Mail,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
} from 'lucide-react';
import './public-process.css';

const stages = [
  {
    label: 'Счёт',
    title: 'У долга появляется история',
    text: 'Счёт, клиент и срок оплаты собраны в одном деле. Остаток виден сразу.',
    status: 'Счёт добавлен',
    date: '10 сентября',
    event: 'Счёт № 417 добавлен в дело',
  },
  {
    label: 'Документы',
    title: 'Сначала — причина задержки',
    text: 'В деле не хватает подписанного акта. Ответственный видит, какой документ нужно получить.',
    status: 'Нужен акт',
    date: '11 сентября',
    event: 'Обнаружен недостающий акт',
  },
  {
    label: 'Договорённость',
    title: 'Обещание получает свой срок',
    text: 'Акт приложен, напоминание отправлено. Ответ клиента сохранён, но задолженность ещё открыта.',
    status: 'Обещание оплаты',
    date: '12 сентября',
    event: 'Клиент обещал оплатить 15 сентября',
  },
  {
    label: 'Поступление',
    title: 'Деньги сверяются со счётом',
    text: 'Поступление из банковской выписки сопоставлено со счётом № 417 по сумме и назначению.',
    status: 'Оплата найдена',
    date: '15 сентября',
    event: 'Поступление 180 000 ₽ сопоставлено',
  },
  {
    label: 'Закрытие',
    title: 'Дело закрыто. История на месте',
    text: 'Оплата учтена, остаток равен нулю. Документы и договорённости остаются в истории дела.',
    status: 'Оплачено',
    date: '15 сентября',
    event: 'Остаток обнулён, счёт закрыт',
  },
];

export function PublicProcess() {
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const root = useRef<HTMLElement>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const started = useRef(false);
  const current = stages[step];

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => {
      setReducedMotion(preference.matches);
      if (preference.matches) setPlaying(false);
    };
    update();
    preference.addEventListener('change', update);
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          if (!preference.matches) setPlaying(true);
        } else if (!entry.isIntersecting) setPlaying(false);
      },
      { threshold: 0.35 }
    );
    if (root.current) observer.observe(root.current);
    return () => {
      preference.removeEventListener('change', update);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setTimeout(() => {
      if (step === stages.length - 1) setPlaying(false);
      else setStep(step + 1);
    }, 4600);
    return () => window.clearTimeout(timer);
  }, [playing, step]);

  function select(next: number) {
    setPlaying(false);
    setStep(next);
  }
  function onTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % stages.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + stages.length) % stages.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = stages.length - 1;
    else return;
    event.preventDefault();
    select(next);
    tabs.current[next]?.focus();
  }

  return (
    <section className="public-process" ref={root} aria-label="Как проходит работа со счётом">
      <div className="pp-heading">
        <div>
          <h2>Один счёт. Весь путь до оплаты.</h2>
        </div>
        <button
          className="pp-play"
          onClick={() => {
            if (playing) setPlaying(false);
            else {
              if (step === stages.length - 1) setStep(0);
              setPlaying(true);
            }
          }}
          aria-label={
            playing
              ? 'Приостановить пример'
              : step === stages.length - 1
                ? 'Повторить пример'
                : 'Воспроизвести пример'
          }
        >
          {playing ? (
            <Pause size={16} />
          ) : step === stages.length - 1 ? (
            <RotateCcw size={16} />
          ) : (
            <Play size={16} />
          )}
          <span>{playing ? 'Пауза' : step === stages.length - 1 ? 'Повторить' : 'Смотреть'}</span>
        </button>
      </div>
      <div className="pp-tabs" role="tablist" aria-label="Путь счёта">
        {stages.map((stage, index) => (
          <button
            key={stage.label}
            ref={(el) => {
              tabs.current[index] = el;
            }}
            role="tab"
            id={`pp-tab-${index}`}
            aria-controls="pp-panel"
            aria-selected={step === index}
            tabIndex={step === index ? 0 : -1}
            onClick={() => select(index)}
            onKeyDown={(event) => onTabKey(event, index)}
            className={index < step ? 'is-complete' : ''}
          >
            <span className="pp-tab-number">
              {index < step ? <Check size={14} /> : `0${index + 1}`}
            </span>
            <span>{stage.label}</span>
          </button>
        ))}
      </div>
      <div
        id="pp-panel"
        role="tabpanel"
        aria-labelledby={`pp-tab-${step}`}
        className={`pp-panel pp-stage-${step}`}
      >
        <div className="pp-case-head">
          <span>
            ООО «Северстрой» <span className="pp-case-divider">/</span> Счёт № 417
          </span>
          <span className={`pp-status ${step === 1 ? 'is-attention' : ''}`}>
            {step === 4 && <Check size={14} />}
            {current.status}
          </span>
        </div>
        <div className="pp-workspace">
          <div className="pp-scene" aria-label="Документы и события по счёту">
            <div className="pp-scene-rail" aria-hidden="true">
              <span className={step <= 1 ? 'active' : ''}>
                <FileText size={18} />
              </span>
              <i />
              <span className={step === 2 ? 'active' : ''}>
                <Mail size={18} />
              </span>
              <i />
              <span className={step >= 3 ? 'active' : ''}>
                <Landmark size={18} />
              </span>
            </div>
            <div className="pp-scene-content" key={step}>
              {step <= 1 && (
                <div className="pp-paper">
                  <div className="pp-paper-top">
                    <FileText size={22} />
                    <span>Документы по сделке</span>
                    <span>№ 417</span>
                  </div>
                  <h3>Счёт на оплату</h3>
                  <p>ООО «Северстрой»</p>
                  <strong className="pp-document-amount">
                    180 000 <span>₽</span>
                  </strong>
                  <dl className="pp-paper-details">
                    <div>
                      <dt>Договор</dt>
                      <dd>№ 12 от 01.09</dd>
                    </div>
                    <div>
                      <dt>Оплатить до</dt>
                      <dd>10 сентября</dd>
                    </div>
                  </dl>
                  <div className={`pp-document-check ${step === 1 ? 'needs-document' : ''}`}>
                    {step === 1 ? (
                      <>
                        <span className="pp-missing-icon">!</span>
                        <div>
                          <strong>Нет подписанного акта</strong>
                          <span>Запросить у ответственного</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <FileCheck2 size={20} />
                        <div>
                          <strong>Счёт добавлен</strong>
                          <span>Проверка комплекта документов</span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
              {step === 2 && (
                <div className="pp-correspondence">
                  <div className="pp-attachment">
                    <FileCheck2 size={18} />
                    <span>Акт № 417 подписан</span>
                    <Check size={16} />
                  </div>
                  <div className="pp-message pp-message-out">
                    <span>Напоминание · 12 сентября</span>
                    <p>
                      Документы в порядке. Подскажите, когда ожидать оплату счёта № 417 на 180 000
                      ₽?
                    </p>
                    <CheckCheck size={16} />
                  </div>
                  <div className="pp-message pp-message-in">
                    <span>ООО «Северстрой»</span>
                    <p>
                      Спасибо, акт получили.
                      <br />
                      Оплатим 15 сентября.
                    </p>
                  </div>
                  <div className="pp-promise">
                    <span>Обещание сохранено</span>
                    <strong>
                      15 сентября <ArrowRight size={16} /> 180 000 ₽
                    </strong>
                  </div>
                </div>
              )}
              {step === 3 && (
                <div className="pp-bank">
                  <div className="pp-paper-top">
                    <Landmark size={22} />
                    <span>Банковская выписка</span>
                    <span>15.09</span>
                  </div>
                  <span className="pp-bank-arrow">
                    <ArrowDownLeft size={28} />
                  </span>
                  <h3>Поступление на счёт</h3>
                  <strong className="pp-document-amount">
                    +180 000 <span>₽</span>
                  </strong>
                  <p>ООО «Северстрой»</p>
                  <div className="pp-bank-purpose">
                    <span>Назначение платежа</span>
                    <p>Оплата по счёту № 417, договор № 12</p>
                  </div>
                  <div className="pp-match">
                    <Check size={18} />
                    <span>Совпали сумма и номер счёта</span>
                  </div>
                </div>
              )}
              {step === 4 && (
                <div className="pp-closed">
                  <span className="pp-closed-icon">
                    <ShieldCheck size={38} strokeWidth={1.5} />
                  </span>
                  <span className="pp-closed-label">Счёт № 417 оплачен</span>
                  <strong>
                    0 <span>₽</span>
                  </strong>
                  <p>Осталось к оплате</p>
                  <div className="pp-reconciliation">
                    <div>
                      <span>Сумма счёта</span>
                      <strong>180 000 ₽</strong>
                    </div>
                    <div>
                      <span>Получено</span>
                      <strong>180 000 ₽</strong>
                    </div>
                  </div>
                  <div className="pp-closed-docs">
                    <FileCheck2 size={16} />
                    <span>Документы и переписка сохранены</span>
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="pp-explanation">
            <div className="pp-step-count">
              Шаг {step + 1} из 5 <span>{current.date}</span>
            </div>
            <div className="pp-copy" key={step}>
              <h3>{current.title}</h3>
              <p>{current.text}</p>
            </div>
            <div className="pp-balance">
              <span>Осталось к оплате</span>
              <strong>
                {step === 4 ? '0' : '180 000'} <span>₽</span>
              </strong>
              <span className="pp-balance-note">
                {step === 4
                  ? 'Подтверждено поступлением'
                  : step === 3
                    ? 'До учёта поступления'
                    : 'По счёту № 417'}
              </span>
            </div>
            <div className="pp-event" aria-live={playing ? 'off' : 'polite'}>
              <span className="pp-event-dot" />
              <span>{current.event}</span>
            </div>
          </div>
        </div>
      </div>
      <div className="pp-footer">
        <span>
          {reducedMotion
            ? 'Этапы можно переключать вручную'
            : 'От документов — к подтверждённой оплате'}
        </span>
      </div>
    </section>
  );
}
