/**
 * Russian is the source language: every string in code is its own key.
 * `t` is a plain function, so it also works in module-level constants; switching
 * language reloads the page. Legal documents for Russian courts stay in Russian.
 */
export type Language = 'ru' | 'en';

const STORAGE_KEY = 'mandato-language';
let dictionary: Record<string, string> = {};

function stored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function detect(): Language {
  const query = new URLSearchParams(window.location.search).get('lang');
  if (query === 'en' || query === 'ru') return query;
  const saved = stored();
  if (saved === 'en' || saved === 'ru') return saved;
  return 'ru'; // The market is Russian: English is always an explicit choice.
}

export const language: Language = detect();

/** Load translations before any module that calls `t` at import time. */
export async function loadLanguage() {
  document.documentElement.lang = language;
  if (language === 'en') dictionary = (await import('./i18n/en.json')).default;
}

export function t(source: string, values?: (string | number | null | undefined)[]): string {
  const text = dictionary[source] ?? source;
  if (!values) return text;
  return text.replace(/\{(\d+)\}/g, (match, index) => String(values[Number(index)] ?? match));
}

export function setLanguage(next: Language) {
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // The URL below still carries the choice for this visit.
  }
  const url = new URL(window.location.href);
  url.searchParams.set('lang', next);
  window.location.assign(url.toString());
}

export const locale = language === 'en' ? 'en-GB' : 'ru-RU';
