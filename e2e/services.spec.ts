import { navigate, test, expect, type Page } from './fixtures';

const businessToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Moscow' });
async function account(page: Page) {
  const response = await page.request.post('/api/auth/register', {
    data: {
      name: 'Сотрудник',
      company: 'ООО Проверка сервисов',
      email: `services-${Date.now()}-${Math.random().toString(16).slice(2)}@example.ru`,
      password: 'Services-testing-2026!',
    },
  });
  expect(response.status()).toBe(201);
  return (await response.json()).csrf_token as string;
}
async function invoice(page: Page, csrf: string) {
  const response = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      company: 'ООО Покупатель',
      inn: '7707083893',
      email: 'buyer@example.ru',
      number: 'SERV-1',
      issued_on: businessToday(),
      due_on: businessToday(),
      amount: 100000,
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}
async function tab(page: Page, name: string) {
  await navigate(page, name);
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(
    false
  );
}

test('cash abstention, policy, reviewed internal proposal and stale financial state', async ({
  page,
}, info) => {
  const csrf = await account(page);
  const inv = await invoice(page, csrf);
  await page.goto('/app');
  await tab(page, 'Поступления и условия');
  await expect(page.getByText('Пока недостаточно сопоставимой истории')).toBeVisible();
  const rules = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Правила переговоров', exact: true }) });
  await expect(rules.getByLabel('Разрешить обработку предложений')).not.toBeChecked();
  await rules.getByLabel('Разрешить обработку предложений').check();
  await rules.getByRole('button', { name: 'Сохранить правила' }).click();
  await expect(rules.getByText('Версия 1', { exact: true })).toBeVisible();
  const form = page.locator('section').filter({
    has: page.getByRole('heading', { name: 'Зарегистрировать предложение', exact: true }),
  });
  await form.getByRole('combobox', { name: 'Счёт', exact: true }).selectOption(inv.id);
  await form.getByLabel('Тип предложения').selectOption('payment_claim');
  await form
    .getByLabel('Обращение и основание условий')
    .fill('Покупатель сообщил об оплате, поступление по выписке ещё не проверено.');
  await form.getByLabel('Условия проверены по обращению покупателя').check();
  await form.getByRole('button', { name: 'Проверить предложение' }).click();
  const proposal = page.locator('.ms-proposal').first();
  await expect(proposal.getByText('На согласовании', { exact: true })).toBeVisible();
  await proposal
    .getByLabel('Основание решения')
    .fill('Разрешена внутренняя задача сверки поступления.');
  await proposal.getByRole('button', { name: 'Принять предложение' }).click();
  await expect(proposal.getByText('Принято · ожидает исполнения', { exact: true })).toBeVisible();
  await proposal.getByRole('button', { name: 'Исполнить в кабинете' }).click();
  await expect(
    proposal.getByText('Нужна сверка поступления с выпиской. Остаток не уменьшен.')
  ).toBeVisible();
  await expect(proposal.getByText('Контрагенту ничего не отправлено.')).toBeVisible();
  let list = await page.request.get('/api/invoices');
  expect((await list.json()).items[0].balance).toBe(100000);
  await form.getByLabel('Тип предложения').selectOption('document_request');
  await form
    .getByLabel('Обращение и основание условий')
    .fill('Покупатель запросил копию подтверждения поставки.');
  await form.getByLabel('Условия проверены по обращению покупателя').check();
  await form.getByRole('button', { name: 'Проверить предложение' }).click();
  const pending = page
    .locator('.ms-proposal')
    .filter({ has: page.getByRole('heading', { name: 'Запрос документов', exact: true }) });
  await pending
    .getByLabel('Основание решения')
    .fill('Документы запрошены уполномоченным покупателем.');
  await pending.getByRole('button', { name: 'Принять предложение' }).click();
  const payment = await page.request.post(`/api/invoices/${inv.id}/payments`, {
    headers: { 'X-CSRF-Token': csrf },
    data: { amount: 100000, paid_on: businessToday(), reference: 'SERV-PAY' },
  });
  expect(payment.status()).toBe(200);
  await pending.getByRole('button', { name: 'Исполнить в кабинете' }).click();
  await expect(pending.getByText('Требуется решение сотрудника', { exact: true })).toBeVisible();
  await expect(pending.getByRole('button', { name: 'Исполнить в кабинете' })).toHaveCount(0);
  list = await page.request.get('/api/invoices');
  expect((await list.json()).items[0].balance).toBe(0);
  await noOverflow(page);
  await page.screenshot({
    path: info.outputPath('intelligence.png'),
    fullPage: true,
    animations: 'disabled',
  });
});

test('file statement approval records incoming cash separately and partner access is explicit and revocable', async ({
  page,
}, info) => {
  await account(page);
  await page.goto('/app');
  await tab(page, 'Подключения');
  const file = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Выписка из файла', exact: true }) });
  const own = '40702810000000000001',
    other = '40702810000000000002';
  const day = businessToday().split('-').reverse().join('.');
  const document = (receiver: string, payer: string, number: string) =>
    `СекцияДокумент=Платежное поручение\nНомер=${number}\nДата=${day}\nСумма=1234.56\nПлательщикСчет=${payer}\nПлательщикИНН=7707083893\nПлательщик=ООО Берёзка\nПолучательСчет=${receiver}\nДатаПоступило=${day}\nНазначениеПлатежа=Оплата по счету ${number}\nКонецДокумента\n`;
  const statement = `1CClientBankExchange\nВерсияФормата=1.03\nКодировка=UTF8\nРасчСчет=${own}\n${document(own, other, '42')}${document(other, own, '43')}КонецФайла\n`;
  await file.getByLabel('Собственный расчётный счёт').fill(own);
  await file.getByLabel('Название источника').fill('Выписка для проверки загрузки');
  await file.getByLabel('Файл банковской выписки').evaluate((element, text) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([text], 'statement.txt', { type: 'text/plain' }));
    (element as HTMLInputElement).files = transfer.files;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, statement);
  await file.getByRole('button', { name: 'Проверить выписку' }).click();
  const preview = page.locator('.ms-preview');
  await expect(preview.getByLabel('Подтвердить строку 1', { exact: true })).toBeEnabled();
  await expect(preview.getByLabel('Подтвердить строку 2', { exact: true })).toBeDisabled();
  let bank = await page.request.get('/api/finance/bank-payments');
  expect((await bank.json()).items).toHaveLength(0);
  await preview.getByLabel('Выбрать все доступные строки').check();
  await preview
    .getByLabel('Основание подтверждения')
    .fill('Входящее поступление сверено по выписке.');
  await preview.getByRole('button', { name: 'Подтвердить строки: 1' }).click();
  await expect(preview.getByText('Подтверждено: 1. Уже учтено: 0.')).toBeVisible();
  bank = await page.request.get('/api/finance/bank-payments');
  const items = (await bank.json()).items;
  expect(items).toHaveLength(1);
  expect(items[0].amount).toBe(123456);
  expect(items[0].allocated_amount).toBe(0);
  const publicSummary = await page.request.get('/api/partner/summary');
  expect(publicSummary.status()).toBe(401);
  const partner = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Доступ партнёра к сводке', exact: true }) });
  await expect(partner.getByRole('checkbox')).not.toBeChecked();
  await expect(partner.getByRole('button', { name: 'Создать доступ к сводке' })).toBeDisabled();
  await partner.getByLabel('Получатель доступа').fill('Партнёр по проверке сводки');
  await partner
    .getByLabel('Цель передачи сводки')
    .fill('Проверка общих сумм портфеля по согласованной заявке компании.');
  await partner.getByRole('checkbox').check();
  await partner.getByRole('button', { name: 'Создать доступ к сводке' }).click();
  const secret = partner.getByLabel('Ключ партнёрского доступа', { exact: true });
  await expect(secret).toBeVisible();
  const token = await secret.inputValue();
  const summary = await page.request.get('/api/partner/summary', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(summary.status()).toBe(200);
  const summaryBody = await summary.json();
  expect(Object.keys(summaryBody.totals).sort()).toEqual([
    'invoice_count',
    'outstanding',
    'overdue',
  ]);
  expect(summaryBody.items).toBeUndefined();
  await partner.getByRole('button', { name: 'Скрыть ключ' }).click();
  await expect(secret).toHaveCount(0);
  await partner.getByRole('button', { name: 'Отозвать доступ' }).click();
  await expect(partner.getByText('Отозван', { exact: true })).toBeVisible();
  const revoked = await page.request.get('/api/partner/summary', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(revoked.status()).toBe(401);
  await noOverflow(page);
  await page.screenshot({
    path: info.outputPath('connections.png'),
    fullPage: true,
    animations: 'disabled',
  });
});

test('mocked source contracts require ledger review and preserve statement pagination period', async ({
  page,
}) => {
  const csrf = await account(page);
  const existing = await invoice(page, csrf);
  const checked = new Date().toISOString();
  const sourceItem = {
    row: 1,
    source_id: 'source-1',
    company: 'ООО Покупатель',
    inn: '7707083893',
    number: 'SERV-1',
    issued_on: businessToday(),
    due_on: businessToday(),
    amount: 200000,
    paid_amount: 0,
  };
  const source = {
    id: 'source-run',
    provider: 'one_c',
    status: 'completed',
    checked_at: checked,
    items: [sourceItem],
    coverage: { data_kind: 'receivables', invoice_import_supported: true, complete: true },
  };
  const fixtureRuns: unknown[] = [];
  const fixtureChecks: unknown[] = [];
  const extraInns = Array.from({ length: 10 }, (_, index) => {
    const prefix = String(780000000 + index);
    const weights = [2, 4, 10, 3, 5, 9, 4, 6, 8];
    return (
      prefix +
      String(
        (weights.reduce((total, weight, position) => total + weight * Number(prefix[position]), 0) %
          11) %
          10
      )
    );
  });
  const expectedInns: string[] = [existing.inn, ...extraInns];
  const registryRequests: string[][] = [];
  await page.route('**/api/invoices', (route) =>
    route.fulfill({
      json: {
        items: [
          existing,
          ...extraInns.map((inn, index) => ({
            ...existing,
            id: `batch-invoice-${index}`,
            inn,
            company: `Контрагент ${index + 2}`,
            number: `BATCH-${index + 2}`,
          })),
        ],
      },
    })
  );
  let previewCount = 0,
    approvalCount = 0;
  const bankRequests: { from_on: string; to_on: string; cursor?: string }[] = [];
  await page.route('**/api/integrations', (route) =>
    route.fulfill({
      json: {
        items: ['one_c', 'diadoc', 'tbank', 'dadata', 'tbank_sandbox'].map((provider) => ({
          provider,
          configured: provider !== 'diadoc',
          status: provider === 'diadoc' ? 'unconfigured' : 'not_checked',
          checked_at: null,
          coverage: {},
        })),
      },
    })
  );
  await page.route('**/api/integrations/runs', (route) =>
    route.fulfill({ json: { items: fixtureRuns } })
  );
  await page.route('**/api/integrations/registry/checks', (route) =>
    route.fulfill({ json: { items: fixtureChecks } })
  );
  await page.route('**/api/integrations/one_c/read', async (route) => {
    fixtureRuns.push(source);
    await route.fulfill({ json: source });
  });
  await page.route('**/api/integrations/runs/source-run/invoice-preview', (route) => {
    previewCount++;
    return route.fulfill({
      json: {
        id: `ledger-${previewCount}`,
        items: [sourceItem],
        errors: [],
        changes: [
          {
            action: previewCount === 1 ? 'conflict' : 'update',
            reason:
              previewCount === 1 ? 'Источник противоречит зарегистрированной оплате' : undefined,
            invoice_id: existing.id,
            before: { ...sourceItem, amount: 100000 },
            after: sourceItem,
          },
        ],
        source_run_id: source.id,
      },
    });
  });
  await page.route('**/api/finance/imports/*/approve', (route) => {
    approvalCount++;
    return route.fulfill({ json: { created: 0, updated: 1, skipped: 0 } });
  });
  await page.route('**/api/integrations/tbank/read', async (route) => {
    const body = route.request().postDataJSON() as {
      from_on: string;
      to_on: string;
      cursor?: string;
    };
    bankRequests.push(body);
    const run = {
      id: `bank-page-${bankRequests.length}`,
      provider: 'tbank',
      status: body.cursor ? 'completed' : 'partial',
      checked_at: checked,
      items: [],
      coverage: {
        ...body,
        complete: !!body.cursor,
        next_cursor: body.cursor ? null : 'page-two',
        request_cursor: body.cursor ?? null,
      },
    };
    fixtureRuns.push(run);
    await route.fulfill({ json: run });
  });
  await page.route('**/api/integrations/registry/check-batch', async (route) => {
    const { inns } = route.request().postDataJSON() as { inns: string[] };
    registryRequests.push(inns);
    const items = inns.map((inn) => ({
      id: `batch-${inn}`,
      inn,
      status: 'completed',
      checked_at: checked,
      result: { name: `Контрагент ${inn}`, state: 'ACTIVE' },
    }));
    fixtureChecks.push(...items);
    await route.fulfill({
      json: {
        batch_id: `batch-${registryRequests.length}`,
        provider: 'dadata',
        items,
        requested_count: inns.length,
        cached_count: 0,
        checked_count: inns.length,
        cache_ttl_hours: 24,
        concurrency: 4,
      },
    });
  });
  await page.route('**/api/integrations/registry/check', async (route) => {
    const body = route.request().postDataJSON() as { inn: string };
    const item = {
      id: 'registry-1',
      inn: body.inn,
      status: 'completed',
      checked_at: checked,
      result: {
        name: 'ООО Покупатель',
        state: 'ACTIVE',
        ogrn: '1027700132195',
        provider_record_date: '2010-01-15T00:00:00+00:00',
      },
    };
    const index = fixtureChecks.findIndex((value) => (value as { inn: string }).inn === body.inn);
    if (index >= 0) fixtureChecks.splice(index, 1, item);
    else fixtureChecks.push(item);
    await route.fulfill({ json: item });
  });
  await page.route('**/api/integrations/tbank/sandbox/read', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ mode: 'sandbox' });
    const run = {
      id: 'sandbox-run',
      provider: 'tbank_sandbox',
      environment: 'sandbox',
      mode: 'sandbox',
      status: 'completed',
      checked_at: checked,
      coverage: {
        environment: 'sandbox',
        synthetic: true,
        ledger_effect: 'forbidden',
        production_verified: false,
        complete: false,
      },
      items: [
        {
          row: 1,
          source_id: 'sandbox:fixture',
          operation_date: '2022-02-02T20:07:04Z',
          amount: 48450,
          reference: 'SANDBOX-1',
          approvable: false,
        },
      ],
    };
    fixtureRuns.push(run);
    await route.fulfill({ json: run });
  });
  await page.route('**/api/forecast', (route) =>
    route.fulfill({
      json: {
        as_of: businessToday(),
        generated_at: checked,
        method: 'empirical_due_cohort_v1',
        status: 'available',
        horizons: [7, 30, 60].map((days) => ({
          days,
          expected_amount: 1234567,
          low_scenario: 1000000,
          high_scenario: 1500000,
        })),
        coverage: {
          open_balance: 2000000,
          eligible_balance: 2000000,
          covered_balance: 2000000,
          training_invoices: 8,
          bank_allocations: 5,
          excluded_balance: 0,
          uncovered_balance: 0,
        },
        limitations: ['Границы — наблюдавшиеся сценарии, не гарантия поступлений.'],
        invoices: [],
      },
    })
  );
  await page.goto('/app');
  await tab(page, 'Подключения');
  const oneC = page
    .locator('.ms-connections section')
    .filter({ has: page.getByRole('heading', { name: '1С', exact: true }) });
  await oneC.getByRole('button', { name: 'Прочитать данные' }).click();
  const stage = page.locator('.ms-preview');
  await stage.getByLabel('Подтвердить строку 1', { exact: true }).check();
  await stage.getByRole('button', { name: 'Сверить выбранные документы с реестром' }).click();
  const ledger = page.locator('.ms-ledger-preview');
  await expect(ledger.getByText('Источник противоречит зарегистрированной оплате')).toBeVisible();
  await expect(
    ledger.getByRole('button', { name: 'Подтвердить изменения реестра' })
  ).toBeDisabled();
  expect(approvalCount).toBe(0);
  await stage.getByRole('button', { name: 'Сверить выбранные документы с реестром' }).click();
  await expect(ledger.getByRole('heading', { name: 'Изменение счёта', exact: true })).toBeVisible();
  await ledger
    .getByLabel('Основание изменения реестра')
    .fill('Изменения подтверждены по первичному документу.');
  await expect(
    ledger.getByRole('button', { name: 'Подтвердить изменения реестра' })
  ).toBeDisabled();
  await ledger.getByRole('checkbox').check();
  await ledger.getByRole('button', { name: 'Подтвердить изменения реестра' }).click();
  await expect(ledger.getByText('Создано: 0. Обновлено: 1. Без изменений: 0.')).toBeVisible();
  expect(approvalCount).toBe(1);
  const tbank = page
    .locator('.ms-connections section')
    .filter({ has: page.getByRole('heading', { name: 'Т-Банк', exact: true }) });
  await tbank.getByRole('button', { name: 'Прочитать данные' }).click();
  await expect(stage.getByText('Т-Банк · Получена часть выписки')).toBeVisible();
  await tbank.getByLabel('Начало периода').fill(businessToday());
  await stage.getByRole('button', { name: 'Следующая страница выписки' }).click();
  await expect(stage.getByText(/Это страница продолжения/)).toBeVisible();
  expect(bankRequests).toHaveLength(2);
  expect(bankRequests[1]).toEqual({ ...bankRequests[0], cursor: 'page-two' });
  await page.getByRole('button', { name: 'Проверить должников: 10', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Проверить должников: 1', exact: true })
  ).toBeEnabled();
  expect(registryRequests[0]).toEqual(expectedInns.slice(0, 10));
  await page.getByRole('button', { name: 'Проверить должников: 1', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Свежие результаты по всем ИНН', exact: true })
  ).toBeDisabled();
  expect(registryRequests[1]).toEqual(expectedInns.slice(10));
  await expect(
    page.getByText('Результаты по 1 ИНН: без кеша 1, из свежего кеша 0.', { exact: true })
  ).toBeVisible();
  await page.getByLabel('Точный ИНН', { exact: true }).fill('7707083893');
  await page.getByRole('button', { name: 'Проверить должника', exact: true }).click();
  await expect(page.getByText('Действует · ОГРН 1027700132195')).toBeVisible();
  await expect(
    page.getByText('Дата последнего изменения записи у провайдера: 15.01.2010')
  ).toBeVisible();
  await expect(
    page.getByText('ЕГРЮЛ/ЕГРИП: снимок провайдера', { exact: true }).first()
  ).toBeVisible();
  await expect(page.getByText('Банкротство: не проверено', { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText('Судебные дела: не проверено', { exact: true }).first()
  ).toBeVisible();
  await expect(page.getByText('ФССП: не проверено', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Прочитать публичную песочницу', exact: true }).click();
  await expect(stage.getByText(/Тестовые данные публичной песочницы/)).toBeVisible();
  await expect(stage.locator('input[type=checkbox]:enabled')).toHaveCount(0);
  await expect(stage.getByRole('button', { name: /Подтвердить строки/ })).toHaveCount(0);
  expect((await (await page.request.get('/api/finance/bank-payments')).json()).items).toHaveLength(
    0
  );

  await noOverflow(page);
  await tab(page, 'Поступления и условия');
  await expect(page.locator('.ms-forecast-grid article')).toHaveCount(3);
  expect(
    (await page.locator('.ms-forecast-grid strong').first().innerText()).replace(/\s/g, '')
  ).toBe('12345,67₽');
  await noOverflow(page);
});

test('ambiguous file receipt requires single-document confirmation and a separate reason', async ({
  page,
}) => {
  const csrf = await account(page);
  const initial = await page.request.post('/api/finance/bank-payments', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      external_id: 'manual-original',
      amount: 123456,
      paid_on: businessToday(),
      payer_inn: '7707083893',
      payer_name: 'ООО Берёзка',
      reference: 'ORIGINAL-1',
      evidence: 'Поступление сверено вручную по оригиналу выписки',
      confirmed: true,
    },
  });
  expect(initial.status()).toBe(201);
  await page.goto('/app');
  await tab(page, 'Подключения');
  const source = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Выписка из файла', exact: true }) });
  const day = businessToday().split('-').reverse().join('.');
  const statement = `1CClientBankExchange\nВерсияФормата=1.03\nКодировка=UTF8\nРасчСчет=40702810000000000001\nСекцияДокумент=Платежное поручение\nНомер=DISTINCT-2\nДата=${day}\nСумма=1234.56\nПлательщикСчет=40702810000000000002\nПлательщикИНН=7707083893\nПлательщик=ООО Берёзка\nПолучательСчет=40702810000000000001\nДатаПоступило=${day}\nНазначениеПлатежа=Отдельная поставка по другому поручению\nКонецДокумента\nКонецФайла\n`;
  await source.getByLabel('Собственный расчётный счёт').fill('40702810000000000001');
  await source.getByLabel('Название источника').fill('Сверка отдельного поступления');
  await source.getByLabel('Файл банковской выписки').evaluate((element, text) => {
    const files = new DataTransfer();
    files.items.add(new File([text], 'distinct.txt', { type: 'text/plain' }));
    (element as HTMLInputElement).files = files.files;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, statement);
  await source.getByRole('button', { name: 'Проверить выписку' }).click();
  const preview = page.locator('.ms-preview');
  await expect(
    preview.getByLabel('Подтверждаю отдельное поступление с другим номером документа', {
      exact: true,
    })
  ).toHaveCount(0);
  await preview.getByLabel('Подтвердить строку 1', { exact: true }).check();
  await preview
    .getByLabel('Основание подтверждения', { exact: true })
    .fill('Документ проверен по банковской выписке.');
  await preview.getByRole('button', { name: 'Подтвердить строки: 1' }).click();
  await expect(
    preview.getByLabel('Подтверждаю отдельное поступление с другим номером документа', {
      exact: true,
    })
  ).toBeVisible();
  expect((await (await page.request.get('/api/finance/bank-payments')).json()).items).toHaveLength(
    1
  );
  await preview
    .getByLabel('Подтверждаю отдельное поступление с другим номером документа', { exact: true })
    .check();
  await expect(preview.getByRole('button', { name: 'Подтвердить строки: 1' })).toBeDisabled();
  await preview
    .getByLabel('Почему это отдельное поступление', { exact: true })
    .fill(
      'Проверены два оригинальных поручения с разными номерами; разные поставки оплачены отдельно.'
    );
  await preview.getByRole('button', { name: 'Подтвердить строки: 1' }).click();
  await expect(preview.getByText('Подтверждено: 1. Уже учтено: 0.')).toBeVisible();
  const payments = (await (await page.request.get('/api/finance/bank-payments')).json()).items;
  expect(payments).toHaveLength(2);
  expect(
    payments.every((payment: { allocated_amount: number }) => payment.allocated_amount === 0)
  ).toBe(true);
});
