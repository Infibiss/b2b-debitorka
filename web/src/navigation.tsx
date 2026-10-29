import { createContext, useContext, useSyncExternalStore } from 'react';

const subscribe = (callback: () => void) => {
  window.addEventListener('popstate', callback);
  window.addEventListener('mandato:navigate', callback);
  return () => {
    window.removeEventListener('popstate', callback);
    window.removeEventListener('mandato:navigate', callback);
  };
};
export function navigate(values: Record<string, string | null>, replace = false) {
  const url = new URL(location.href);
  if ('case' in values && values.case !== url.searchParams.get('case') && !('caseTab' in values))
    values = { ...values, caseTab: null };
  if (
    'context' in values &&
    values.context !== url.searchParams.get('context') &&
    !('legal' in values)
  ) {
    values = {
      ...values,
      legal: null,
      legalTab: null,
      factsStep: null,
      ...(!('party' in values) ? { party: null } : {}),
      ...(!('agentProposal' in values) ? { agentProposal: null } : {}),
      ...(!('proposal' in values) ? { proposal: null } : {}),
      ...(!('sourceAgent' in values) ? { sourceAgent: null } : {}),
    };
  }
  if (
    'context' in values &&
    values.context !== url.searchParams.get('context') &&
    !('case' in values)
  )
    values = { ...values, case: null, caseTab: null };
  for (const [key, value] of Object.entries(values)) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  if (url.href === location.href) return;
  const filePending = Array.from(
    document.querySelectorAll<HTMLInputElement>('form input[type=file]')
  ).some((input) => input.files?.length);
  if (
    filePending &&
    !window.confirm(
      'Файл ещё не отправлен. После перехода его нужно будет выбрать заново. Перейти?'
    )
  )
    return;
  history[replace ? 'replaceState' : 'pushState']({}, '', url);
  window.dispatchEvent(new Event('mandato:navigate'));
}
export function useRouteField<T extends string | null>(name: string, fallback: T) {
  const search = useSyncExternalStore(subscribe, () => location.search);
  const value = (new URLSearchParams(search).get(name) || fallback) as T;
  return [value, (next: T) => navigate({ [name]: next })] as const;
}
export const WorkContext = createContext({ userId: '', invoiceId: '', caseId: '' });
export const useWorkContext = () => useContext(WorkContext);
