import { test, expect, navigate, type Page } from './fixtures';

async function account(page: Page, suffix: string) {
  const result = await page.request.post('/api/auth/register', {
    data: {
      name: 'Анна',
      company: 'Северные системы',
      email: `workspace-polish-${suffix}-${Date.now()}@example.ru`,
      password: 'Mandato-Workspace-2026!',
    },
  });
  expect(result.status()).toBe(201);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Позже', exact: true }).click();
}

test('section help directly starts the current section guide without a training dialog', async ({
  page,
}, info) => {
  await account(page, `help-${info.project.name}`);
  for (const [label, section] of [
    ['Работа', 'workflow'],
    ['Аудит', 'audit'],
    ['Подключения', 'connections'],
    ['Управление', 'management'],
    ['Переписка', 'messages'],
    ['Оплаты и сверка', 'finance'],
    ['Документы', 'yandex'],
    ['Настройки', 'settings'],
  ]) {
    await navigate(page, label);
    await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
    const guide = page.getByRole('complementary', { name: `Обучение: ${label}`, exact: true });
    await expect(guide).toBeVisible({ timeout: 2000 });
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Учебный разговор', exact: true })).toHaveCount(
      0
    );
    expect(new URL(page.url()).searchParams.get('section') || 'workflow').toBe(section);
    await guide.getByRole('button', { name: 'Далее', exact: true }).click();
    await expect(guide.getByRole('button', { name: 'Назад', exact: true })).toBeEnabled();
    await guide.getByRole('button', { name: 'Закрыть обучение', exact: true }).click();
  }
});

test('workspace logo fits the sidebar and search has one coherent keyboard focus', async ({
  page,
}, info) => {
  await account(page, `controls-${info.project.name}`);
  const brand = page.locator('.sidebar-brand .brand');
  const mark = await brand.locator('svg').boundingBox();
  const word = await brand.locator('span').boundingBox();
  const sidebar = await page.locator('.sidebar').boundingBox();
  expect(mark).not.toBeNull();
  expect(word).not.toBeNull();
  expect(sidebar).not.toBeNull();
  expect(mark!.width).toBeLessThanOrEqual(36);
  expect(mark!.height).toBeLessThanOrEqual(36);
  expect(word!.x + word!.width).toBeLessThanOrEqual(sidebar!.x + sidebar!.width - 8);
  const search = page.getByRole('textbox', { name: 'Поиск дел', exact: true });
  await search.focus();
  const focused = await search.evaluate((input) => {
    const own = getComputedStyle(input),
      group = getComputedStyle(input.parentElement!);
    return {
      inputOutline: own.outlineStyle,
      inputShadow: own.boxShadow,
      groupOutline: group.outlineStyle,
      groupShadow: group.boxShadow,
    };
  });
  expect(focused.inputOutline).toBe('none');
  expect(focused.inputShadow).toBe('none');
  expect(focused.groupOutline !== 'none' || focused.groupShadow !== 'none').toBeTruthy();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  ).toBeLessThanOrEqual(2);
});

test('ordinary correspondence and tool panels use the same white surface', async ({
  page,
}, info) => {
  await account(page, `surfaces-${info.project.name}`);
  for (const [section, selector] of [
    ['Переписка', '.case-conversation, section.panel'],
    ['Прогноз и условия', '.ms-card'],
    ['Оплаты и сверка', '.ops-card'],
    ['Документы', '.ops-card'],
    ['Настройки', '.settings-panel'],
  ]) {
    await navigate(page, section);
    const panels = page.locator(
      `#workspace-main ${selector.split(', ').join(', #workspace-main ')}`
    );
    await expect(panels.first()).toBeVisible();
    const backgrounds = await panels.evaluateAll((items) =>
      items.map((el) => getComputedStyle(el).backgroundColor)
    );
    expect(
      backgrounds.every((color) => color === 'rgb(255, 255, 255)'),
      `${section}: ${backgrounds.join(', ')}`
    ).toBeTruthy();
  }
});

test('communication tabs visibly identify the selected channel', async ({ page }, info) => {
  await account(page, `channel-${info.project.name}`);
  await navigate(page, 'Переписка');
  const history = page.getByRole('button', { name: 'История и письма', exact: true });
  const calls = page.getByRole('button', { name: 'Звонки', exact: true });
  const background = async (button: import('@playwright/test').Locator) =>
    button.evaluate((element) => getComputedStyle(element).backgroundColor);
  await expect(history).toHaveAttribute('aria-pressed', 'true');
  expect(await background(history)).not.toBe(await background(calls));
  const selected = await background(history);
  await calls.click();
  await expect(calls).toHaveAttribute('aria-pressed', 'true');
  await expect(calls).toHaveCSS('background-color', selected);
  await expect(history).not.toHaveCSS('background-color', selected);
});
