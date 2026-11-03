import { test, expect, navigate, type Page } from './fixtures';

async function seed(page: Page, name: string) {
  const response = await page.request.post('/api/auth/register', {
    data: {
      company: 'Поставщик',
      name: 'Анна',
      email: `ux-${name}-${Date.now()}@example.ru`,
      password: 'Mandato-ux-2026!',
    },
  });
  expect(response.status()).toBe(201);
  const session = await response.json();
  const headers = { 'X-CSRF-Token': session.csrf_token };
  const added = await page.request.post('/api/invoices', {
    headers,
    data: {
      company: 'Северстрой',
      inn: '7701234567',
      email: 'buyer@example.ru',
      number: 'СЧ-101',
      issued_on: '2026-08-01',
      due_on: '2026-09-01',
      amount: 18000000,
    },
  });
  expect(added.status()).toBe(201);
  const invoice = await added.json();
  const contract = await page.request.post('/api/workflow/contracts', {
    headers,
    data: {
      counterparty_id: invoice.counterparty_id,
      number: 'П-12/2026',
      invoice_ids: [invoice.id],
    },
  });
  expect(contract.status()).toBe(201);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Позже', exact: true }).click();
  return { invoice, headers, session };
}

test('case navigation carries invoice, legal prefill, drafts and deep links', async ({
  page,
}, info) => {
  const { invoice, headers } = await seed(page, info.project.name);
  await page.getByRole('button', { name: /Открыть дело Северстрой/ }).click();
  await page.getByRole('button', { name: 'Условия и согласования', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Счёт', exact: true })).toHaveValue(invoice.id);
  expect(new URL(page.url()).searchParams.get('context')).toBe(invoice.id);
  await page.reload();
  await expect(page.getByRole('combobox', { name: 'Счёт', exact: true })).toHaveValue(invoice.id);
  await page.getByRole('button', { name: 'Вернуться к делу', exact: true }).click();
  const caseDialog = page.getByRole('dialog', { name: 'Карточка дела', exact: true });
  await caseDialog.getByRole('tab', { name: 'Финансовый реестр', exact: true }).click();
  await caseDialog
    .getByRole('button', { name: 'Проверить поступления и распределение', exact: true })
    .click();
  expect(new URL(page.url()).searchParams.get('financeTab')).toBe('ledger');
  await expect(page.getByRole('combobox', { name: 'Счёт', exact: true })).toHaveValue(invoice.id);
  await page.getByRole('button', { name: 'Вернуться к делу', exact: true }).click();
  await caseDialog.getByRole('tab', { name: 'Документы', exact: true }).click();
  await caseDialog
    .getByRole('button', { name: 'Добавить договор или документ', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Добавить договор или документ', exact: true })
  ).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Счёт', exact: true })).toHaveValue(invoice.id);
  await navigate(page, 'Претензии и суд');
  await page.getByRole('button', { name: 'Новое дело', exact: true }).click();
  await expect(
    page.getByRole('dialog').getByRole('combobox', { name: 'Счёт', exact: true })
  ).toHaveValue(invoice.id);
  await page.getByRole('button', { name: 'Открыть дело', exact: true }).click();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue('П-12/2026');
  await page.getByLabel('Номер договора', { exact: true }).fill('Несохранённый договор 42');
  await page.getByLabel('Долг возник в предпринимательской деятельности', { exact: true }).check();
  await expect(page.getByText(/Черновик сохранён в этой вкладке/)).toBeVisible();
  await expect(page.getByText('Данные сохранены', { exact: true })).toHaveCount(0);
  await page.getByRole('tab', { name: 'Расчёт', exact: true }).click();
  await page.getByRole('tab', { name: 'Факты', exact: true }).click();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue(
    'Несохранённый договор 42'
  );
  await expect(
    page.getByLabel('Долг возник в предпринимательской деятельности', { exact: true })
  ).toBeChecked();
  const legalUrl = page.url();
  page.on('dialog', (dialog) => dialog.accept());
  await page.reload();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue(
    'Несохранённый договор 42'
  );
  await navigate(page, 'Подключения');
  await page.reload();
  expect(new URL(page.url()).searchParams.get('section')).toBe('connections');
  await page.goBack();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue(
    'Несохранённый договор 42'
  );
  const cases = await (await page.request.get('/api/legal/cases', { headers })).json();
  expect(cases.items[0].facts.contract_number).toBe('П-12/2026');
  await page.screenshot({ path: info.outputPath('facts-draft.png') });
  expect(legalUrl).toContain('legal=');
});

test('documents are added directly and mail setup request survives reload', async ({
  page,
}, info) => {
  const { invoice } = await seed(page, `documents-${info.project.name}`);
  await navigate(page, 'Документы');
  await page.getByRole('combobox', { name: 'Счёт', exact: true }).selectOption(invoice.id);
  await page
    .getByLabel('Номер, название или ссылка на архив', { exact: true })
    .fill('Договор поставки П-12/2026');
  await page.getByRole('button', { name: 'Добавить документ', exact: true }).click();
  await expect(page.locator('.portfolio-document')).toContainText('Договор поставки П-12/2026');
  await navigate(page, 'Подключения');
  await page.getByRole('button', { name: 'Почта', exact: true }).click();
  await page
    .getByLabel('Почта для отправки писем покупателям', { exact: true })
    .fill('billing@example.ru');
  await page.getByRole('button', { name: 'Оставить заявку на подключение', exact: true }).click();
  await expect(page.getByText(/Ожидает администратора/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Ожидает администратора/)).toBeVisible();
  await page.screenshot({ path: info.outputPath('mail-setup.png'), fullPage: true });
});

test('login recovery uses the same layout and explains unavailable service without support dropdown', async ({
  page,
}) => {
  await page.goto('/app?mode=login');
  await page.getByRole('button', { name: 'Забыли пароль?', exact: true }).click();
  await page.getByLabel('Email аккаунта', { exact: true }).fill('someone@example.ru');
  await page.getByRole('button', { name: 'Получить ссылку', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Сервис восстановления пока не подключён');
  await expect(page.getByText(/Для помощи со входом обратитесь к администратору/)).toBeVisible();
  await expect(page.locator('.support-contact summary')).toHaveCount(0);
  await expect(page.locator('.recovery-page .auth-aside')).toHaveCount(1);
  await page.getByRole('button', { name: 'Вернуться ко входу', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Войти в Mandato', exact: true })).toBeVisible();
});

test('390px work queue starts in the first viewport and operations remain accessible', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await seed(page, `mobile-${info.project.name}`);
  const card = page.getByRole('button', { name: /Открыть дело Северстрой/ });
  await expect(card).toBeVisible();
  const box = await card.boundingBox();
  expect(box!.y).toBeLessThan(760);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({ path: info.outputPath('mobile-work.png'), fullPage: true });
  await navigate(page, 'Документы');
  await expect(
    page.getByRole('heading', { name: 'Добавить договор или документ', exact: true })
  ).toBeVisible();
});

test('failed save keeps a draft; successful save clears it and logout asks before discarding', async ({
  page,
}, info) => {
  const { invoice, headers } = await seed(page, `failure-${info.project.name}`);
  const response = await page.request.post('/api/legal/cases', {
    headers,
    data: {
      invoice_id: invoice.id,
      facts: {
        creditor: {
          name: 'Поставщик',
          inn: '7801234567',
          ogrn: '1027800000001',
          address: 'Адрес кредитора',
          bank_details: 'Реквизиты кредитора',
        },
        debtor: {
          name: 'Северстрой',
          inn: '7701234567',
          ogrn: '1027700000001',
          address: 'Адрес должника',
        },
        contract_date: '2026-07-01',
        obligation_description: 'Оплата оборудования',
        performance_description: 'Товар передан по УПД',
        due_basis: 'По договору',
        legal_basis: 'По договору и закону',
      },
    },
  });
  expect(response.status()).toBe(201);
  const legal = await response.json();
  await page.goto(`/app?section=legal&legal=${legal.id}`);
  await page.getByLabel('Номер договора', { exact: true }).fill('Изменённый договор');
  await page.route(`**/api/legal/cases/${legal.id}`, async (route) => {
    if (route.request().method() === 'PATCH')
      await route.fulfill({ status: 503, json: { detail: 'Временный отказ сохранения' } });
    else await route.continue();
  });
  await page.getByRole('button', { name: 'Сохранить факты', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Временный отказ сохранения');
  await page.getByRole('tab', { name: 'Расчёт', exact: true }).click();
  await page.getByRole('tab', { name: 'Факты', exact: true }).click();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue(
    'Изменённый договор'
  );
  await page.unroute(`**/api/legal/cases/${legal.id}`);
  await page.getByRole('button', { name: 'Сохранить факты', exact: true }).click();
  await expect(page.getByText('Факты сохранены', { exact: true })).toBeVisible();
  expect(
    await page.evaluate(() =>
      Object.keys(sessionStorage).filter((key) => key.startsWith('mandato:draft:'))
    )
  ).toHaveLength(0);
  await page.reload();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue(
    'Изменённый договор'
  );
  await page.getByLabel('Номер договора', { exact: true }).fill('Отменяемый черновик');
  await page.getByRole('button', { name: 'Все поля', exact: true }).click();
  await page
    .getByRole('combobox', { name: 'Тип должника', exact: true })
    .selectOption('sole_proprietor');
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Отменить изменения', exact: true }).click();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue(
    'Изменённый договор'
  );
  expect(
    await page.evaluate(() =>
      Object.keys(sessionStorage).filter((key) => key.startsWith('mandato:draft:'))
    )
  ).toHaveLength(0);
  await expect(page.getByRole('combobox', { name: 'Тип должника', exact: true })).toHaveValue(
    'organization'
  );
  await page.getByLabel('Номер договора', { exact: true }).fill('Последний черновик');
  await page.getByRole('button', { name: 'Профиль и настройки', exact: true }).click();
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('menuitem', { name: 'Выйти', exact: true }).click();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue(
    'Последний черновик'
  );
  await page.getByRole('button', { name: 'Профиль и настройки', exact: true }).click();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('menuitem', { name: 'Выйти', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Забыли пароль?', exact: true })).toBeVisible();
  expect(
    await page.evaluate(() =>
      Object.keys(sessionStorage).filter((key) => key.startsWith('mandato:draft:'))
    )
  ).toHaveLength(0);
});

test('conditional entrepreneur fields restore and storage failure is explained', async ({
  page,
}, info) => {
  const { invoice, headers } = await seed(page, `entrepreneur-${info.project.name}`);
  const response = await page.request.post('/api/legal/cases', {
    headers,
    data: { invoice_id: invoice.id },
  });
  const legal = await response.json();
  await page.goto(`/app?section=legal&legal=${legal.id}`);
  await page.getByRole('button', { name: 'Все поля', exact: true }).click();
  await page
    .getByRole('combobox', { name: 'Тип должника', exact: true })
    .selectOption('sole_proprietor');
  await page.getByLabel('Дата рождения должника', { exact: true }).fill('1980-01-02');
  await page.getByLabel('Место рождения должника', { exact: true }).fill('Москва');
  await page.getByRole('tab', { name: 'Расчёт', exact: true }).click();
  await page.getByRole('tab', { name: 'Факты', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Тип должника', exact: true })).toHaveValue(
    'sole_proprietor'
  );
  await expect(page.getByLabel('Дата рождения должника', { exact: true })).toHaveValue(
    '1980-01-02'
  );
  await expect(page.getByLabel('Место рождения должника', { exact: true })).toHaveValue('Москва');
  await page.evaluate(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException('Unavailable', 'QuotaExceededError');
    };
  });
  await page.getByLabel('Номер договора', { exact: true }).fill('Черновик в памяти');
  await expect(page.getByText(/Хранилище браузера недоступно/)).toBeVisible();
  await page.getByRole('tab', { name: 'Расчёт', exact: true }).click();
  await page.getByRole('tab', { name: 'Факты', exact: true }).click();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue('Черновик в памяти');
});
