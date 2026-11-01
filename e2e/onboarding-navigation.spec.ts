import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';

async function account(page: Page, suffix: string) {
  const response = await page.request.post('/api/auth/register', {
    data: {
      name: 'Анна',
      company: 'Поставка',
      email: `orientation-${suffix}-${Date.now()}@example.ru`,
      password: 'Mandato-orientation-2026!',
    },
  });
  expect(response.status()).toBe(201);
  const session = await response.json();
  await page.goto('/app');
  return session;
}

test('general orientation explains the four sections and can be replayed independently', async ({
  page,
}, info) => {
  await account(page, info.project.name);
  await page.getByRole('button', { name: 'Начать обучение', exact: true }).click();
  const coach = page.getByRole('complementary', { name: 'Обучение: Mandato', exact: true });
  await expect(coach).toBeVisible();
  await expect(
    coach.getByRole('heading', { name: 'Работа — дела и сроки', exact: true })
  ).toBeVisible();
  await expect(page.locator('[data-tour="nav-workflow"]')).toHaveClass(/wf-tour-highlight/);
  await expect(coach.getByRole('button', { name: 'Назад', exact: true })).toBeDisabled();
  for (const [section, title] of [
    ['audit', 'Аудит — что мешает оплате'],
    ['connections', 'Подключения — откуда приходят данные'],
    ['management', 'Управление — правила и команда'],
  ]) {
    await coach.getByRole('button', { name: 'Далее', exact: true }).click();
    await expect(coach.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(page.locator(`[data-tour="nav-${section}"]`)).toHaveClass(/wf-tour-highlight/);
  }
  await coach.getByRole('button', { name: 'Назад', exact: true }).click();
  await expect(
    coach.getByRole('heading', { name: 'Подключения — откуда приходят данные', exact: true })
  ).toBeVisible();
  await coach.getByRole('button', { name: 'Закрыть обучение', exact: true }).click();
  await page.getByRole('button', { name: 'Обучение', exact: true }).click();
  await expect(
    coach.getByRole('heading', { name: 'Работа — дела и сроки', exact: true })
  ).toBeVisible();
  for (let step = 0; step < 4; step += 1)
    await coach.getByRole('button', { name: 'Далее', exact: true }).click();
  await expect(
    coach.getByRole('heading', { name: 'Начните с реестра', exact: true })
  ).toBeVisible();
  await expect(page.locator('[data-tour="work-import"]')).toHaveClass(/wf-tour-highlight/);
  await coach.getByRole('button', { name: 'Готово', exact: true }).click();
  await expect(coach).toHaveCount(0);
  await page.getByRole('button', { name: 'Обучение', exact: true }).click();
  await expect(coach).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(coach).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Начать обучение', exact: true })).toHaveCount(0);
  expect((await (await page.request.get('/api/invoices')).json()).items).toHaveLength(0);
});

test('local work lesson highlights a compact empty action and then an actual case', async ({
  page,
}, info) => {
  const session = await account(page, `local-${info.project.name}`);
  await page.getByRole('button', { name: 'Позже', exact: true }).click();
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await page.getByRole('button', { name: 'Показать обзор раздела', exact: true }).click();
  const coach = page.getByRole('complementary', { name: 'Обучение: Работа', exact: true });
  await coach.getByRole('button', { name: 'Далее', exact: true }).click();
  await expect(
    coach.getByRole('heading', { name: 'Добавьте первое дело', exact: true })
  ).toBeVisible();
  await expect(page.locator('[data-tour="workflow-empty"]')).toHaveClass(/wf-tour-highlight/);
  await expect(page.locator('.wf-desk.wf-tour-highlight')).toHaveCount(0);
  const emptyBox = await page.locator('[data-tour="workflow-empty"]').boundingBox();
  expect(emptyBox!.height).toBeLessThan(180);
  await coach.getByRole('button', { name: 'Закрыть обучение', exact: true }).click();
  const added = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      company: 'ООО Покупатель',
      number: 'LEARN-42',
      issued_on: '2026-01-10',
      due_on: '2026-02-10',
      amount: 250000,
    },
  });
  expect(added.status()).toBe(201);
  await page.reload();
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await page.getByRole('button', { name: 'Показать обзор раздела', exact: true }).click();
  await coach.getByRole('button', { name: 'Далее', exact: true }).click();
  await expect(coach.getByRole('heading', { name: 'Откройте дело', exact: true })).toBeVisible();
  const highlighted = page.locator('[data-tour="workflow-case"].wf-tour-highlight');
  await expect(highlighted).toHaveCount(1);
  const box = await highlighted.boundingBox();
  expect(box!.height).toBeLessThan(450);
  await coach.getByRole('button', { name: 'Закрыть обучение', exact: true }).click();
  await page
    .getByRole('textbox', { name: 'Поиск дел', exact: true })
    .fill('Нет такого контрагента');
  await expect(page.getByRole('button', { name: 'Сбросить фильтры', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await page.getByRole('button', { name: 'Показать обзор раздела', exact: true }).click();
  await coach.getByRole('button', { name: 'Далее', exact: true }).click();
  await expect(coach.getByRole('heading', { name: 'Сбросьте фильтр', exact: true })).toBeVisible();
  await expect(page.locator('[data-tour="workflow-filter-empty"]')).toHaveClass(
    /wf-tour-highlight/
  );
  await expect(page.locator('[data-tour="work-import"]')).not.toHaveClass(/wf-tour-highlight/);
  await page.getByRole('button', { name: 'Сбросить фильтры', exact: true }).click();
  await expect(coach.getByRole('heading', { name: 'Откройте дело', exact: true })).toBeVisible();
  await expect(highlighted).toHaveCount(1);
  await page.getByRole('button', { name: 'Таблица', exact: true }).click();
  await expect(page.locator('.wf-table-row.wf-tour-highlight')).toHaveCount(1);
  await page.getByRole('button', { name: 'Аудит', exact: true }).click();
  await expect(coach).toHaveCount(0);
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await page.getByRole('button', { name: 'Показать обзор раздела', exact: true }).click();
  await expect(
    page.getByRole('complementary', { name: 'Обучение: Аудит', exact: true })
  ).toBeVisible();
});
