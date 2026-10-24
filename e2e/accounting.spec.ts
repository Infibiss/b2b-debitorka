import { test, expect } from './fixtures';

const businessToday = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(
  new Date()
);

test('accounting source mapping, discrepancy and approved evidence persist without fabricating invoices', async ({
  page,
}, info) => {
  const registered = await page.request.post('/api/auth/register', {
    data: {
      company: 'ООО Поставщик',
      name: 'Бухгалтер',
      email: `accounting-${Date.now()}-${info.project.name}@example.ru`,
      password: 'Accounting-browser-2026!',
    },
  });
  expect(registered.status()).toBe(201);
  const session = await registered.json();
  const created = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      company: 'ООО Берёзка',
      inn: '7701234567',
      number: `OSV-${Date.now()}`,
      issued_on: businessToday,
      due_on: businessToday,
      amount: 70_000,
    },
  });
  expect(created.status()).toBe(201);
  const original = await created.json();
  const source = `ОСВ 62: браузер ${info.project.name}`;
  const reason =
    'Проверено бухгалтером: расхождение передано на разбор, агрегаты не являются счетами';
  await page.goto('/app');
  await page.getByRole('button', { name: 'Финансы', exact: true }).click();
  await page.getByRole('tab', { name: 'ОСВ и акты', exact: true }).click();
  await page.getByLabel('Номер или название источника', { exact: true }).fill(source);
  await page.getByLabel('Дата остатков', { exact: true }).fill(businessToday);
  await page
    .getByLabel('Данные источника', { exact: true })
    .fill(
      [
        'Контрагент;ИНН;Начальное сальдо дебет;Начальное сальдо кредит;Оборот дебет;Оборот кредит;Конечное сальдо дебет;Конечное сальдо кредит',
        'ООО Берёзка;7701234567;1000;0;200;400;800;0',
        'ООО Север;7801234567;500;0;100;0;600;0',
        'Итого;;1500;0;300;400;1400;0',
      ].join('\n')
    );
  await page.getByRole('button', { name: 'Прочитать столбцы', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Сопоставление столбцов', exact: true })
  ).toBeVisible();
  const fields = [
    'Контрагент',
    'ИНН',
    'Начальное сальдо, дебет',
    'Начальное сальдо, кредит',
    'Оборот, дебет',
    'Оборот, кредит',
    'Конечное сальдо, дебет',
    'Конечное сальдо, кредит',
  ];
  for (let index = 0; index < fields.length; index++) {
    const select = page
      .locator('.ops-mapping')
      .getByRole('combobox', { name: new RegExp(`^${fields[index]}`) });
    await expect(select).toHaveValue(`column_${index + 1}`);
  }
  // Exercise a manual correction after automatic discovery through the actual UI.
  const endingDebit = page
    .locator('.ops-mapping')
    .getByRole('combobox', { name: /^Конечное сальдо, дебет/ });
  await endingDebit.selectOption('');
  await endingDebit.selectOption('column_7');
  await page.getByRole('button', { name: 'Сравнить остатки', exact: true }).click();
  await expect(page.getByText(/Итоговая строка не является контрагентом/)).toBeVisible();
  const preview = page
    .locator('.ops-preview')
    .filter({ has: page.getByRole('columnheader', { name: 'СЕЙЧАС В РЕЕСТРЕ', exact: true }) });
  const buyer = preview.getByRole('row').filter({ hasText: 'ООО Берёзка' });
  await expect(buyer).toContainText('800 ₽');
  await expect(buyer).toContainText('700 ₽');
  await expect(buyer).toContainText('100 ₽');
  await expect(preview.getByLabel('Включить строку 2', { exact: true })).toBeChecked();
  await expect(preview.getByLabel('Включить строку 3', { exact: true })).toBeChecked();
  await expect(preview.getByLabel('Включить строку 4', { exact: true })).toHaveCount(0);
  await page.getByLabel('Основание согласования', { exact: true }).fill(reason);
  await page
    .getByLabel('Проверил выбранные строки и исключил промежуточные итоги', { exact: true })
    .check();
  await page.getByRole('button', { name: 'Сохранить сверку', exact: true }).click();
  const history = page
    .locator('.ops-card')
    .filter({ has: page.getByRole('heading', { name: 'Сохранённые сверки', exact: true }) });
  await expect(history.getByRole('row').filter({ hasText: 'ООО Берёзка' })).toContainText(source);
  await expect(history.getByRole('row').filter({ hasText: 'ООО Берёзка' })).toContainText(reason);
  await expect(history.getByRole('row').filter({ hasText: 'ООО Север' })).toContainText('600 ₽');
  const ledger = await page.request.get('/api/invoices');
  expect(ledger.status()).toBe(200);
  const items = (await ledger.json()).items;
  expect(items).toHaveLength(1);
  expect(items[0].id).toBe(original.id);
  expect(items[0].balance).toBe(70_000);
  await page.reload();
  await page.getByRole('button', { name: 'Финансы', exact: true }).click();
  await page.getByRole('tab', { name: 'ОСВ и акты', exact: true }).click();
  await expect(history.getByRole('row').filter({ hasText: 'ООО Берёзка' })).toContainText(reason);
  await expect(history.getByRole('row').filter({ hasText: 'ООО Север' })).toContainText(source);
  await expect(history.getByRole('row')).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(
    false
  );
  await page.screenshot({
    path: info.outputPath('accounting-source.png'),
    fullPage: true,
    animations: 'disabled',
  });
});
