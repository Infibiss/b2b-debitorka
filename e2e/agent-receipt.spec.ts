import { navigate, expect, test } from './fixtures';

// The input belongs to the browser's timezone, independently of the business date.
test.use({ timezoneId: 'Asia/Vladivostok' });

test('manual agent intake persists the explicit receipt time and shows it after reload', async ({
  page,
}, info) => {
  const response = await page.request.post('/api/auth/register', {
    data: {
      company: 'ООО Проверка времени',
      name: 'Оператор',
      email: `receipt-${Date.now()}-${info.project.name}@example.invalid`,
      password: 'Receipt-browser-2026!',
    },
  });
  expect(response.status()).toBe(201);
  const session = await response.json();
  const added = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      company: 'Синтетический покупатель',
      number: `RECEIPT-${Date.now()}`,
      issued_on: '2026-10-01',
      due_on: '2026-10-15',
      amount: 100_000,
    },
  });
  expect(added.status()).toBe(201);
  const invoice = await added.json();
  await page.goto('/app');
  await navigate(page, 'Агент');
  await page.getByRole('button', { name: 'Разобрать сообщение', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Ответ покупателя', exact: true });
  const receipt = dialog.getByLabel('Дата и время получения ответа', { exact: true });
  await expect(receipt).toHaveAttribute('type', 'datetime-local');
  await expect(receipt).toHaveAttribute('required', '');
  await expect(receipt).toHaveValue(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  await expect(dialog).toContainText('Сроки вроде «завтра» считаются от даты получения.');
  await expect(dialog).toContainText('Asia/Vladivostok');
  await receipt.fill('2026-10-23T23:45');
  await dialog.getByRole('combobox', { name: 'Счёт', exact: true }).selectOption(invoice.id);
  await dialog
    .getByLabel('Новый ответ покупателя', { exact: true })
    .fill('Обещаем оплатить 300 рублей завтра.');
  const submitted = page.waitForResponse(
    (r) => r.url().endsWith('/api/agent/ingest') && r.request().method() === 'POST'
  );
  await dialog.getByRole('button', { name: 'Разобрать сообщение', exact: true }).click();
  const ingested = await submitted;
  expect(ingested.status()).toBe(201);
  const proposal = await ingested.json();
  expect(new Date(proposal.received_at).toISOString()).toBe('2026-10-23T13:45:00.000Z');
  // The real isolated E2E server has no Yandex credentials. No model or response is mocked.
  expect(proposal.status).toBe('handoff');
  expect(proposal.reasons).toContain('provider_unconfigured');
  await expect(page.getByRole('dialog').locator('time')).toContainText('23:45');
  const stored = await page.request.get(`/api/agent/proposals/${proposal.id}`);
  expect(stored.status()).toBe(200);
  expect(new Date((await stored.json()).received_at).toISOString()).toBe(
    '2026-10-23T13:45:00.000Z'
  );
  await page.reload();
  await navigate(page, 'Агент');
  await page
    .locator('.ops-proposal-row')
    .filter({ hasText: 'Обещаем оплатить 300 рублей завтра.' })
    .click();
  await expect(page.getByRole('dialog').locator('time')).toHaveAttribute(
    'datetime',
    proposal.received_at
  );
  await expect(page.getByRole('dialog').locator('time')).toContainText('23:45');
  await expect(page.getByRole('button', { name: 'Подтвердить действие', exact: true })).toHaveCount(
    0
  );
});
