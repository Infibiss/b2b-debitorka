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
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await page.getByRole('button', { name: 'Учебный разговор', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Начать разговор', exact: true })).toBeDisabled();
  await expect(page.getByText('Нужно подключение', { exact: true })).toHaveCount(2);
  expect((await (await page.request.get('/api/invoices')).json()).items[0].balance).toBe(125050);
});

test('provider-contract UI renders OCR acceptance and a voice exchange without touching money', async ({
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
  await page.route('**/api/yandex/voice/turns?*', (route) =>
    route.fulfill({ json: { items: [] } })
  );
  await page.route('**/api/yandex/voice/text', async (route) => {
    const body = route.request().postDataJSON();
    expect(body.identity_confirmed).toBe(true);
    await route.fulfill({
      json: {
        id: 'voice-ui',
        status: 'completed',
        transcript: body.text,
        reply: 'Уточните дату, сумму и номер платёжного поручения. Мы сверим поступление.',
        audio: '',
        audio_mime: 'audio/ogg',
        error_code: '',
      },
    });
  });
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
      value: async () => {
        throw new DOMException('Permission denied', 'NotAllowedError');
      },
    });
  });
  await page.goto('/app');
  await navigate(page, 'Документы и голос');
  await page.getByLabel('Счёт для документов и диалога').selectOption(inv.id);
  await page
    .getByLabel('Загрузить документ для распознавания')
    .setInputFiles('e2e/fixtures/ocr-contract.png');
  await expect(page.getByLabel('Распознанный текст — исправьте ошибки')).toHaveValue('Договор №42');
  await page.getByLabel('Проверенный номер документа').fill('42');
  await page.getByLabel('Что проверено по оригиналу').fill('Сверено бухгалтером');
  await page.getByRole('button', { name: 'Сохранить проверенную версию' }).click();
  await expect(page.getByText('Проверенная версия сохранена.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await page.getByRole('button', { name: 'Учебный разговор', exact: true }).click();
  await page.getByRole('dialog').getByLabel('Счёт для документов и диалога').selectOption(inv.id);
  await page.getByRole('dialog').getByRole('checkbox').check();
  await page.getByLabel('Или введите реплику').fill('Мы оплатили вчера');
  await page.getByRole('button', { name: 'Ответить Mandato', exact: true }).click();
  await expect(page.getByLabel('История диалога')).toContainText('номер платёжного поручения');
  await page.getByRole('button', { name: 'Начать запись', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Доступ к микрофону не разрешён');
  expect((await (await page.request.get('/api/invoices')).json()).items[0].balance).toBe(125050);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2)).toBe(
    false
  );
  await page.screenshot({ path: info.outputPath('documents-voice.png'), fullPage: true });
});
