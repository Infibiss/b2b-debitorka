import { useEffect, useRef, useState } from 'react';
import { ChevronUp, LogOut, Settings } from 'lucide-react';

export function WorkspaceProfile({
  name,
  company,
  role,
  onSettings,
  onLogout,
}: {
  name: string;
  company: string;
  role: string;
  onSettings: () => void;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', key);
    };
  }, [open]);
  return (
    <div
      className="user-block profile-root"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      {open && (
        <div
          className="profile-menu"
          role="menu"
          aria-label="Меню профиля"
          ref={menu}
          onKeyDown={(event) => {
            const buttons = Array.from(
              menu.current?.querySelectorAll<HTMLButtonElement>('button') || []
            );
            const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
            if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
              event.preventDefault();
              const next =
                event.key === 'Home'
                  ? 0
                  : event.key === 'End'
                    ? buttons.length - 1
                    : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) %
                      buttons.length;
              buttons[next]?.focus();
            }
          }}
        >
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onSettings();
              trigger.current?.focus();
            }}
          >
            <Settings size={16} />
            Настройки
          </button>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            <LogOut size={16} />
            Выйти
          </button>
        </div>
      )}
      <button
        className="profile-trigger"
        ref={trigger}
        aria-label="Профиль и настройки"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="user-avatar" aria-hidden="true">
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span className="profile-identity">
          <strong title={company}>{company}</strong>
          <span title={`${name} · ${role}`}>
            {name} · {role}
          </span>
        </span>
        <ChevronUp size={14} aria-hidden="true" />
      </button>
    </div>
  );
}

export function WorkspaceAdvice({ userId, onRules }: { userId: string; onRules: () => void }) {
  const key = `mandato-rules-advice:${userId}`;
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(key) === 'hidden';
    } catch {
      return false;
    }
  });
  if (hidden) return null;
  return (
    <div className="sidebar-help">
      <button
        className="advice-dismiss"
        aria-label="Скрыть подсказку о правилах"
        onClick={() => {
          setHidden(true);
          try {
            localStorage.setItem(key, 'hidden');
          } catch {
            /* Optional preference. */
          }
        }}
      >
        ×
      </button>
      <strong>Всё под вашим контролем</strong>
      <p>Mandato работает по вашим правилам. Исключения — на согласование.</p>
      <button onClick={onRules}>Правила работы →</button>
    </div>
  );
}
