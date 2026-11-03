import { test, expect } from './fixtures';
test('separate pricing page discloses monthly tiers and additional recovery charges', async ({
  page,
}, info) => {
  await page.goto('/pricing');
  const pricing = page.getByRole('region', { name: 'Тарифы Mandato' });
  await expect(pricing.locator('article')).toHaveCount(4);
  for (const amount of ['9\\s?900', '19\\s?900', '39\\s?900'])
    await expect(pricing).toContainText(new RegExp(amount));
  await expect(page.getByText('Госпошлина оплачивается отдельно', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: '6% от поступлений' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '7 000 / 12 000 ₽' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Адвокату — 12%' })).toBeVisible();
  await page.screenshot({ path: info.outputPath('pricing.png'), fullPage: true });
});
test('home focuses on product and links to trial and demonstration without FAQ', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('link', { name: 'Заказать демонстрацию', exact: true })).toHaveCount(
    1
  );
  await expect(page.getByRole('link', { name: 'Попробовать бесплатно', exact: true })).toHaveCount(
    1
  );
  await expect(page.getByRole('heading', { name: 'Вопросы и ответы' })).toHaveCount(0);
  await page.getByRole('link', { name: 'Попробовать бесплатно', exact: true }).click();
  await expect(page).toHaveURL(/\/start\?plan=trial/);
  await expect(page.getByLabel('Компания', { exact: true })).toBeVisible();
});
test('public routes have readable content without horizontal overflow', async ({ page }) => {
  for (const path of [
    '/',
    '/pricing',
    '/product',
    '/solutions',
    '/integrations',
    '/security',
    '/demo',
    '/privacy',
    '/terms',
    '/refunds',
    '/cookies',
    '/company',
    '/data-request',
  ]) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
      path
    ).toBeLessThanOrEqual(2);
  }
});

test('unknown public routes return a real 404 and let the visitor return home', async ({
  page,
}) => {
  const response = await page.goto('/missing-public-page');
  expect(response?.status()).toBe(404);
  await expect(page.getByRole('heading', { name: 'Страница не найдена' })).toBeVisible();
  await page.getByRole('link', { name: 'Вернуться на главную', exact: true }).click();
  await expect(page).toHaveURL('/');
});
