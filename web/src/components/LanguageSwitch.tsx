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
