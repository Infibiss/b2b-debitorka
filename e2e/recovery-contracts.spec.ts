import { expect, test, type Page } from './fixtures';

async function setup(page: Page) {
  await page.goto('/app?mode=register');
  await page.getByLabel('Ваше имя').fill('Анна');
  await page.getByLabel('Компания', { exact: true }).fill('ООО Поставка');
  await page
    .getByLabel('Рабочая почта')
    .fill(`contracts-${Date.now()}-${Math.random().toString(16).slice(2)}@example.ru`);
  await page.getByLabel('Пароль', { exact: true }).fill('Correct-horse-24!');
  for (const checkbox of await page.getByRole('checkbox').all()) await checkbox.check();
  await page.locator('form').getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByRole('heading', { name: 'Главная', exact: true })).toBeVisible();
  const me = await (await page.request.get('/api/auth/me')).json();
  const headers = { 'X-CSRF-Token': me.csrf_token };
  const invoices: { id: string; counterparty_id: string }[] = [];
  const day = (offset: number) =>
    new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10);
  for (const number of ['А-1', 'Б-1', 'Без-1']) {
    const response = await page.request.post('/api/invoices', {
      headers,
      data: {
        company: 'ООО Север',
        inn: '7701234567',
        email: 'ap@example.ru',
        number,
        issued_on: day(-40),
        due_on: day(-20),
        amount: 10000000,
        notes: '',
      },
    });
    expect(response.status()).toBe(201);
    invoices.push(await response.json());
  }
  await page.goto('/app?section=debtors');
  await page.getByRole('button', { name: 'ООО Север', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'ООО Север', exact: true })).toBeVisible();
  return { invoices, headers, day };
}

async function contract(page: Page, name: string, invoice: string) {
  await page.getByRole('button', { name: 'Указать договор', exact: true }).click();
  await page.getByLabel('Номер и дата договора').fill(name);
  await page.getByRole('checkbox', { name: `Счёт ${invoice}` }).check();
  await page.getByRole('button', { name: 'Сохранить договор', exact: true }).click();
  await expect(page.getByLabel('Договор или счёт')).toHaveValue(/^contract:/);
  await expect(page.getByRole('option', { name: `Договор ${name}`, exact: true })).toBeAttached();
}

async function selectCase(page: Page, name: string) {
  const response = page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      r.url().includes('/api/recovery/debtors/') &&
      r.url().includes('case_id=')
  );
  await page.getByLabel('Договор или счёт').selectOption({ label: name });
  expect((await response).ok()).toBeTruthy();
  await expect(page.locator('.rc-case-scope')).toBeVisible();
}

test('contracts keep separate promises, disputes, invoices and balances after reload', async ({
  page,
}) => {
  const { invoices, headers, day } = await setup(page);
  await expect(page.getByRole('button', { name: 'Начать работу', exact: true })).toHaveCount(0);
  await contract(page, 'А от 01.11.2026', 'А-1');
  // The overview exposes unassigned invoices without changing either existing case.
  await page.getByLabel('Договор или счёт').selectOption('');
  await expect(page.getByRole('button', { name: 'Указать договор', exact: true })).toBeVisible();
  await contract(page, 'Б от 02.11.2026', 'Б-1');
  await page.getByRole('button', { name: 'Начать работу', exact: true }).click();
  await page.getByRole('button', { name: 'Отметить спор', exact: true }).click();
  await page
    .getByLabel('Комментарий', { exact: true })
    .fill('Не согласны с качеством по договору Б');
  await page.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(page.locator('.rc-head').getByText(/Спор/)).toBeVisible();

  await selectCase(page, 'Договор А от 01.11.2026');
  await page.getByRole('button', { name: 'Начать работу', exact: true }).click();
  await page.getByRole('button', { name: 'Записать обещание', exact: true }).click();
  await page.getByLabel('Дата обещанной оплаты', { exact: true }).fill(day(5));
  await page.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(page.locator('.rc-head').getByText(/Обещал оплатить/)).toBeVisible();
  const promiseUrl = page.url();
  await page.reload();
  await expect(page.getByLabel('Договор или счёт')).toHaveValue(/^contract:/);
  await expect(page.locator('.rc-head').getByText(/Обещал оплатить/)).toBeVisible();
  await page.getByRole('button', { name: 'Счета', exact: true }).click();
  await expect(page.locator('.rc-table').getByText('А-1', { exact: true })).toBeVisible();
  await expect(page.locator('.rc-table').getByText('Б-1', { exact: true })).toHaveCount(0);

  // A real ledger mutation in B must not reduce A's displayed balance.
  const payment = await page.request.post(`/api/invoices/${invoices[1].id}/payments`, {
    headers,
    data: { amount: 2500000, paid_on: day(0), reference: 'ПП-Б-1' },
  });
  expect(payment.ok()).toBeTruthy();
  await page.goto(promiseUrl);
  await expect(page.locator('.rc-amount strong')).toHaveText(/100\s*000/);
  await selectCase(page, 'Договор Б от 02.11.2026');
  await expect(page.locator('.rc-head').getByText(/Спор/)).toBeVisible();
  await expect(page.locator('.rc-amount strong')).toHaveText(/75\s*000/);
  await page.getByRole('button', { name: 'Счета', exact: true }).click();
  await expect(page.locator('.rc-table').getByText('Б-1', { exact: true })).toBeVisible();
  await expect(page.locator('.rc-table').getByText('А-1', { exact: true })).toHaveCount(0);
  await selectCase(page, 'Без договора · Без-1');
  await expect(page.locator('.rc-head').getByText(/Новый/)).toBeVisible();
  if (test.info().project.name === 'desktop') {
    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect
        .poll(() =>
          page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)
        )
        .toBe(true);
      await page.screenshot({
        path: `var/review-2026-11-24/contracts-${width}.png`,
        fullPage: true,
      });
    }
  }
});

test('switching case hides stale controls while a delayed detail is loading', async ({ page }) => {
  await setup(page);
  await contract(page, 'А от 01.11.2026', 'А-1');
  const a = await page.getByLabel('Договор или счёт').inputValue();
  await page.getByLabel('Договор или счёт').selectOption('');
  await contract(page, 'Б от 02.11.2026', 'Б-1');
  const b = await page.getByLabel('Договор или счёт').inputValue();
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/recovery/debtors/*?case_id=${encodeURIComponent(a)}`, async (route) => {
    await gate;
    await route.continue();
  });
  try {
    await page.getByLabel('Договор или счёт').selectOption(a);
    await expect(page.getByRole('button', { name: 'Начать работу', exact: true })).toHaveCount(0);
    await expect(page.getByText('Загружаем…', { exact: true })).toBeVisible();
  } finally {
    release();
  }
  await expect(page.getByLabel('Договор или счёт')).toHaveValue(a);
  await expect(page.getByRole('button', { name: 'Начать работу', exact: true })).toBeVisible();
  await page.route(`**/api/recovery/debtors/*?case_id=${encodeURIComponent(b)}`, (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Не удалось загрузить выбранный договор' }),
    })
  );
  await page.getByLabel('Договор или счёт').selectOption(b);
  await expect(page.getByRole('alert')).toHaveText('Не удалось загрузить выбранный договор');
  await expect(page.getByRole('button', { name: 'Начать работу', exact: true })).toHaveCount(0);
});

test('an in-flight action cannot erase the next form or change its contract', async ({ page }) => {
  await setup(page);
  await contract(page, 'А от 01.11.2026', 'А-1');
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/recovery/debtors/*/actions?*', async (route) => {
    if (route.request().postDataJSON()?.action === 'start') await gate;
    await route.continue();
  });
  try {
    await page.getByRole('button', { name: 'Начать работу', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Отметить спор', exact: true })).toBeDisabled();
    await expect(page.getByLabel('Договор или счёт')).toBeDisabled();
  } finally {
    release();
  }
  await expect(page.getByRole('button', { name: 'Отметить спор', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Отметить спор', exact: true }).click();
  await expect(page.getByLabel('Комментарий', { exact: true })).toBeVisible();
});
