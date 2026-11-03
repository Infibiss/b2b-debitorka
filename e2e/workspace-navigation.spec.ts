import { test, expect } from './fixtures';

async function showOperations(page: import('@playwright/test').Page) {
  await expect(page.getByRole('navigation', { name: 'Разделы кабинета' })).toBeVisible();
  const toggle = page.getByRole('button', { name: /^Операции ·/ });
  if ((await toggle.isVisible()) && (await toggle.getAttribute('aria-expanded')) === 'false')
    await toggle.click();
}

test('operations remain visible, profile contains company and settings, advice can be dismissed', async ({
  page,
}, info) => {
  const result = await page.request.post('/api/auth/register', {
    data: {
      name: 'Анна Юрист',
      company: 'Компания Север',
      email: `navigation-${info.project.name}-${Date.now()}@example.ru`,
      password: 'Mandato-Navigation-2026!',
    },
  });
  expect(result.status()).toBe(201);
  await page.goto('/app');
  await expect(page.locator('.workspace-header')).not.toContainText('РАБОЧЕЕ ПРОСТРАНСТВО');
  await expect(page.locator('.workspace-header > .workspace-section-help')).toBeVisible();
  await expect(page.locator('.workspace-footer')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Проверить реестр', exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Разобрать поступления', exact: true })
  ).toHaveCount(0);
  const operations = page.getByRole('navigation', { name: 'Операции с дебиторкой' });
  await showOperations(page);
  await expect(operations).toBeVisible();
  for (const name of [
    'Счета',
    'Оплаты и сверка',
    'Переписка',
    'Документы',
    'Прогноз и условия',
    'Претензии и суд',
  ])
    await expect(operations.getByRole('button', { name, exact: true })).toBeVisible();
  await expect(operations.getByRole('button')).toHaveCount(6);
  for (const section of ['Аудит', 'Подключения', 'Управление', 'Работа']) {
    await page.getByRole('button', { name: section, exact: true }).click();
    await showOperations(page);
    await expect(operations.getByRole('button')).toHaveCount(6);
    await expect(operations.getByRole('button', { name: 'Документы', exact: true })).toBeVisible();
  }
  await operations.getByRole('button', { name: 'Переписка', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Разобрать ответ', exact: true })).toBeVisible();
  await showOperations(page);
  await expect(operations).toBeVisible();
  await page.getByRole('button', { name: 'Разобрать ответ', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Разбор ответов', exact: true })).toBeVisible();
  const profile = page.getByRole('button', { name: 'Профиль и настройки' });
  await expect(profile).toContainText('Компания Север');
  await profile.click();
  await page.getByRole('menuitem', { name: 'Настройки', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Настройки', exact: true })).toBeVisible();
  const settingsWidth = await page.locator('.settings-form').boundingBox();
  const panelWidth = await page.locator('.settings-panel').first().boundingBox();
  expect(Math.abs(settingsWidth!.width - panelWidth!.width)).toBeLessThanOrEqual(2);
  await expect(page.locator('.mail-setup-badge')).toHaveText('Не подключена');
  await expect(page.locator('.mail-setup-badge')).toHaveClass(/is-warning/);
  await expect(page.locator('.mail-setup details')).toHaveCount(0);
  await profile.click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(profile).toBeFocused();
  await profile.press('Enter');
  await expect(page.getByRole('menuitem', { name: 'Настройки', exact: true })).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('menuitem', { name: 'Выйти', exact: true })).toBeFocused();
  await page.keyboard.press('Home');
  await expect(page.getByRole('menuitem', { name: 'Настройки', exact: true })).toBeFocused();
  await page.keyboard.press('End');
  await expect(page.getByRole('menuitem', { name: 'Выйти', exact: true })).toBeFocused();
  await page.getByRole('heading', { name: 'Настройки', exact: true }).click();
  await expect(page.getByRole('menu')).toHaveCount(0);
  await profile.press('Space');
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('menu')).toHaveCount(0);
  if (info.project.name === 'desktop') {
    await page.getByRole('button', { name: 'Скрыть подсказку о правилах' }).click();
    await expect(page.getByText('Всё под вашим контролем', { exact: true })).toHaveCount(0);
    await page.reload();
    await expect(page.getByText('Всё под вашим контролем', { exact: true })).toHaveCount(0);
  }
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  ).toBeLessThanOrEqual(2);
});

test('landing and workspace remain usable at narrow and intermediate widths', async ({
  page,
}, info) => {
  if (info.project.name !== 'desktop') return;
  const response = await page.request.post('/api/auth/register', {
    data: {
      name: 'Анна',
      company: 'ООО Компания с длинным названием для проверки',
      email: `responsive-${Date.now()}@example.ru`,
      password: 'Mandato-Responsive-2026!',
    },
  });
  expect(response.status()).toBe(201);
  for (const width of [320, 650, 768, 1024, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    const final = page.getByRole('region', { name: 'Начните со своего реестра', exact: true });
    await final.scrollIntoViewIfNeeded();
    const title = await final.getByRole('heading').boundingBox();
    const link = await final.getByRole('link', { name: 'Загрузить реестр' }).boundingBox();
    expect(Math.abs(title!.x - link!.x)).toBeLessThanOrEqual(2);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
    ).toBeLessThanOrEqual(2);
    await page.goto('/app');
    const operations = page.getByRole('navigation', { name: 'Операции с дебиторкой' });
    await showOperations(page);
    for (const button of await operations.getByRole('button').all())
      await expect(button).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
    ).toBeLessThanOrEqual(2);
    await page.screenshot({
      path: info.outputPath(`workspace-${width}.png`),
      animations: 'disabled',
    });
    await page.getByRole('button', { name: 'Профиль и настройки', exact: true }).click();
    const menu = await page.getByRole('menu').boundingBox();
    expect(menu!.y).toBeGreaterThanOrEqual(0);
    expect(menu!.y + menu!.height).toBeLessThanOrEqual(901);
    await page.getByRole('menuitem', { name: 'Настройки', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Настройки', exact: true })).toBeVisible();
  }
});
