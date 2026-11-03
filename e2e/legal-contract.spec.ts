import { test, expect, navigate } from './fixtures';

test('a lawyer opens one contract claim and scopes an act to its actual invoice', async ({
  page,
}, info) => {
  const registration = await page.request.post('/api/auth/register', {
    data: {
      name: 'Анна',
      company: 'Поставщик',
      email: `contract-${info.project.name}-${Date.now()}@example.ru`,
      password: 'Mandato-contract-2026!',
    },
  });
  expect(registration.status()).toBe(201);
  const session = await registration.json();
  const headers = { 'X-CSRF-Token': session.csrf_token };
  const invoices = [];
  for (const [number, amount] of [
    ['Д-101', 5000000],
    ['Д-102', 10000000],
  ] as const) {
    const r = await page.request.post('/api/invoices', {
      headers,
      data: {
        company: 'ООО Покупатель',
        inn: '7701234567',
        number,
        amount,
        issued_on: '2026-10-01',
        due_on: '2026-10-15',
      },
    });
    expect(r.status()).toBe(201);
    invoices.push(await r.json());
  }
  const contract = await page.request.post('/api/workflow/contracts', {
    headers,
    data: {
      counterparty_id: invoices[0].counterparty_id,
      number: 'П-12',
      invoice_ids: invoices.map((i) => i.id),
    },
  });
  expect(contract.status()).toBe(201);
  await page.goto('/app');
  await navigate(page, 'Претензии и суд');
  await page.getByRole('button', { name: 'Новое дело', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Новое юридическое дело', exact: true });
  await dialog.getByRole('combobox', { name: 'Счёт', exact: true }).selectOption(invoices[0].id);
  const extra = dialog.getByRole('checkbox', { name: /Д-102/ });
  await expect(extra).not.toBeChecked();
  await extra.check();
  await dialog.getByRole('button', { name: 'Открыть дело', exact: true }).click();
  await expect(page.locator('.ops-context')).toContainText('150 000');
  await expect(page.locator('.ops-context')).toContainText('Д-101, Д-102');
  await expect(page.locator('.work-context-bar')).toHaveCount(0);
  await page.getByLabel('Ответственный юрист', { exact: true }).fill('Елена Петрова');
  await page.getByLabel('Полномочия юриста', { exact: true }).fill('Договор сопровождения П-12');
  await page.getByRole('button', { name: 'Сохранить факты', exact: true }).click();
  await expect(page.getByText('Факты сохранены', { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Доказательства', exact: true }).click();
  await page.getByLabel('Вид доказательства', { exact: true }).selectOption('performance');
  await page.getByLabel('Название доказательства', { exact: true }).fill('Акт по первому счёту');
  await expect(
    page.getByLabel('Документ подтверждает все счета этого дела', { exact: true })
  ).not.toBeChecked();
  await page.getByLabel('Д-101', { exact: true }).check();
  await page.getByLabel('Номер, ссылка или место хранения', { exact: true }).fill('Акт А-101');
  await page.getByRole('button', { name: 'Зарегистрировать доказательство', exact: true }).click();
  await expect(page.getByText('Доказательство зарегистрировано', { exact: true })).toBeVisible();
  const id = new URL(page.url()).searchParams.get('legal');
  const saved = await (await page.request.get(`/api/legal/cases/${id}`)).json();
  expect(saved.facts.responsible_lawyer).toBe('Елена Петрова');
  expect(saved.evidence[0].invoice_ids).toEqual([invoices[0].id]);
  expect(saved.invoice_count).toBe(2);
  await navigate(page, 'Переписка');
  await expect(
    page.getByRole('combobox', { name: 'Текущая задолженность', exact: true })
  ).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Счёт', exact: true })).toHaveCount(1);
  await page.screenshot({ path: info.outputPath('contract-evidence.png'), fullPage: true });
});
