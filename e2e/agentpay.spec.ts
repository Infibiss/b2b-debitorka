import { navigate, expect, test, type Page } from './fixtures';

const PASSWORD = 'AgentPay-e2e-correct-2026!';
const businessDate = (instant: Date) =>
  instant.toLocaleDateString('en-CA', { timeZone: 'Europe/Moscow' });
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
  await page
    .getByRole('button', { name: /Создать аккаунт|Зарегистрироваться/ })
    .last()
    .click();
  await expect(page.getByRole('button', { name: 'Работа', exact: true })).toBeVisible();
  return email;
}

async function openRegistry(page: Page) {
  await navigate(page, 'Реестр');
}

async function createInvoice(
  page: Page,
  number: string,
  amount: string,
  issuedOn = '2026-10-01',
  dueOn = '2026-10-15'
) {
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
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1
  );
  expect(overflow).toBe(false);
}

async function selectInvoice(page: Page, number: string, scope = page.getByRole('main')) {
  const select = scope.getByRole('combobox', { name: 'Счёт', exact: true });
  const id = await select
    .locator('option')
    .filter({ hasText: number })
    .getAttribute('value', { timeout: 10000 });
  expect(id).toBeTruthy();
  await select.selectOption(id!);
}

test('public website is readable, interactive, and offers a real signup', async ({
  page,
}, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('h1')).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Начать работу', exact: true }).first()
  ).toBeVisible();
  const lastStep = page.getByRole('tab', { name: /Учитываем реальные поступления/ });
  await lastStep.click();
  await expect(lastStep).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel')).toContainText('300 000');
  const initialCost = await page.locator('.calc-result output').innerText();
  await page.getByLabel('Задержка оплаты').fill('60');
  await expect(page.locator('.calc-result output')).not.toHaveText(initialCost);
  await page
    .getByRole('button', { name: 'Нужно сразу подключать 1С и банк?', exact: true })
    .click();
  await expect(page.getByText(/Для начала достаточно выгрузки счетов/)).toBeVisible();
  for (const section of await page.locator('.reveal').all()) await section.scrollIntoViewIfNeeded();
  await page.locator('h1').scrollIntoViewIfNeeded();
  await assertNoHorizontalOverflow(page);
  await page.screenshot({
    path: info.outputPath('landing.png'),
    fullPage: true,
    animations: 'disabled',
  });
  await page.getByRole('link', { name: 'Начать работу', exact: true }).first().click();
  await expect(page.getByLabel('Компания', { exact: true })).toBeVisible();
  await assertNoHorizontalOverflow(page);
});

test('invoice, approved draft, promise, payments and login persist without a fake email send', async ({
  page,
}, info) => {
  const email = await register(page);
  const number = `СЧ-E2E-${Date.now()}`;
  await createInvoice(page, number, '1250.50');
  await page.getByText(number, { exact: true }).first().click();
  const drawer = page.getByRole('dialog', { name: 'Карточка счёта', exact: true });
  await expect
    .poll(() => drawer.evaluate((element) => element.contains(document.activeElement)))
    .toBe(true);
  await page.keyboard.press('Shift+Tab');
  await expect
    .poll(() => drawer.evaluate((element) => element.contains(document.activeElement)))
    .toBe(true);
  await page.getByRole('button', { name: 'Подготовить письмо', exact: true }).click();
  await expect(page.getByRole('button', { name: /Согласовать/ }).first()).toBeVisible();
  await page
    .getByRole('button', { name: /Согласовать/ })
    .first()
    .click();
  // SMTP is deliberately disabled; successful send must never be fabricated.
  await expect(page.locator('.editor-safety')).toContainText(
    'Отправка доступна после подключения почты'
  );
  const send = page.getByRole('button', { name: 'Отправить письмо', exact: true });
  await expect(send).toBeVisible();
  await expect(send).toBeEnabled();
  const sendResponse = page.waitForResponse((response) =>
    /\/api\/messages\/[^/]+\/send$/.test(response.url())
  );
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
  await drawer.evaluate((element) => element.scrollTo({ top: 0 }));
  await page.screenshot({
    path: info.outputPath('drawer.png'),
    fullPage: true,
    animations: 'disabled',
  });
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
  await expect(
    page.getByRole('button', { name: 'Подготовить письмо', exact: true })
  ).toBeDisabled();

  await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).click();
  await page.getByRole('button', { name: 'Профиль и настройки', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Выйти', exact: true }).click();
  await page
    .getByRole('button', { name: /^Войти$/ })
    .first()
    .click();
  await page.getByLabel('Рабочая почта', { exact: true }).fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD);
  await page
    .getByRole('button', { name: /^Войти$/ })
    .last()
    .click();
  await openRegistry(page);
  await expect(page.getByText(number, { exact: true }).first()).toBeVisible();
  await expect(page.locator('.invoice-table')).toContainText('Оплачен');
  await assertNoHorizontalOverflow(page);
  await page.screenshot({
    path: info.outputPath('workspace.png'),
    fullPage: true,
    animations: 'disabled',
  });
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
  await navigate(page, 'Работа');
  await expect(page.getByRole('button', { name: /Открыть дело.*Северные системы/ })).toContainText(
    'ООО Северные системы'
  );
  await expect(
    page.getByRole('button', { name: /Открыть дело.*Северные системы/ })
  ).not.toContainText('Нарушено обещание');
});

test('correcting a contact invalidates the old recipient and persists a fresh draft', async ({
  page,
}) => {
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
  const staleApproval = page.waitForResponse((response) =>
    /\/api\/messages\/[^/]+\/approve$/.test(response.url())
  );
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

test('CSV import previews invalid data, accepts valid rows, and avoids duplicates', async ({
  page,
}) => {
  await register(page);
  await openRegistry(page);
  await page
    .getByRole('button', { name: /Импорт/ })
    .first()
    .click();
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
  await page
    .getByRole('button', { name: /Импорт/ })
    .first()
    .click();
  await page.locator('input[type="file"]').setInputFiles('e2e/fixtures/receivables.csv');
  await expect(page.getByText(/повтор|дубликат|уже существует/i).first()).toBeVisible();
});

test('bank allocation, correction and partial promise preserve cash and debt', async ({
  page,
}, info) => {
  await register(page);
  const number = `FIN-${Date.now()}`;
  await createInvoice(page, number, '1000');
  await navigate(page, 'Финансы');
  await page.getByRole('button', { name: 'Добавить поступление', exact: true }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('ID операции в выписке', { exact: true }).fill(`BANK-${Date.now()}`);
  await dialog.getByLabel('Номер платежа', { exact: true }).fill('ПП-Банк-001');
  await dialog.getByLabel('Сумма поступления, ₽', { exact: true }).fill('600');
  await dialog.getByLabel('Плательщик', { exact: true }).fill('ООО Северные системы');
  await dialog
    .getByLabel('Основание проверки', { exact: true })
    .fill('Сверено с банковской выпиской за текущий день, строка 1');
  await dialog.getByRole('checkbox', { name: 'Сверил поступление с банковской выпиской' }).check();
  await dialog.getByRole('button', { name: 'Сохранить поступление', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: 'Распределить', exact: true }).click();
  dialog = page.getByRole('dialog');
  await selectInvoice(page, number, dialog);
  await dialog.getByLabel('Сумма распределения, ₽', { exact: true }).fill('400');
  await dialog.getByRole('button', { name: 'Распределить сумму', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('.ops-table tbody tr')).toContainText(/400/);
  await page.getByRole('tab', { name: 'Движение по счёту', exact: true }).click();
  await selectInvoice(page, number);
  await expect(page.locator('.ops-ledger-summary')).toContainText(/600/);
  await page.getByRole('button', { name: 'Исправить платёж ПП-Банк-001', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Сумма отмены, ₽', { exact: true }).fill('100');
  await dialog
    .getByLabel('Основание и причина', { exact: true })
    .fill('Ошибка распределения, подтверждено бухгалтером');
  await dialog.getByRole('button', { name: 'Сохранить изменения', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('.ops-ledger-summary')).toContainText(/700/);
  await page.getByRole('button', { name: 'Договорённость', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Обещанная сумма, ₽', { exact: true }).fill('250');
  await dialog.getByLabel('Дата оплаты', { exact: true }).fill(nextWeek);
  await dialog.getByRole('button', { name: 'Сохранить договорённость', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await navigate(page, 'Работа');
  await expect(
    page.locator('.wf-portfolio-sums > div').filter({ hasText: 'Осталось к оплате' })
  ).toContainText(/700/);
  await expect(
    page.locator('.wf-portfolio-sums > div').filter({ hasText: 'Обещано к оплате' })
  ).toContainText(/250/);
  await expect(
    page.locator('.wf-portfolio-sums > div').filter({ hasText: 'Поступило' })
  ).toContainText(/300/);
  await navigate(page, 'Финансы');
  await assertNoHorizontalOverflow(page);
  await page.screenshot({
    path: info.outputPath('finance.png'),
    fullPage: true,
    animations: 'disabled',
  });
});

test('agent inbox fails safely without a provider and never fabricates payment', async ({
  page,
}, info) => {
  await register(page);
  const number = `AGENT-${Date.now()}`;
  await createInvoice(page, number, '1000');
  await navigate(page, 'Агент');
  await page.getByRole('button', { name: 'Разобрать сообщение', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await selectInvoice(page, number, dialog);
  await dialog
    .getByLabel('Новый ответ покупателя', { exact: true })
    .fill('Оплатили 1000 рублей, проверьте поступление.');
  await dialog.getByRole('button', { name: 'Разобрать сообщение', exact: true }).click();
  await expect(dialog).toContainText('Обработка сообщений ещё не подключена');
  await expect(
    dialog.getByRole('button', { name: 'Подтвердить действие', exact: true })
  ).toHaveCount(0);
  await page.keyboard.press('Escape');
  await navigate(page, 'Работа');
  await expect(
    page.locator('.wf-portfolio-sums > div').filter({ hasText: 'Осталось к оплате' })
  ).toContainText(/1\s?000/);
  await expect(
    page.locator('.wf-portfolio-sums > div').filter({ hasText: 'Поступило' })
  ).toContainText('0');
  await navigate(page, 'Агент');
  await assertNoHorizontalOverflow(page);
  await page.screenshot({
    path: info.outputPath('agent.png'),
    fullPage: true,
    animations: 'disabled',
  });
});

test('a failed ledger switch never offers an action on the previous invoice', async ({ page }) => {
  await register(page);
  const first = `RACE-A-${Date.now()}`,
    second = `RACE-B-${Date.now()}`;
  await createInvoice(page, first, '1000');
  await createInvoice(page, second, '2000');
  await navigate(page, 'Финансы');
  await page.getByRole('tab', { name: 'Движение по счёту', exact: true }).click();
  await selectInvoice(page, first);
  await expect(page.locator('.ops-ledger-summary')).toContainText(/1\s?000/);
  const select = page.getByRole('combobox', { name: 'Счёт', exact: true });
  const id = await select.locator('option').filter({ hasText: second }).getAttribute('value');
  await page.route(`**/api/finance/invoices/${id}/ledger`, (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Сверка временно недоступна' }),
    })
  );
  await selectInvoice(page, second);
  await expect(page.getByRole('alert')).toContainText('Сверка временно недоступна');
  await expect(page.locator('.ops-ledger-summary')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Изменить требование', exact: true })).toHaveCount(
    0
  );
});

test('reconciliation shows a derived balance and a settled invoice accepts a reasoned additional charge', async ({
  page,
}) => {
  await register(page);
  const number = `RECON-${Date.now()}`;
  await createInvoice(page, number, '1000');
  await navigate(page, 'Финансы');
  await page.getByRole('tab', { name: 'Сверка реестра', exact: true }).click();
  const source = page.getByLabel('Данные реестра', { exact: true });
  await source.fill(
    `контрагент;инн;email;номер;дата;срок;сумма\nООО Северные системы;7701234567;ap@example.ru;${number};01.10.2026;15.10.2026;2000`
  );
  let release: undefined | (() => void);
  await page.route('**/api/finance/imports/preview', async (route) => {
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.continue();
  });
  try {
    await page.getByRole('button', { name: 'Проверить изменения', exact: true }).click();
    await expect.poll(() => Boolean(release)).toBe(true);
    // Match the same control directly while its ancestor fieldset is disabled.
    // Chromium/Playwright changes the implicit label lookup in this state.
    await expect(page.locator('.ops-input-group textarea.ops-csv')).toBeDisabled();
  } finally {
    release?.();
  }
  await expect(page.locator('.ops-preview tbody td:last-child')).toHaveText(/2\s?000\s?₽/);
  await page
    .getByLabel('Основание сверки', { exact: true })
    .fill('Уточнена исходная сумма по первичным документам');
  await page.getByLabel('Проверил суммы, оплаты и изменения реестра', { exact: true }).check();
  await page.getByRole('button', { name: 'Подтвердить сверку', exact: true }).click();
  await expect(page.locator('.ops-preview')).toHaveCount(0);
  const session = await (await page.request.get('/api/auth/me')).json();
  const items = await (await page.request.get('/api/invoices')).json();
  const invoice = items.items.find((item: { number: string }) => item.number === number);
  expect(invoice.amount).toBe(200000);
  const paid = await page.request.post(`/api/invoices/${invoice.id}/payments`, {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: { amount: 200000, paid_on: today, reference: 'SETTLED-RECON' },
  });
  expect(paid.status()).toBe(200);
  await page.getByRole('button', { name: 'Обновить данные', exact: true }).click();
  await page.getByRole('tab', { name: 'Движение по счёту', exact: true }).click();
  await selectInvoice(page, number);
  await expect(
    page.getByRole('button', { name: 'Изменить требование', exact: true })
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Изменить требование', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('combobox', { name: 'Основание', exact: true })).toHaveValue(
    'debit'
  );
  await dialog.getByLabel('Сумма изменения, ₽', { exact: true }).fill('100');
  await dialog
    .getByLabel('Документ и причина', { exact: true })
    .fill('Подтверждённое дополнительное начисление по соглашению сторон');
  await dialog.getByRole('button', { name: 'Сохранить изменения', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('.ops-ledger-summary')).toContainText(/100\s?₽/);
});
