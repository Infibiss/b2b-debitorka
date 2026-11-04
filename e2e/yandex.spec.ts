import { test, expect, navigate, type Page } from './fixtures';

async function setup(page: Page, suffix: string) {
  const response = await page.request.post('/api/auth/register', {
    data: {
      name: 'Руководитель',
      company: 'Поставщик',
      email: `yandex-ui-${suffix}-${Date.now()}@example.ru`,
      password: 'Yandex-Mandato-2026!',
    },
  });
  const session = await response.json();
  const result = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      company: 'Покупатель',
      number: 'YX-42',
      issued_on: '2026-01-01',
      due_on: '2026-02-01',
      amount: 125050,
    },
  });
  expect(result.status()).toBe(201);
  return result.json();
}

test('document and voice tools explain missing access without fabricating results', async ({
  page,
}, info) => {
  await setup(page, info.project.name);
  await page.goto('/app');
  await navigate(page, 'Документы и голос');
  await expect(page.getByRole('heading', { name: 'Распознавание документов' })).toBeVisible();
  await expect(page.getByLabel('Загрузить документ для распознавания')).toBeDisabled();
  await navigate(page, 'Переписка');
  await page.getByRole('button', { name: 'Звонки', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Звонок по счёту' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Позвонить', exact: true })).toBeDisabled();
  await expect(page.getByText('Нужно подключить телефонию', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Учебный разговор', exact: true })).toHaveCount(0);
  expect((await (await page.request.get('/api/invoices')).json()).items[0].balance).toBe(125050);
});

test('document upload keeps the selected file visible and recognition has one page title', async ({
  page,
}, info) => {
  const inv = await setup(page, `archive-${info.project.name}`);
  await page.goto('/app');
  await navigate(page, 'Документы');
  await page.getByRole('combobox', { name: 'Счёт', exact: true }).selectOption(inv.id);
  await page.getByLabel('Номер, название или ссылка на архив', { exact: true }).fill('Договор №42');
  await page
    .getByLabel('Файл документа', { exact: true })
    .setInputFiles('e2e/fixtures/ocr-contract.png');
  await expect(page.getByRole('status').filter({ hasText: 'ocr-contract.png' })).toBeVisible();
  await page.getByRole('button', { name: 'Добавить документ', exact: true }).click();
  await expect(page.locator('.documents-archive')).toContainText('Договор №42');
  await expect(
    page.locator('.documents-archive').getByRole('link', { name: 'Скачать файл' })
  ).toBeVisible();
  await expect(page.locator('.documents-filename')).toHaveCount(0);
  await page.getByRole('button', { name: 'Распознавание', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  await expect(page.locator('.yx-connection-missing')).toBeVisible();
  await expect(page.getByLabel('Загрузить документ для распознавания')).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2)).toBe(
    false
  );
});

test('OCR acceptance and voice preparation stop at the real connection boundary', async ({
  page,
}, info) => {
  const inv = await setup(page, `contract-${info.project.name}`);
  let recognizedDocument: Record<string, unknown> | null = null;
  const status = {
    configured: true,
    status: 'not_checked',
    message: 'Проверка подключения',
    required_roles: [],
  };
  await page.route('**/api/yandex/status', (route) =>
    route.fulfill({ json: { ocr: status, voice: status } })
  );
  await page.route('**/api/yandex/documents', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      expect(body.invoice_id).toBe(inv.id);
      expect(body.mime_type).toBe('image/png');
      recognizedDocument = {
        id: 'ocr-ui',
        filename: body.filename,
        invoice_id: inv.id,
        status: 'completed',
        error_code: '',
        text: 'Договор №42',
        page_count: 1,
        source_hash: 'a'.repeat(64),
        acceptance: null,
      };
      await route.fulfill({ json: recognizedDocument });
    } else await route.fulfill({ json: { items: recognizedDocument ? [recognizedDocument] : [] } });
  });
  await page.route('**/api/yandex/documents/ocr-ui/accept', async (route) => {
    const body = route.request().postDataJSON();
    expect(body.fields.number).toBe('42');
    recognizedDocument = { ...recognizedDocument, acceptance: body };
    await route.fulfill({ json: recognizedDocument });
  });
  await page.goto('/app');
  await navigate(page, 'Документы и голос');
  await page.getByLabel('Счёт для документа', { exact: true }).selectOption(inv.id);
  await page
    .getByLabel('Загрузить документ для распознавания')
    .setInputFiles('e2e/fixtures/ocr-contract.png');
  await expect(page.getByLabel('Распознанный текст — исправьте ошибки')).toHaveValue('Договор №42');
  await page.getByLabel('Проверенный номер документа').fill('42');
  await page.getByLabel('Что проверено по оригиналу').fill('Сверено бухгалтером');
  await page.getByRole('button', { name: 'Сохранить проверенную версию' }).click();
  await expect(page.getByText('Проверенная версия сохранена.', { exact: true })).toBeVisible();
  await navigate(page, 'Переписка');
  await page.getByRole('button', { name: 'Звонки', exact: true }).click();
  await page.getByLabel('Счёт для звонка', { exact: true }).selectOption(inv.id);
  await page.getByLabel('Телефон контрагента', { exact: true }).fill('+7 (999) 123-45-67');
  await page
    .getByRole('checkbox', {
      name: 'Номер принадлежит представителю контрагента, полномочия на контакт проверены',
    })
    .check();
  const prepared = page.waitForResponse('**/api/yandex/voice/calls/prepare');
  await page.getByRole('button', { name: 'Позвонить', exact: true }).click();
  const preparation = await (await prepared).json();
  expect(preparation.status).toBe('connection_required');
  expect(preparation.call_started).toBe(false);
  expect(preparation.phone).toBe('+79991234567');
  expect(preparation).not.toHaveProperty('call_id');
  await expect(page.getByText('Звонок не начат', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Скопировать задание на подключение' })
  ).toBeVisible();
  await expect(page.getByText('Это разговор в браузере', { exact: false })).toHaveCount(0);
  expect(
    (await (await page.request.get('/api/yandex/voice/turns?invoice_id=' + inv.id)).json()).items
  ).toHaveLength(0);
  expect((await (await page.request.get('/api/invoices')).json()).items[0].balance).toBe(125050);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2)).toBe(
    false
  );
  await page.screenshot({ path: info.outputPath('documents-voice.png'), fullPage: true });
});
