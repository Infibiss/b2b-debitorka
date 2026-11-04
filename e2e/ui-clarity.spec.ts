import { test, expect, navigate } from './fixtures';
import type { Page } from '@playwright/test';
async function account(page: Page, suffix: string) {
  const r = await page.request.post('/api/auth/register', {
    data: {
      name: 'Анна',
      company: 'Поставка',
      email: `clarity-${suffix}-${Date.now()}@example.ru`,
      password: 'Mandato-clarity-2026!',
    },
  });
  expect(r.status()).toBe(201);
  await page.goto('/app');
  return r.json();
}
test('landing has controlled headline, concise copy and spaced footer contacts', async ({
  page,
}, info) => {
  await page.goto('/');
  if (info.project.name === 'desktop') await page.setViewportSize({ width: 1728, height: 1100 });
  await expect(page.locator('.pub-hero h1')).toBeVisible();
  await expect(page.locator('.pub-hero h1 br')).toHaveCount(1);
  const size = await page
    .locator('.pub-hero h1')
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(size).toBeLessThanOrEqual(80);
  await expect(page.getByText('ВАШИ КЛИЕНТЫ · ВАШИ ПРАВИЛА', { exact: true })).toHaveCount(0);
  await expect(page.locator('.section-kicker')).toHaveCount(0);
  const note = page.getByText('Правила утверждаете вы. История сохраняется.', { exact: true });
  await expect(note).toHaveCount(0);
  await expect(page.getByText('Для бизнеса. По-человечески.', { exact: true })).toHaveCount(0);
  const footer = page.locator('.pub-footer');
  const brand = await footer.getByRole('link', { name: 'Mandato — на главную' }).boundingBox();
  const email = await footer
    .getByRole('link', { name: 'info@mandato.ru', exact: true })
    .boundingBox();
  expect(brand).not.toBeNull();
  expect(email).not.toBeNull();
  expect(email!.y - (brand!.y + brand!.height)).toBeGreaterThanOrEqual(12);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(2);
  await page.screenshot({
    path: info.outputPath('landing-refined.png'),
    fullPage: false,
    animations: 'disabled',
  });
});
test('learning is contextual nonmodal and supports back without hiding the screen', async ({
  page,
}, info) => {
  await account(page, info.project.name);
  await page.getByRole('button', { name: 'Позже', exact: true }).click();
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  const coach = page.getByRole('complementary', { name: 'Обучение: Работа', exact: true });
  await expect(coach).toBeVisible();
  await expect(page.locator('.modal-backdrop')).toHaveCount(0);
  await expect(coach.getByRole('button', { name: 'Назад', exact: true })).toBeDisabled();
  await coach.getByRole('button', { name: 'Далее', exact: true }).click();
  await expect(
    coach.getByRole('heading', { name: 'Добавьте первое дело', exact: true })
  ).toBeVisible();
  await coach.getByRole('button', { name: 'Назад', exact: true }).click();
  await expect(coach.getByRole('heading', { name: 'Загрузите реестр', exact: true })).toBeVisible();
  const box = await coach.boundingBox();
  const viewport = page.viewportSize()!;
  expect(viewport.width - box!.x - box!.width).toBeLessThanOrEqual(25);
  expect(viewport.height - box!.y - box!.height).toBeLessThanOrEqual(25);
  await page.getByRole('button', { name: 'Аудит', exact: true }).click();
  await expect(coach).toHaveCount(0);
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  const audit = page.getByRole('complementary', { name: 'Обучение: Аудит', exact: true });
  await expect(audit).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Аудит дебиторки', exact: true })).toBeVisible();
  await expect(audit.getByRole('list')).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath('learning-audit.png'),
    fullPage: false,
    animations: 'disabled',
  });
  for (const section of ['Подключения', 'Управление']) {
    await page.getByRole('button', { name: section, exact: true }).click();
    await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
    await expect(
      page.getByRole('complementary', { name: `Обучение: ${section}`, exact: true })
    ).toBeVisible();
  }
});
test('audit selects reserve room for chevrons and preserve native selection and keyboard focus', async ({
  page,
}, info) => {
  await account(page, `audit-${info.project.name}`);
  await page.getByRole('button', { name: 'Аудит', exact: true }).click();
  await page.getByRole('button', { name: 'Собрать аудит', exact: true }).click();
  const select = page.getByLabel('Важность замечаний', { exact: true });
  await expect(select).toBeVisible();
  const css = await select.evaluate((el) => ({
    appearance: getComputedStyle(el).appearance,
    padding: parseFloat(getComputedStyle(el).paddingRight),
  }));
  expect(css.appearance).toBe('none');
  expect(css.padding).toBeGreaterThanOrEqual(36);
  await select.selectOption('urgent');
  await expect(select).toHaveValue('urgent');
  await select.focus();
  await select.press('Tab');
  await expect(page.getByRole('link', { name: 'Скачать отчёт', exact: true })).toBeFocused();
  await expect(page.locator('.portfolio-empty .portfolio-empty')).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath('audit-controls.png'),
    fullPage: false,
    animations: 'disabled',
  });
});
test('empty work starts without zero totals or a duplicate overview destination', async ({
  page,
}, info) => {
  await account(page, `overview-${info.project.name}`);
  await expect(page.getByRole('region', { name: 'Суммы по портфелю', exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Начните с вашего реестра', exact: true })
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Обзор', exact: true })).toHaveCount(0);
});

test('large portfolio totals fit a narrow workspace', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.route('**/api/overview', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({
      response,
      json: {
        ...body,
        total_outstanding: 9876543210123,
        overdue_amount: 123456789012,
        promised_amount: 56789123456,
        collected_amount: 34567890123,
      },
    });
  });
  const session = await account(page, `large-${info.project.name}`);
  const added = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      company: 'Крупный покупатель',
      number: 'LARGE-1',
      issued_on: '2026-08-01',
      due_on: '2026-09-01',
      amount: 9876543210123,
    },
  });
  expect(added.status()).toBe(201);
  await page.reload();
  await page.getByText('Сводка портфеля и источники оплат', { exact: true }).click();
  const sums = page.getByRole('region', { name: 'Суммы по портфелю' });
  await expect(sums).toContainText('млрд');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(2);
  await page.screenshot({
    path: info.outputPath('work-large-portfolio.png'),
    fullPage: false,
    animations: 'disabled',
  });
});
test('learning starts on its own section and independent sections retain their progress', async ({
  page,
}, info) => {
  await account(page, `context-${info.project.name}`);
  await page.getByRole('button', { name: 'Позже', exact: true }).click();
  await navigate(page, 'Оплаты и сверка');
  await expect(page.getByRole('button', { name: 'Начать обучение', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  const financeGuide = page.getByRole('complementary', {
    name: 'Обучение: Оплаты и сверка',
    exact: true,
  });
  await expect(financeGuide).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Оплаты и сверка', exact: true })).toBeVisible();
  await financeGuide.getByRole('button', { name: 'Далее', exact: true }).click();
  await financeGuide.getByRole('button', { name: 'Закрыть обучение', exact: true }).click();
  await page.getByRole('button', { name: 'Аудит', exact: true }).click();
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await expect(
    page
      .getByRole('complementary', { name: 'Обучение: Аудит' })
      .getByRole('heading', { name: 'Соберите аудит' })
  ).toBeVisible();
  await page.getByRole('button', { name: 'Работа', exact: true }).click();
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await expect(
    page
      .getByRole('complementary', { name: 'Обучение: Работа', exact: true })
      .getByRole('heading', { name: 'Загрузите реестр' })
  ).toBeVisible();
});

test('an invitation opens when its link changes within an existing login page', async ({
  page,
}, info) => {
  const r = await page.request.post('/api/auth/register', {
    data: {
      name: 'Руководитель',
      company: 'Поставка',
      email: `hash-owner-${info.project.name}-${Date.now()}@example.ru`,
      password: 'Mandato-hash-owner-2026!',
    },
  });
  expect(r.status()).toBe(201);
  const session = await r.json();
  const invite = await page.request.post('/api/workflow/invitations', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: { email: `hash-bookkeeper-${info.project.name}-${Date.now()}@example.ru` },
  });
  expect(invite.status()).toBe(201);
  const { token } = await invite.json();
  const logout = await page.request.post('/api/auth/logout', {
    headers: { 'X-CSRF-Token': session.csrf_token },
  });
  expect(logout.status()).toBe(200);
  await page.goto('/app?mode=login');
  await expect(page.getByLabel('Рабочая почта', { exact: true })).toBeVisible();
  await page.goto(`/app?mode=login#invite=${token}`);
  await expect(
    page.getByRole('heading', { name: 'Присоединиться к команде', exact: true })
  ).toBeVisible();
});

test('a delayed initial audit read cannot erase a newly collected report', async ({
  page,
}, info) => {
  await account(page, `audit-race-${info.project.name}`);
  let release!: () => void;
  let captured!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const ready = new Promise<void>((resolve) => {
    captured = resolve;
  });
  await page.route('**/api/portfolio', async (route) => {
    const response = await route.fetch();
    captured();
    await held;
    await route.fulfill({ response });
  });
  try {
    await page.getByRole('button', { name: 'Аудит', exact: true }).click();
    await ready;
    await page.getByRole('button', { name: 'Собрать аудит', exact: true }).click();
    await expect(page.getByLabel('Важность замечаний', { exact: true })).toBeVisible();
    const initialRead = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/portfolio');
    release();
    await initialRead;
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
        )
    );
    await expect(page.getByLabel('Важность замечаний', { exact: true })).toBeVisible();
  } finally {
    release();
  }
});
