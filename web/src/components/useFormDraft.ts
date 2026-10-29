import { useLayoutEffect, useRef, useState } from 'react';
import { useWorkContext } from '../navigation';

type Saved = { values: Record<string, string | boolean>; revision?: string };
const prefix = 'mandato:draft:';
const memory = new Map<string, Saved>();
export function hasFormDrafts() {
  let pending = memory.size > 0;
  try {
    pending ||= Object.keys(sessionStorage).some((key) => key.startsWith(prefix));
  } catch {
    /* Memory remains usable. */
  }
  return pending;
}
window.addEventListener('beforeunload', (event) => {
  if (hasFormDrafts()) {
    event.preventDefault();
    event.returnValue = '';
  }
});
export function clearFormDrafts() {
  memory.clear();
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const key = sessionStorage.key(i);
      if (key?.startsWith(prefix)) sessionStorage.removeItem(key);
    }
  } catch {
    /* Storage may be disabled. */
  }
}
// Controlled forms keep their structured state (including repeatable rows) intact.
export function useStateDraft<T extends object>(identity: string, initial: () => T) {
  const { userId } = useWorkContext();
  const key = `${prefix}${userId}:${identity}`;
  const read = () => {
    try {
      const saved = memory.get(key) || JSON.parse(sessionStorage.getItem(key) || 'null');
      if (saved?.values.state) return JSON.parse(saved.values.state) as T;
    } catch {
      /* Memory or initial state still works. */
    }
    return initial();
  };
  const restoredStatus = () => {
    try {
      return memory.has(key) || sessionStorage.getItem(key)
        ? 'Черновик восстановлен в этой вкладке. Проверьте актуальные полномочия перед сохранением.'
        : '';
    } catch {
      return memory.has(key)
        ? 'Черновик восстановлен из памяти. Сохраните его до обновления страницы.'
        : '';
    }
  };
  const [entry, setEntry] = useState(() => ({ key, value: read(), status: restoredStatus() }));
  const current = entry.key === key ? entry : { key, value: read(), status: restoredStatus() };
  const update = (patch: Partial<T>) => {
    const value = { ...read(), ...patch };
    const saved = { values: { state: JSON.stringify(value) } };
    memory.set(key, saved);
    let status = 'Черновик сохранён в этой вкладке. На сервер ещё не сохранён.';
    try {
      sessionStorage.setItem(key, JSON.stringify(saved));
    } catch {
      status = 'Хранилище браузера недоступно. Сохраните предложение до обновления страницы.';
    }
    setEntry({ key, value, status });
  };
  const clear = () => {
    memory.delete(key);
    try {
      sessionStorage.removeItem(key);
    } catch {
      /* Memory cleared. */
    }
    setEntry({ key, value: initial(), status: '' });
  };
  return { value: current.value, status: current.status, update, clear };
}
export function useFormDraft(identity: string, revision?: string) {
  const { userId } = useWorkContext();
  const ref = useRef<HTMLFormElement>(null);
  const [status, setStatus] = useState('');
  const key = `${prefix}${userId}:${identity}`;
  useLayoutEffect(() => {
    const form = ref.current;
    if (!form || !userId || !identity) return;
    let saved = memory.get(key);
    try {
      saved ??= JSON.parse(sessionStorage.getItem(key) || 'null') as Saved | undefined;
    } catch {
      /* Memory fallback. */
    }
    const pending = { ...saved?.values };
    const restore = () => {
      for (const [name, value] of Object.entries(pending)) {
        const el = form.elements.namedItem(name);
        if (!el) continue;
        if (el instanceof HTMLInputElement && el.type === 'checkbox') el.checked = Boolean(value);
        else if (
          el instanceof HTMLInputElement ||
          el instanceof HTMLSelectElement ||
          el instanceof HTMLTextAreaElement
        ) {
          if (el instanceof HTMLInputElement && ['file', 'password'].includes(el.type)) continue;
          el.value = String(value);
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        delete pending[name];
      }
    };
    // Conditional fields (for example an entrepreneur's birth details) mount
    // after their restored select value updates React state.
    const observer = new MutationObserver(restore);
    observer.observe(form, { childList: true, subtree: true });
    if (saved) {
      restore();
      setStatus(
        saved.revision !== revision
          ? 'Восстановлен черновик. Данные на сервере изменились — проверьте их перед сохранением.'
          : 'Черновик восстановлен в этой вкладке. На сервер ещё не сохранён.'
      );
    }
    const capture = () => {
      const values: Saved['values'] = {};
      let hasFile = false;
      for (const el of Array.from(form.elements)) {
        if (
          !(
            el instanceof HTMLInputElement ||
            el instanceof HTMLTextAreaElement ||
            el instanceof HTMLSelectElement
          ) ||
          !el.name
        )
          continue;
        if (el instanceof HTMLInputElement && el.type === 'password') continue;
        if (el instanceof HTMLInputElement && el.type === 'file') {
          hasFile ||= Boolean(el.files?.length);
          continue;
        }
        values[el.name] =
          el instanceof HTMLInputElement && el.type === 'checkbox' ? el.checked : el.value;
      }
      const data = { values, revision };
      memory.set(key, data);
      try {
        sessionStorage.setItem(key, JSON.stringify(data));
        setStatus(
          hasFile
            ? 'Текст сохранён в черновике. Файл нужно отправить до ухода из формы.'
            : 'Черновик сохранён в этой вкладке. На сервер ещё не сохранён.'
        );
      } catch {
        setStatus(
          'Есть несохранённые изменения. Хранилище браузера недоступно — сохраните форму до обновления страницы.'
        );
      }
    };
    form.addEventListener('input', capture);
    form.addEventListener('change', capture);
    const warn = (event: BeforeUnloadEvent) => {
      if (memory.has(key)) {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', warn);
    return () => {
      observer.disconnect();
      form.removeEventListener('input', capture);
      form.removeEventListener('change', capture);
      window.removeEventListener('beforeunload', warn);
    };
  }, [key, userId, identity, revision]);
  const clear = () => {
    if (!identity) return;
    memory.delete(key);
    try {
      sessionStorage.removeItem(key);
    } catch {
      /* Storage may be disabled. */
    }
    setStatus('Изменения сохранены на сервере.');
  };
  const discard = () => {
    if (!window.confirm('Отменить изменения в этой форме и вернуться к сохранённым данным?'))
      return;
    ref.current?.reset();
    ref.current
      ?.querySelectorAll('select')
      .forEach((el) => el.dispatchEvent(new Event('change', { bubbles: true })));
    clear();
    setStatus('Черновик удалён. Показаны сохранённые данные.');
  };
  return { ref, status, clear, discard };
}
