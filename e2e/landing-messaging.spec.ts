import { test, expect } from './fixtures';
test('separate pricing page discloses monthly tiers and additional recovery charges', async ({
  page,
}, info) => {
  await page.goto('/pricing');
  const pricing = page.getByRole('region', { name: 'Тарифы Mandato' });
  await expect(pricing.locator('article')).toHaveCount(4);
  for (const amount of ['9\\s?900', '24\\s?900', '49\\s?900'])
    await expect(pricing).toContainText(new RegExp(amount));
  await expect(page.getByText('Госпошлина оплачивается отдельно', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: '8% от поступлений' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /9\s?900 \/ 14\s?900 ₽/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Адвокату — 12%' })).toBeVisible();
  await page.screenshot({ path: info.outputPath('pricing.png'), fullPage: true });
});
test('home offers a distinct navigation demo and a final free trial action without FAQ', async ({
  page,
}) => {
  await page.goto('/');
  const menu = page.getByRole('button', { name: 'Открыть меню', exact: true });
  const compactNavigation = await menu.isVisible();
  if (compactNavigation) await menu.click();
  const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
  const demo = navigation.getByRole('link', { name: 'Заказать демонстрацию', exact: true });
  await expect(demo).toBeVisible({ timeout: 1500 });
  await expect(demo).toHaveAttribute('href', '/demo');
  await expect(navigation.getByRole('link', { name: 'Войти', exact: true })).toBeVisible();
  expect((await navigation.getByRole('link').allTextContents()).map((text) => text.trim())).toEqual(
    ['Продукт', 'Для вашей команды', 'Подключения', 'Цены', 'Войти', 'Заказать демонстрацию']
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  ).toBeLessThanOrEqual(2);
  if (compactNavigation) await page.getByRole('button', { name: 'Закрыть меню' }).click();
  const finalAction = page.getByRole('region', { name: 'Начните получать оплату вовремя' });
  await expect(finalAction).toBeVisible();
  await expect(finalAction).toContainText('14 дней бесплатно');
  await expect(finalAction).toContainText(/без карты и автоматического продления/i);
  const trial = finalAction.getByRole('link', { name: 'Попробовать бесплатно', exact: true });
  await expect(trial).toHaveAttribute('href', '/start?plan=trial');
  await expect(page.getByRole('heading', { name: 'Вопросы и ответы' })).toHaveCount(0);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  ).toBeLessThanOrEqual(2);
  await trial.click();
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
