import { language, setLanguage } from '../i18n';

export function LanguageSwitch() {
  const next = language === 'ru' ? 'en' : 'ru';
  return (
    <button
      type="button"
      className="language-switch"
      lang={next}
      aria-label={next === 'en' ? 'Switch to English' : 'Переключить на русский'}
      onClick={() => setLanguage(next)}
    >
      {next.toUpperCase()}
    </button>
  );
}

/** Interface language as a labelled setting, for the workspace settings page. */
export function LanguageChoice() {
  return (
    <label className="language-choice">
      {language === 'ru' ? 'Язык интерфейса' : 'Interface language'}
      <select value={language} onChange={(event) => setLanguage(event.target.value as 'ru' | 'en')}>
        <option value="ru">Русский</option>
        <option value="en">English</option>
      </select>
    </label>
  );
}
