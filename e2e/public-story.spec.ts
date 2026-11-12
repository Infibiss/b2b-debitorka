import { test, expect } from './fixtures';
test('home explains the stages and is readable without waiting for scripts', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Долги');
  const stages = page.getByRole('region', { name: /Претензии|Суд|Взыскание/ });
  await expect(stages.getByRole('figure')).toContainText('Досудебная работа');
  await stages.getByRole('button', { name: 'Вперёд' }).click();
  await expect(stages.getByRole('figure')).toContainText('Пошлина');
  await expect(page.getByRole('contentinfo')).toContainText('ОГРНИП 326265100166493');
  await expect(page.getByRole('contentinfo')).not.toContainText('18+');
  await expect(page.getByRole('contentinfo')).not.toContainText('Муртазалиев');
});
test('public pages ship real html, meta tags and a sitemap', async ({ request }) => {
  const home = await (await request.get('/')).text();
  expect(home).toContain('<h1 id="hero-title">');
  expect(home).toContain('rel="canonical" href="https://mandato.ru/"');
  expect(home).toContain('application/ld+json');
  const product = await (await request.get('/product')).text();
  expect(product).toContain('Реестр должников'.slice(0, 6));
  expect(product).toContain('rel="canonical" href="https://mandato.ru/product"');
  expect(await (await request.get('/robots.txt')).text()).toContain(
    'Sitemap: https://mandato.ru/sitemap.xml'
  );
  expect(await (await request.get('/sitemap.xml')).text()).toContain(
    '<loc>https://mandato.ru/pricing</loc>'
  );
  expect(await (await request.get('/app')).text()).not.toContain('hero-title');
  expect((await request.get('/nope')).status()).toBe(404);
});
test('subscription comparison adds capabilities with each tier', async ({ page }) => {
  await page.goto('/pricing');
  const table = page.getByRole('table', { name: 'Состав подписки по тарифам' });
  await expect(table.getByRole('row', { name: /Юридические дела/ })).toContainText('—');
  await expect(table.getByRole('row', { name: /Подготовка претензии/ })).toContainText('Включено');
  await expect(table.getByRole('row')).toHaveCount(11);
});
