import { test, expect, navigate, type Page } from './fixtures';

async function account(page: Page, suffix: string) {
  const response = await page.request.post('/api/auth/register', {
    data: {
      name: 'Анна',
      company: 'Поставка',
      email: `audit-fix-${suffix}-${Date.now()}@example.ru`,
      password: 'Audit-followup-2026!',
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
      number: 'АУД-42',
      issued_on: '2026-08-01',
      due_on: '2026-09-01',
      amount: 18000000,
      paid_amount: 1500000,
    },
  });
  expect(added.status()).toBe(201);
  const invoice = await added.json();
  await page.goto(`/app?context=${invoice.id}`);
  await page.getByRole('button', { name: 'Позже', exact: true }).click();
  return { invoice, headers };
}

test('direct import intent survives registration and empty workbench has a short start', async ({
  page,
}, info) => {
  await page.goto('/app?intent=import');
  await page.getByLabel('Компания', { exact: true }).fill('Первый клиент');
  await page.getByLabel('Ваше имя', { exact: true }).fill('Анна');
  await page
    .getByLabel('Рабочая почта', { exact: true })
    .fill(`intent-${info.project.name}-${Date.now()}@example.ru`);
  await page.getByLabel('Пароль', { exact: true }).fill('Start-from-import-2026!');
  await page.getByRole('checkbox').check();
  await page.locator('form').getByRole('button', { name: 'Создать аккаунт', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('реестр');
  expect(new URL(page.url()).searchParams.has('intent')).toBe(false);
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Начните с вашего реестра', exact: true })
  ).toBeVisible();
  await expect(page.getByLabel('Суммы по портфелю')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('permissions return preserves installment draft and old proposal can be rechecked', async ({
  page,
}, info) => {
  const { invoice, headers } = await account(page, `terms-${info.project.name}`);
  const policy = await page.request.put('/api/negotiation/policy', {
    headers,
    data: {
      expected_version: 0,
      enabled: true,
      auto_accept: false,
      max_promise_days: 30,
      max_installments: 6,
      max_discount_bps: 0,
      allowed_kinds: ['promise', 'installment', 'payment_claim'],
    },
  });
  expect(policy.status()).toBe(200);
  await navigate(page, 'Прогноз и условия');
  const check = page.getByLabel('Проверка полномочий', { exact: true });
  await expect(check).toContainText('Разрешите принимать обещания');
  await page
    .getByRole('combobox', { name: 'Тип предложения', exact: true })
    .selectOption('installment');
  await page.getByLabel('Обещанная сумма, ₽', { exact: true }).fill('5000');
  await page.getByLabel('Сумма платежа 1, ₽', { exact: true }).fill('5000');
  await page
    .getByRole('textbox', { name: 'Обращение и основание условий', exact: true })
    .fill('Оплатим по графику, письмо 42');
  await page.getByRole('button', { name: 'Разрешения этого контрагента', exact: true }).click();
  const modal = page.getByRole('dialog');
  await expect(modal).toContainText('Северстрой');
  await modal.getByLabel('Разрешить Mandato принимать обещания оплаты в заданных пределах').check();
  await modal.getByRole('button', { name: 'Сохранить изменения', exact: true }).click();
  await expect(modal).toHaveCount(0);
  await page.getByRole('button', { name: 'Вернуться к предложению', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Тип предложения', exact: true })).toHaveValue(
    'installment'
  );
  await expect(page.getByLabel('Сумма платежа 1, ₽', { exact: true })).toHaveValue('5000');
  await expect(
    page.getByRole('textbox', { name: 'Обращение и основание условий', exact: true })
  ).toHaveValue('Оплатим по графику, письмо 42');
  await expect(check).toContainText('Предварительные ограничения не найдены');
  page.on('dialog', (dialog) => dialog.accept());
  await page.reload();
  await expect(page.getByLabel('Обещанная сумма, ₽', { exact: true })).toHaveValue('5000');
  await page.getByLabel('Условия проверены по обращению покупателя').check();
  await page.getByRole('button', { name: 'Проверить предложение', exact: true }).click();
  const card = page.locator('.ms-proposal').first();
  await expect(card).toContainText('Оплатим по графику, письмо 42');
  await card
    .getByLabel('Основание повторной проверки', { exact: true })
    .fill('Полномочия уточнены, условия действуют');
  await card.getByRole('button', { name: 'Повторно проверить предложение', exact: true }).click();
  await card.getByText('История решений', { exact: true }).click();
  await expect(card).toContainText('Условия повторно проверены');
  const proposals = (await (await page.request.get('/api/negotiation/proposals')).json()).items;
  expect(proposals).toHaveLength(1);
  expect(proposals[0].invoice_id).toBe(invoice.id);
  expect(
    (await (await page.request.get(`/api/invoices/${invoice.id}`)).json()).invoice.balance
  ).toBe(16500000);
});

test('context help preserves partial legal intake, steps and route through reload', async ({
  page,
}, info) => {
  const { invoice, headers } = await account(page, `legal-${info.project.name}`);
  const created = await page.request.post('/api/legal/cases', {
    headers,
    data: { invoice_id: invoice.id },
  });
  expect(created.status()).toBe(201);
  const legal = await created.json();
  await navigate(page, 'Претензии и суд');
  await page.getByLabel('Номер договора', { exact: true }).fill('ЧАСТЬ-42');
  const before = page.url();
  await page.getByRole('button', { name: 'Как работать в разделе', exact: true }).click();
  await expect(
    page.getByRole('complementary', { name: 'Обучение: Претензии и суд', exact: true })
  ).toBeVisible();
  expect(page.url()).toBe(before);
  await page.getByRole('button', { name: 'Закрыть обучение', exact: true }).click();
  await expect(page.getByLabel('Номер договора', { exact: true })).toHaveValue('ЧАСТЬ-42');
  await page.getByRole('button', { name: 'Сохранить факты', exact: true }).click();
  await expect(page.getByText('Факты сохранены', { exact: true })).toBeVisible();
  const saved = (await (await page.request.get(`/api/legal/cases/${legal.id}`)).json()).facts;
  expect(saved.contract_number).toBe('ЧАСТЬ-42');
  expect(saved.contract_date).toBe(null);
  expect(saved.business_debt_confirmed).toBe(false);
  await page.getByRole('button', { name: 'Должник', exact: true }).click();
  await page.getByLabel('Адрес должника', { exact: true }).fill('Несохранённый адрес');
  page.on('dialog', (dialog) => dialog.accept());
  await page.reload();
  await expect(page.getByLabel('Адрес должника', { exact: true })).toHaveValue(
    'Несохранённый адрес'
  );
  await expect(page.getByLabel('Номер договора', { exact: true })).toBeHidden();
  await expect(page.getByText(/Готовность сохранённых данных:/)).toBeVisible();
});

test('conversation connects terms to payment reconciliation and shows provider status upfront', async ({
  page,
}, info) => {
  const { invoice, headers } = await account(page, `history-${info.project.name}`);
  const created = await page.request.post('/api/negotiation/proposals', {
    headers,
    data: {
      invoice_id: invoice.id,
      kind: 'payment_claim',
      evidence: 'Мы оплатили вчера, проверьте выписку',
      confirmed_by_operator: true,
      expires_on: '2026-12-31',
      idempotency_key: 'claim',
    },
  });
  expect(created.status()).toBe(201);
  await navigate(page, 'Переписка');
  const timeline = page.locator('.case-conversation');
  await expect(timeline).toContainText('Мы оплатили вчера, проверьте выписку');
  await expect(timeline).toContainText('Оплачено на начало учёта');
  await timeline.getByRole('button', { name: 'Покупатель оплатил — сверить', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Счёт', exact: true })).toHaveValue(invoice.id);
  expect(new URL(page.url()).searchParams.get('financeTab')).toBe('ledger');
  await navigate(page, 'Разбор ответов');
  await expect(
    page.getByText('Автоматическая обработка недоступна', { exact: true })
  ).toBeVisible();
  await page.getByRole('button', { name: 'Разобрать сообщение', exact: true }).click();
  await page
    .getByRole('dialog')
    .getByLabel('Новый ответ покупателя', { exact: true })
    .fill('Оплатим 5000 рублей по графику, письмо 77');
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Разобрать сообщение', exact: true })
    .click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Разобрать условия вручную', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Использовать текст ответа как основание', exact: true })
    .click();
  await expect(
    page.getByRole('textbox', { name: 'Обращение и основание условий', exact: true })
  ).toHaveValue('Оплатим 5000 рублей по графику, письмо 77');
  await expect(page.getByRole('combobox', { name: 'Счёт', exact: true })).toHaveValue(invoice.id);
});

test('compact queue keeps filters in URL and financial source labels are explicit', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await account(page, `queue-${info.project.name}`);
  await expect(page.getByRole('button', { name: 'Таблица', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  const first = page.getByRole('button', { name: 'Открыть дело Северстрой', exact: true });
  await expect(first).toBeVisible();
  expect((await first.boundingBox())!.y).toBeLessThan(700);
  await page.getByLabel('Поиск дел', { exact: true }).fill('Север');
  await page.reload();
  await expect(page.getByLabel('Поиск дел', { exact: true })).toHaveValue('Север');
  await page.getByText('Сводка портфеля и источники оплат', { exact: true }).click();
  await expect(page.getByText('Подтверждено по банку', { exact: true })).toBeVisible();
  await expect(page.locator('.wf-source-note').first()).toContainText(/15\s000/);
  await expect(page.locator('.wf-source-note').first()).toContainText(
    'не означают результат взыскания'
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.getByText('Сводка портфеля и источники оплат', { exact: true }).click();
  await page.screenshot({ path: info.outputPath('mobile-queue.png'), fullPage: true });
  await info.attach('mobile-measurements.json', {
    contentType: 'application/json',
    body: JSON.stringify(
      {
        viewport: page.viewportSize(),
        first_case: await first.boundingBox(),
        horizontal_overflow: await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth
        ),
      },
      null,
      2
    ),
  });
  await navigate(page, 'Аудит');
  await page.getByRole('button', { name: 'Собрать аудит', exact: true }).click();
  await expect(page.locator('.portfolio-metrics small').first()).toBeVisible();
  const captions = await page
    .locator('.portfolio-metrics small, .portfolio-metrics span, .portfolio-desk .page-date')
    .evaluateAll((elements) => elements.map((el) => parseFloat(getComputedStyle(el).fontSize)));
  expect(Math.min(...captions)).toBeGreaterThanOrEqual(12);
  const labels = await page
    .locator('.portfolio-metrics span')
    .evaluateAll((elements) => elements.map((el) => parseFloat(getComputedStyle(el).fontSize)));
  expect(Math.min(...labels)).toBeGreaterThanOrEqual(14);
});
