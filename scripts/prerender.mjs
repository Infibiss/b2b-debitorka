// Writes real HTML for public pages so search engines and first paint do not wait for JavaScript.
import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'web/dist');
const site = 'https://mandato.ru';
const lastmod = new Date().toISOString().slice(0, 10);

const pages = {
  '/': ['Mandato — автоматизация взыскания дебиторской задолженности', 'Досудебная работа, суд и исполнение в одной системе. Напоминания, претензии, расчёт процентов и пошлины, заявления в суд и приставам. 14 дней бесплатно.', 1],
  '/product': ['Возможности — взыскание дебиторки от напоминания до приставов | Mandato', 'Реестр должников, напоминания и претензии, судебные заявления, исполнительное производство, аналитика и отчёты.', 0.9],
  '/solutions': ['Для руководителя, бухгалтера и юриста | Mandato', 'Как Mandato распределяет работу с просроченной дебиторкой между руководителем, бухгалтерией и юристом.', 0.7],
  '/integrations': ['Подключения: Excel, 1С, банк, почта | Mandato', 'Загрузка долгов из Excel и 1С, банковская выписка, корпоративная почта и проверка контрагентов по ИНН.', 0.7],
  '/pricing': ['Цены и тарифы | Mandato', 'Тарифы на автоматизацию взыскания дебиторской задолженности. 14 дней бесплатно, без привязки карты.', 0.9],
  '/security': ['Безопасность и хранение данных | Mandato', 'Как Mandato защищает данные о долгах и контрагентах: доступы, журналирование и хранение в России.', 0.5],
  '/demo': ['Заказать демонстрацию | Mandato', 'Покажем, как Mandato будет работать на вашем реестре должников.', 0.8],
  '/company': ['О компании | Mandato', 'Сведения о владельце сервиса Mandato.', 0.3],
  '/privacy': ['Политика конфиденциальности | Mandato', 'Как Mandato обрабатывает персональные данные.', 0.3],
  '/consent': ['Согласие на обработку персональных данных | Mandato', 'Текст согласия на обработку персональных данных.', 0.3],
  '/terms': ['Условия использования | Mandato', 'Условия использования сервиса Mandato.', 0.3],
  '/refunds': ['Возврат средств | Mandato', 'Условия возврата средств за подписку Mandato.', 0.3],
  '/cookies': ['Файлы cookie | Mandato', 'Какие файлы cookie использует сайт Mandato.', 0.3],
  '/data-request': ['Запрос по персональным данным | Mandato', 'Как отправить запрос о своих персональных данных.', 0.2],
};

const escape = (value) => value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const organization = JSON.stringify({
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'Mandato',
  url: site,
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  inLanguage: 'ru',
  description: pages['/'][1],
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'RUB', description: '14 дней бесплатно' },
});

const memory = new Map();
const location = { pathname: '/', search: '', hash: '', href: site + '/', origin: site };
const storage = { getItem: (key) => memory.get(key) ?? null, setItem: () => {}, removeItem: () => {} };
Object.assign(globalThis, {
  location,
  localStorage: storage,
  sessionStorage: storage,
  document: { documentElement: { classList: { add() {}, remove() {}, toggle() {} } }, title: '' },
});
globalThis.window = globalThis;
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

const { render } = await import(pathToFileURL(join(root, 'web/dist-ssr/prerender.js')).href);
const shell = readFileSync(join(dist, 'index.html'), 'utf8');
rmSync(join(dist, '_pages'), { recursive: true, force: true });

// The public chunk is imported dynamically; linking it here styles the page before scripts run.
const assets = readdirSync(join(dist, 'assets'));
const find = (pattern) => assets.find((name) => pattern.test(name));
const assetLinks = [
  `<link rel="stylesheet" href="/assets/${find(/^PublicSite-.*\.css$/)}" />`,
  `<link rel="modulepreload" href="/assets/${find(/^PublicSite-.*\.js$/)}" />`,
  `<link rel="preload" as="font" type="font/woff2" crossorigin href="/assets/${find(/^onest-cyrillic-wght-normal.*\.woff2$/)}" />`,
].join('');

for (const [path, [title, description]] of Object.entries(pages)) {
  location.pathname = path;
  location.href = site + path;
  const url = site + (path === '/' ? '/' : path);
  const head = [
    `<title>${escape(title)}</title>`,
    assetLinks,
    `<meta name="description" content="${escape(description)}" />`,
    `<link rel="canonical" href="${url}" />`,
    `<meta property="og:title" content="${escape(title)}" />`,
    `<meta property="og:description" content="${escape(description)}" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:locale" content="ru_RU" />`,
    `<meta property="og:site_name" content="Mandato" />`,
    `<meta property="og:image" content="${site}/og.png" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    path === '/' ? `<script type="application/ld+json">${organization}</script>` : '',
    path === '/' ? '<link rel="preload" as="image" href="/hero.webp" fetchpriority="high" />' : '',
  ].join('');
  let html = shell.replace(/<title>[\s\S]*?<\/title>/, '').replace(/<meta name="description"[\s\S]*?\/>/, '').replace('</head>', head + '</head>');
  html = html.replace('<div id="root"></div>', `<div id="root">${render()}</div>`);
  if (path === '/') html = html.replace('<html lang="ru">', '<html lang="ru" class="landing-page">');
  const target = join(dist, '_pages', path === '/' ? '' : path.slice(1));
  mkdirSync(target, { recursive: true });
  writeFileSync(join(target, 'index.html'), html);
}

const urls = Object.entries(pages)
  .map(([path, value]) => `<url><loc>${site}${path === '/' ? '/' : path}</loc><lastmod>${lastmod}</lastmod><priority>${value[2]}</priority></url>`)
  .join('');
writeFileSync(join(dist, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`);
rmSync(join(root, 'web/dist-ssr'), { recursive: true, force: true });
console.log(`prerendered ${Object.keys(pages).length} pages`);
