import { test, expect } from './fixtures';

const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(new Date());

test('portfolio audit ties documents, deadlines and payment to immutable reports', async ({
  page,
}, info) => {
  const registered = await page.request.post('/api/auth/register', {
    data: {
      company: 'Поставщик',
      name: 'Финансист',
      email: `portfolio-${Date.now()}-${info.project.name}@example.ru`,
      password: 'Mandato-portfolio-2026!',
    },
  });
  expect(registered.status()).toBe(201);
  const { csrf_token } = await registered.json();
  const headers = { 'X-CSRF-Token': csrf_token };
  const response = await page.request.post('/api/invoices', {
    headers,
    data: {
      company: 'ООО Портфель',
      inn: '7701234567',
      number: 'AUDIT-42',
      issued_on: day,
      due_on: day,
      amount: 100000,
    },
  });
  expect(response.status()).toBe(201);
  const inv = await response.json();
  await page.goto('/app');
  await page.getByRole('button', { name: 'Аудит', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Аудит дебиторки', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Собрать аудит', exact: true }).click();
  const row = page.locator('.portfolio-row').filter({ hasText: 'AUDIT-42' });
  await expect(row).toContainText('Проверить должника');
  await row.click();
  await expect(page.getByRole('heading', { name: 'Нет договора', exact: true })).toBeVisible();
  await expect(
    page.getByText('Регистрация должника: нужна актуальная проверка', { exact: true })
  ).toBeVisible();
  await expect(
    page.getByText(/Судебные дела, исполнительные производства и полный реестр банкротств/)
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath('portfolio.png'),
    fullPage: true,
    animations: 'disabled',
  });
  await page.getByRole('combobox', { name: 'Вид документа', exact: true }).selectOption('contract');
  await page
    .getByLabel('Номер, название или ссылка на архив', { exact: true })
    .fill('Договор №42: архив бухгалтерии');
  await page.getByRole('button', { name: 'Сохранить документ', exact: true }).click();
  await expect(page.getByText('Договор №42: архив бухгалтерии', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Нет договора', exact: true })).toHaveCount(0);
  await page
    .getByRole('combobox', { name: 'Что проверить', exact: true })
    .selectOption('court_review');
  await page.getByLabel('Дата проверки', { exact: true }).fill(day);
  await page
    .getByLabel('Основание и поручение', { exact: true })
    .fill('Юрист проверяет комплект перед дальнейшей работой');
  await page.getByRole('button', { name: 'Назначить проверку', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Назначен срок юридической проверки', exact: true })
  ).toBeVisible();
  await page
    .getByLabel('Результат проверки', { exact: true })
    .fill('Юрист проверил комплект, срок контроля завершён');
  await page.getByRole('button', { name: 'Завершить проверку', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Назначен срок юридической проверки', exact: true })
  ).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Скачать отчёт', exact: true })).toHaveAttribute(
    'href',
    /\/api\/portfolio\/runs\/.+\/export/
  );
  const paid = await page.request.post(`/api/invoices/${inv.id}/payments`, {
    headers,
    data: { amount: 100000, paid_on: day, reference: 'AUDIT-PAID' },
  });
  expect(paid.status()).toBe(200);
  await page.reload();
  await page.getByRole('button', { name: 'Аудит', exact: true }).click();
  await expect(page.getByText('Портфель изменился после проверки', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Обновить аудит', exact: true }).click();
  await expect(page.locator('.portfolio-row').filter({ hasText: 'AUDIT-42' })).toContainText(
    'Оплата отражена'
  );
  await expect(
    page.getByRole('combobox', { name: 'История аудитов', exact: true }).locator('option')
  ).not.toHaveCount(0);
});

test('OSV-only portfolio remains visible and does not invent an invoice', async ({
  page,
}, info) => {
  const registered = await page.request.post('/api/auth/register', {
    data: {
      company: 'Оптовик',
      name: 'Бухгалтер',
      email: `portfolio-osv-${Date.now()}-${info.project.name}@example.ru`,
      password: 'Mandato-OSV-2026!',
    },
  });
  const { csrf_token } = await registered.json();
  const headers = { 'X-CSRF-Token': csrf_token };
  const preview = await page.request.post('/api/accounting/preview', {
    headers,
    data: {
      source_type: 'reconciliation_act',
      source_ref: 'Сверка №9',
      as_of: day,
      format: 'csv',
      content: 'Контрагент;ИНН;Дебет;Кредит\nООО Источник;7801234567;25000;0\n',
      mapping: {
        company: 'Контрагент',
        inn: 'ИНН',
        ending_debit: 'Дебет',
        ending_credit: 'Кредит',
      },
    },
  });
  expect(preview.status()).toBe(200);
  const p = await preview.json();
  expect(
    (
      await page.request.post(`/api/accounting/imports/${p.id}/approve`, {
        headers,
        data: { reason: 'Сверено бухгалтером по источнику', selected_rows: [2] },
      })
    ).status()
  ).toBe(200);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Аудит', exact: true }).click();
  await page.getByRole('button', { name: 'Собрать аудит', exact: true }).click();
  await expect(
    page.getByText('Сальдо без документов обязательства', { exact: true })
  ).toBeVisible();
  await expect(page.getByText(/ООО Источник: в принятом источнике/)).toBeVisible();
  expect((await (await page.request.get('/api/invoices')).json()).items).toHaveLength(0);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 2
  );
  expect(overflow).toBe(false);
});

test('unsaved document stays scoped to its invoice and survives report refresh with a file warning', async ({
  page,
}, info) => {
  const registered = await page.request.post('/api/auth/register', {
    data: {
      company: 'Поставщик документов',
      name: 'Бухгалтер',
      email: `portfolio-files-${Date.now()}-${info.project.name}@example.ru`,
      password: 'Mandato-file-scope-2026!',
    },
  });
  expect(registered.status()).toBe(201);
  const headers = { 'X-CSRF-Token': (await registered.json()).csrf_token };
  const invoices = [];
  for (const number of ['FILE-A', 'FILE-B']) {
    const response = await page.request.post('/api/invoices', {
      headers,
      data: {
        company: 'ООО Документы',
        inn: '7707083893',
        number,
        issued_on: day,
        due_on: day,
        amount: 100000,
      },
    });
    expect(response.status()).toBe(201);
    invoices.push(await response.json());
  }
  await page.goto('/app');
  await page.getByRole('button', { name: 'Аудит', exact: true }).click();
  await page.getByRole('button', { name: 'Собрать аудит', exact: true }).click();
  await page.locator('.portfolio-row').filter({ hasText: 'FILE-A' }).click();
  await page.getByLabel('Файл документа').evaluate((element) => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File(['%PDF-1.4\nA invoice evidence\n%%EOF'], 'contract-for-A.pdf', {
        type: 'application/pdf',
      })
    );
    (element as HTMLInputElement).files = transfer.files;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  });
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.locator('.portfolio-row').filter({ hasText: 'FILE-B' }).click();
  expect(
    await page
      .getByLabel('Файл документа')
      .evaluate((element) => (element as HTMLInputElement).files?.length)
  ).toBe(1);
  page.once('dialog', (dialog) => dialog.accept());
  await page.locator('.portfolio-row').filter({ hasText: 'FILE-B' }).click();
  await expect
    .poll(() =>
      page
        .getByLabel('Файл документа')
        .evaluate((element) => (element as HTMLInputElement).files?.length)
    )
    .toBe(0);
  await page
    .getByLabel('Номер, название или ссылка на архив', { exact: true })
    .fill('Реквизиты договора только для FILE-B');
  await page.getByRole('button', { name: 'Сохранить документ', exact: true }).click();
  await expect(
    page.getByText('Реквизиты договора только для FILE-B', { exact: false })
  ).toBeVisible();
  const saved = await page.request.get(`/api/portfolio/invoices/${invoices[1].id}/evidence`);
  expect((await saved.json()).items[0].filename).toBe('');
  const original = await page.request.get(`/api/portfolio/invoices/${invoices[0].id}/evidence`);
  expect((await original.json()).items).toHaveLength(0);
  await page.getByLabel('Файл документа').evaluate((element) => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File(['%PDF-1.4\nunsaved old report evidence\n%%EOF'], 'old-report.pdf', {
        type: 'application/pdf',
      })
    );
    (element as HTMLInputElement).files = transfer.files;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page
    .getByLabel('Номер, название или ссылка на архив', { exact: true })
    .fill('Не сохранено в прежнем отчёте');
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Обновить аудит', exact: true }).click();
  await expect(page.getByLabel('Номер, название или ссылка на архив', { exact: true })).toHaveValue(
    'Не сохранено в прежнем отчёте'
  );
  await expect
    .poll(() =>
      page
        .getByLabel('Файл документа')
        .evaluate((element) => (element as HTMLInputElement).files?.length)
    )
    .toBe(0);
});
