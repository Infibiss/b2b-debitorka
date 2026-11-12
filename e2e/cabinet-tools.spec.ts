import { expect, test, navigate, type Page } from './fixtures';

const password = 'Correct-horse-24!';

async function signUp(page: Page) {
  const email = `tools-${Date.now()}-${Math.random().toString(16).slice(2)}@example.ru`;
  await page.goto('/app?mode=register');
  await page.getByLabel('Ваше имя').fill('Анна');
  await page.getByLabel('Компания', { exact: true }).fill('ООО Поставка');
  await page.getByLabel('Рабочая почта').fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  for (const box of await page.getByRole('checkbox').all()) await box.check();
  await page.locator('form').getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByRole('heading', { name: 'Главная' })).toBeVisible();
}

async function addInvoice(page: Page) {
  const csrf = await page.evaluate(
    async () => (await (await fetch('/api/auth/me')).json()).csrf_token
  );
  const day = (offset: number) =>
    new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10);
  const response = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      company: 'ООО Север',
      inn: '7701234567',
      email: 'ap@example.ru',
      number: 'СЧ-1',
      issued_on: day(-40),
      due_on: day(-20),
      amount: 50000000,
      notes: '',
    },
  });
  expect(response.ok()).toBeTruthy();
}

test('a court order pdf becomes a proposal tied to the debtor', async ({ page, browser }) => {
  const printer = await (await browser.newContext()).newPage();
  await printer.setContent(
    '<meta charset="utf-8"><pre>АРБИТРАЖНЫЙ СУД ГОРОДА МОСКВЫ\nСУДЕБНЫЙ ПРИКАЗ\n12 марта 2026 года Дело № А40-777/2026\nВзыскать с ООО Север (ИНН 7701234567) задолженность 500 000 руб.</pre>'
  );
  const buffer = await printer.pdf();
  await signUp(page);
  await addInvoice(page);
  await page.reload();
  await navigate(page, 'Распознавание');
  await page.getByLabel('Загрузить PDF').setInputFiles({
    name: 'order.pdf',
    mimeType: 'application/pdf',
    buffer,
  });
  const card = page.locator('.rc-recognition');
  await expect(card.getByRole('heading', { name: 'Судебный приказ' })).toBeVisible();
  await expect(card.getByLabel('Номер дела')).toHaveValue('А40-777/2026');
  await expect(card.getByLabel('Должник').locator('option:checked')).toHaveText('ООО Север');
  await card.getByRole('button', { name: 'Подтвердить' }).click();
  await expect(page.locator('.rc-recognition')).toHaveCount(0);
});

test('a second company has its own debtors and can be switched back', async ({ page }) => {
  await signUp(page);
  await addInvoice(page);
  await page.reload();
  const profile = page.getByRole('button', { name: 'Профиль и настройки' });
  await profile.click();
  await page.getByRole('menuitem', { name: 'Добавить организацию' }).click();
  const dialog = page.getByRole('dialog', { name: 'Новая организация' });
  await dialog.getByLabel('Название').fill('ООО Вторая');
  await dialog.getByRole('button', { name: 'Создать' }).click();
  await profile.click();
  await expect(page.getByRole('menuitemradio', { name: 'ООО Вторая' })).toHaveAttribute(
    'aria-checked',
    'true'
  );
  await page.keyboard.press('Escape');
  await navigate(page, 'Должники');
  await expect(page.getByRole('button', { name: 'ООО Север' })).toHaveCount(0);
  await profile.click();
  await page.getByRole('menuitemradio', { name: 'ООО Поставка' }).click();
  await expect(page.getByRole('heading', { name: 'Главная' })).toBeVisible();
  await navigate(page, 'Должники');
  await expect(page.getByRole('button', { name: 'ООО Север' }).first()).toBeVisible();
});

test('home charts change type, gain a chart and a report gets a schedule', async ({ page }) => {
  await signUp(page);
  await addInvoice(page);
  await page.reload();
  const charts = page.getByRole('region', { name: 'Графики' });
  await expect(charts.getByRole('heading', { name: 'Долг по сроку просрочки' })).toBeVisible();
  await page.getByRole('button', { name: 'Настроить графики' }).click();
  const first = charts.locator('.ch-card').first();
  await first.getByLabel('Вид').selectOption('line');
  await expect(first.locator('.ch-line')).toBeVisible();
  await charts.getByRole('button', { name: 'Добавить график' }).click();
  const added = charts.locator('.ch-card').last();
  await added.getByLabel('Вид').selectOption('number');
  await added.getByLabel('Что считать').selectOption('overdue');
  await expect(added.locator('.ch-number')).toContainText('500');
  await page.getByRole('button', { name: 'Готово' }).click();
  await page.reload();
  await expect(charts.locator('.ch-card').first().locator('.ch-line')).toBeVisible();
  await expect(charts.locator('.ch-card')).toHaveCount(5);
  await navigate(page, 'Отчёты');
  await page.getByRole('button', { name: 'Новое расписание' }).click();
  await page.locator('.rc-settings').getByLabel('Название').fill('Для бухгалтерии');
  await page.locator('.rc-settings').getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.locator('.rc-documents')).toContainText('Для бухгалтерии');
});

test('the workspace fits every width without sideways scrolling', async ({ page }) => {
  test.setTimeout(240_000);
  await signUp(page);
  await addInvoice(page);
  await page.reload();
  for (const section of ['home', 'debtors', 'recognize', 'templates', 'reports', 'settings']) {
    await page.goto(`/app?section=${section}`);
    await expect(page.locator('.rc-page').first()).toBeVisible();
    for (const width of [320, 390, 600, 768, 900, 1024, 1280, 1600]) {
      await page.setViewportSize({ width, height: 800 });
      await page.waitForTimeout(80);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
        `${section} ${width}`
      ).toBeLessThanOrEqual(1);
    }
  }
});
