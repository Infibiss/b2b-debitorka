import { expect, test, type Page } from '@playwright/test';

const PASSWORD = 'AgentPay-e2e-correct-2026!';
const businessDate = (instant: Date) => instant.toLocaleDateString('en-CA', { timeZone: 'Europe/Moscow' });
const today = businessDate(new Date());
const nextWeek = businessDate(new Date(Date.now() + 7 * 86_400_000));

async function register(page: Page) {
  const email = `e2e-${Date.now()}-${Math.random().toString(16).slice(2)}@example.ru`;
  await page.goto('/');
  await page.getByRole('link', { name: 'Начать работу', exact: true }).first().click();
  await expect(page).toHaveURL(/\/app/);
  await page.getByLabel('Компания', { exact: true }).fill('ООО Проверка');
  await page.getByLabel('Ваше имя', { exact: true }).fill('Анна');
  await page.getByLabel('Рабочая почта', { exact: true }).fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD);
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: /Создать аккаунт|Зарегистрироваться/ }).last().click();
  await expect(page.getByRole('button', { name: 'Реестр', exact: true })).toBeVisible();
  return email;
}

async function openRegistry(page: Page) {
  await page.getByRole('button', { name: /^Реестр/ }).click();
}

async function createInvoice(page: Page, number: string, amount: string, issuedOn = '2026-10-01', dueOn = '2026-10-15') {
  await openRegistry(page);
  await page.getByRole('button', { name: 'Добавить счёт', exact: true }).first().click();
  await page.getByLabel('Контрагент', { exact: true }).fill('ООО Северные системы');
  await page.getByLabel('ИНН', { exact: true }).fill('7701234567');
  await page.getByLabel('Email покупателя', { exact: true }).fill('ap@example.ru');
  await page.getByLabel('Номер счёта', { exact: true }).fill(number);
  await page.getByLabel('Дата счёта', { exact: true }).fill(issuedOn);
  await page.getByLabel('Оплатить до', { exact: true }).fill(dueOn);
  await page.getByLabel('Сумма', { exact: true }).fill(amount);
  await page.getByRole('button', { name: 'Добавить счёт', exact: true }).last().click();
  await expect(page.getByText(number, { exact: true }).first()).toBeVisible();
}

async function assertNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBe(false);
}

test('public website is readable, interactive, and offers a real signup', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('h1')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Начать работу', exact: true }).first()).toBeVisible();
  const lastStep = page.getByRole('tab', { name: /Закрываем оплатой/ });
  await lastStep.click();
  await expect(lastStep).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel')).toContainText('Деньги снова в деле.');
  const initialCost = await page.locator('.calc-result strong').innerText();
  await page.getByLabel('Дней ожидания').fill('60');
  await expect(page.locator('.calc-result strong')).not.toHaveText(initialCost);
  await page.getByRole('button', { name: 'Как загрузить данные из 1С?', exact: true }).click();
  await expect(page.getByText(/Выгрузите реестр в CSV/)).toBeVisible();
  for (const section of await page.locator('.reveal').all()) await section.scrollIntoViewIfNeeded();
  await page.locator('h1').scrollIntoViewIfNeeded();
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: info.outputPath('landing.png'), fullPage: true, animations: 'disabled' });
  await page.getByRole('link', { name: 'Начать работу', exact: true }).first().click();
  await expect(page.getByLabel('Компания', { exact: true })).toBeVisible();
  await assertNoHorizontalOverflow(page);
});

test('invoice, approved draft, promise, payments and login persist without a fake email send', async ({ page }, info) => {
  const email = await register(page);
  const number = `СЧ-E2E-${Date.now()}`;
  await createInvoice(page, number, '1250.50');
  await page.getByText(number, { exact: true }).first().click();
  const drawer = page.getByRole('dialog', { name: 'Карточка счёта', exact: true });
  await expect.poll(() => drawer.evaluate(element => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Shift+Tab');
  await expect.poll(() => drawer.evaluate(element => element.contains(document.activeElement))).toBe(true);
  await page.getByRole('button', { name: 'Подготовить письмо', exact: true }).click();
  await expect(page.getByRole('button', { name: /Согласовать/ }).first()).toBeVisible();
  await page.getByRole('button', { name: /Согласовать/ }).first().click();
  // SMTP is deliberately disabled; successful send must never be fabricated.
  await expect(page.locator('.editor-safety')).toContainText('Отправка доступна после подключения почты');
  const send = page.getByRole('button', { name: 'Отправить письмо', exact: true });
  await expect(send).toBeVisible();
  await expect(send).toBeEnabled();
  const sendResponse = page.waitForResponse(response => /\/api\/messages\/[^/]+\/send$/.test(response.url()));
  await send.click();
  expect((await sendResponse).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('Почта компании не подключена');
  await expect(page.getByText('Отправлено', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Обещание оплаты', exact: true }).click();
  await page.getByLabel('Дата оплаты', { exact: true }).fill(nextWeek);
  await page.getByRole('button', { name: 'Сохранить обещание', exact: true }).click();
  await expect(drawer.locator('.promise-banner')).toContainText('Обещание оплаты');

  await page.getByRole('button', { name: 'Внести оплату', exact: true }).click();
  await page.getByLabel('Сумма оплаты', { exact: true }).fill('250.50');
  await page.getByLabel('Дата поступления', { exact: true }).fill(today);
  await page.getByLabel('Номер платежа', { exact: true }).fill('E2E-001');
  await page.getByRole('button', { name: 'Записать оплату', exact: true }).click();
  await expect(drawer.locator('.drawer-balance > strong')).toHaveText(/1\s?000\s?₽/);
  await drawer.evaluate(element => element.scrollTo({ top: 0 }));
  await page.screenshot({ path: info.outputPath('drawer.png'), fullPage: true, animations: 'disabled' });
  await assertNoHorizontalOverflow(page);

  await page.reload();
  await openRegistry(page);
  await page.getByText(number, { exact: true }).first().click();
  await page.getByRole('button', { name: 'Внести оплату', exact: true }).click();
  await page.getByLabel('Сумма оплаты', { exact: true }).fill('1000');
  await page.getByLabel('Дата поступления', { exact: true }).fill(today);
  await page.getByLabel('Номер платежа', { exact: true }).fill('E2E-002');
  await page.getByRole('button', { name: 'Записать оплату', exact: true }).click();
  await expect(drawer.locator('.drawer-invoice-head')).toContainText('Оплачен');
  await expect(page.getByRole('button', { name: 'Подготовить письмо', exact: true })).toBeDisabled();

  await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).click();
  await page.getByRole('button', { name: /Выйти/ }).click();
  await page.getByRole('button', { name: /^Войти$/ }).first().click();
  await page.getByLabel('Рабочая почта', { exact: true }).fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: /^Войти$/ }).last().click();
  await openRegistry(page);
  await expect(page.getByText(number, { exact: true }).first()).toBeVisible();
  await expect(page.locator('.invoice-table')).toContainText('Оплачен');
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: info.outputPath('workspace.png'), fullPage: true, animations: 'disabled' });
});

test('a promise due today is not shown as a broken promise', async ({ page }) => {
  await register(page);
  const number = `PROMISE-${Date.now()}`;
  const issued = businessDate(new Date(Date.now() - 60 * 86_400_000));
  const due = businessDate(new Date(Date.now() - 45 * 86_400_000));
  await createInvoice(page, number, '1250', issued, due);
  await page.getByText(number, { exact: true }).first().click();
  await page.getByRole('button', { name: 'Обещание оплаты', exact: true }).click();
  await page.getByLabel('Дата оплаты', { exact: true }).fill(today);
  await page.getByRole('button', { name: 'Сохранить обещание', exact: true }).click();
  await expect(page.locator('.promise-banner')).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).click();
  await page.getByRole('button', { name: 'Обзор', exact: true }).click();
  await expect(page.locator('.attention-list')).toContainText('ООО Северные системы');
  await expect(page.locator('.attention-list')).not.toContainText('Нарушено обещание');
});

test('correcting a contact invalidates the old recipient and persists a fresh draft', async ({ page }) => {
  await register(page);
  const number = `CONTACT-${Date.now()}`;
  const note = 'Адрес подтверждён покупателем';
  await createInvoice(page, number, '500');
  await page.getByText(number, { exact: true }).first().click();
  const drawer = page.getByRole('dialog', { name: 'Карточка счёта', exact: true });
  await page.getByRole('button', { name: 'Подготовить письмо', exact: true }).click();
  await page.getByRole('button', { name: 'Согласовать письмо', exact: true }).click();
  await expect(drawer.locator('.editor-header')).toContainText('Согласовано');
  await page.getByRole('button', { name: 'Изменить контакт и заметку', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Контакт и заметка', exact: true });
  await dialog.getByLabel('Email покупателя', { exact: true }).fill('corrected@example.ru');
  await dialog.getByLabel('Заметка по счёту', { exact: true }).fill(note);
  await dialog.getByRole('button', { name: 'Сохранить контакт', exact: true }).click();
  await expect(drawer.locator('.drawer-company')).toContainText('corrected@example.ru');
  await drawer.locator('.message-item').filter({ hasText: 'ap@example.ru' }).click();
  const staleApproval = page.waitForResponse(response => /\/api\/messages\/[^/]+\/approve$/.test(response.url()));
  await page.getByRole('button', { name: 'Согласовать письмо', exact: true }).click();
  expect((await staleApproval).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('Адрес получателя изменился');
  await page.getByRole('button', { name: 'Подготовить письмо', exact: true }).click();
  await expect(drawer.locator('.editor-to')).toContainText('corrected@example.ru');
  await page.reload();
  await openRegistry(page);
  await page.getByText(number, { exact: true }).first().click();
  await expect(drawer.locator('.drawer-company')).toContainText('corrected@example.ru');
  await expect(drawer.locator('.invoice-notes')).toContainText(note);
  await page.getByRole('button', { name: 'Поставить на паузу', exact: true }).click();
  await expect(drawer.locator('.drawer-invoice-head')).toContainText('На паузе');
  await expect(drawer.locator('.invoice-notes')).toContainText(note);
  await page.getByRole('button', { name: 'Вернуть в работу', exact: true }).click();
  await expect(drawer.locator('.drawer-invoice-head')).toContainText('В работе');
  await expect(drawer.locator('.invoice-notes')).toContainText(note);
});

test('CSV import previews invalid data, accepts valid rows, and avoids duplicates', async ({ page }) => {
  await register(page);
  await openRegistry(page);
  await page.getByRole('button', { name: /Импорт/ }).first().click();
  await page.locator('input[type="file"]').setInputFiles('e2e/fixtures/invalid.csv');
  await expect(page.getByText(/ошиб|положительн|больше нуля/i).first()).toBeVisible();
  await expect(page.getByRole('button', { name: /^Импортировать/ })).toBeDisabled();
  await page.locator('input[type="file"]').setInputFiles('e2e/fixtures/receivables.csv');
  await expect(page.getByText(/CSV-101/).first()).toBeVisible();
  await page.getByRole('button', { name: /^Импортировать/ }).click();
  await expect(page.getByText('CSV-101', { exact: true }).first()).toBeVisible();
  await page.reload();
  await openRegistry(page);
  await expect(page.getByText('CSV-101', { exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: /Импорт/ }).first().click();
  await page.locator('input[type="file"]').setInputFiles('e2e/fixtures/receivables.csv');
  await expect(page.getByText(/повтор|дубликат|уже существует/i).first()).toBeVisible();
});
