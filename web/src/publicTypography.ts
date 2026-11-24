import { language, t } from './i18n';

/** Keep short Russian function words with their phrase, without fixed line breaks. */
export function publicText(source: string, values?: (string | number | null | undefined)[]) {
  const text = t(source, values);
  if (language !== 'ru') return text;
  const nbsp = '\u00a0';
  // Compact conjunction phrases stay together; longer phrases can still wrap naturally.
  const connected = text.replace(
    /([А-ЯЁа-яё]+) +(и|а|но|или) +([А-ЯЁа-яё]+)/gu,
    (phrase, before: string, conjunction: string, after: string) =>
      phrase.length <= 26 ? [before, conjunction, after].join(nbsp) : phrase
  );
  return connected.replace(
    /(^|[\s(«])((?:[ВвКкСсУуОо]|[Вв]о|[Нн]а|[Пп]о|[Ии]з|[Зз]а|[Дд]о|[Оо]т|[Нн]е|[Дд]ля|[Пп]ри|[Бб]ез)) +(?=\S)/gu,
    '$1$2' + nbsp
  );
}
