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
async function tab(page: Page, name: string) {
  await navigate(page, name);
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(
    false
  );
}

test('file statement approval records incoming cash separately and partner access is explicit and revocable', async ({
  page,
}, info) => {
  await account(page);
  await page.goto('/app');
  await tab(page, 'Подключения');
  await page
    .getByRole('group', { name: 'Источники' })
    .getByRole('button', { name: 'Банк', exact: true })
    .click();
  const file = page
    .locator('.ms-card')
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
  await page.getByText('Доступ партнёра к сводке', { exact: true }).first().click();
  const partner = page
    .locator('.ms-card')
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
  await page
    .getByRole('group', { name: 'Источники' })
    .getByRole('button', { name: 'Банк', exact: true })
    .click();
  const source = page
    .locator('.ms-card')
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
