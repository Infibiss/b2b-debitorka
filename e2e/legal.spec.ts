import { navigate, test, expect } from './fixtures';

const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(new Date());

test('legal facts, calculation, evidence, real DOCX review and manual filing persist', async ({
  page,
}, info) => {
  const response = await page.request.post('/api/auth/register', {
    data: {
      company: 'ООО Поставщик',
      name: 'Проверяющий юрист',
      email: `legal-${Date.now()}-${info.project.name}@example.ru`,
      password: 'Legal-browser-2026!',
    },
  });
  expect(response.status()).toBe(201);
  const session = await response.json();
  const added = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      company: 'ООО Покупатель',
      inn: '7701234567',
      email: 'buyer@example.ru',
      number: `LEGAL-${Date.now()}`,
      issued_on: '2026-08-01',
      due_on: '2026-09-01',
      amount: 10_000_000,
    },
  });
  expect(added.status()).toBe(201);
  const invoice = await added.json();
  await page.goto('/app');
  await navigate(page, 'Дела');
  await page.getByRole('button', { name: 'Новое дело', exact: true }).click();
  const opening = page.getByRole('dialog', { name: 'Новое юридическое дело', exact: true });
  await opening.getByRole('combobox', { name: 'Счёт', exact: true }).selectOption(invoice.id);
  await opening.getByRole('button', { name: 'Открыть дело', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Данные дела', exact: true })
  ).toBeVisible();
  await page.getByRole('button', { name: 'Все поля', exact: true }).click();
  for (const [label, value] of Object.entries({
    'Наименование кредитора': 'ООО Поставщик',
    'ИНН кредитора': '7801234567',
    'ОГРН / ОГРНИП кредитора': '1027800000001',
    'Адрес кредитора': 'Санкт-Петербург, Невский проспект, 1',
    'Банковские реквизиты кредитора': 'Расчётный счёт 40702810000000000001, БИК 044030001',
    'Наименование должника': 'ООО Покупатель',
    'ИНН должника': '7701234567',
    'ОГРН / ОГРНИП должника': '1027700000001',
    'Адрес должника': 'Москва, улица Покупателя, 1',
    'Номер договора': 'П-1',
    'Дата договора': '2026-07-01',
    'Содержание обязательства': 'Оплата поставленного оборудования',
    'Факт исполнения': 'Товар передан и принят по УПД № 10',
    'Основание срока оплаты': 'Пункт 3.1 договора: оплатить до 01.09.2026',
    'Правовое основание требования': 'Статьи 309, 310, 516 ГК РФ; договор № П-1',
    'Наименование суда': 'Арбитражный суд города Москвы',
    'Адрес суда': 'Москва, Большая Тульская, 17',
    'Основание подсудности': 'Место нахождения ответчика, статья 35 АПК РФ',
    'Договор сопровождения': 'Договор № А-1',
    'Дата начала сопровождения': '2026-08-01',
    'Отдельное соглашение с адвокатом': 'Прямое соглашение с адвокатом № 1',
  }))
    await page.getByLabel(label, { exact: true }).fill(value);
  const business = page.getByLabel('Долг возник в предпринимательской деятельности', {
    exact: true,
  });
  await expect(business).not.toBeChecked();
  await business.check();
  await page
    .getByLabel('Проверены специальные режимы, банкротство, моратории и давность', { exact: true })
    .check();
  await page.getByLabel('Требование бесспорно и подтверждено документами', { exact: true }).check();
  await page.getByRole('button', { name: 'Сохранить факты', exact: true }).click();
  await expect(page.getByText('Факты сохранены', { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Расчёт', exact: true }).click();
  await expect(page.getByLabel('Вид начислений', { exact: true })).toHaveValue('none');
  await page.getByLabel('Вид начислений', { exact: true }).selectOption('art395');
  await page.getByLabel('Рассчитать по', { exact: true }).fill(today);
  await page.getByRole('button', { name: 'Рассчитать требования', exact: true }).click();
  await expect(page.locator('.legal-calculation-result')).toContainText('100 000');
  await expect(page.locator('.legal-calculation-result')).toContainText('Проценты по ст. 395');
  await page.getByRole('tab', { name: 'Доказательства', exact: true }).click();
  const proofs = [
    ['contract', 'Договор № П-1', '2026-07-01'],
    ['performance', 'УПД № 10', '2026-08-01'],
    ['duty_payment', 'Пошлина: поручение 11', today],
    ['application_copy_sent', 'Копия заявления: РПО 12', today],
    ['filing_receipt', 'Тестовая квитанция ручной подачи 13', today],
  ];
  for (const [kind, title, date] of proofs) {
    await page.getByLabel('Вид доказательства', { exact: true }).selectOption(kind);
    await page.getByLabel('Название доказательства', { exact: true }).fill(title);
    await page
      .getByLabel('Номер, ссылка или место хранения', { exact: true })
      .fill(`Тестовая папка клиента: ${title}`);
    await page.getByLabel('Дата документа', { exact: true }).fill(date);
    await page
      .getByRole('button', { name: 'Зарегистрировать доказательство', exact: true })
      .click();
    await expect(page.locator('.legal-evidence-list')).toContainText(title);
  }
  await page.getByRole('tab', { name: 'Документы', exact: true }).click();
  await page.getByLabel('Вид документа', { exact: true }).selectOption('court_order');
  await page.getByRole('button', { name: 'Подготовить DOCX', exact: true }).click();
  await expect(page.locator('.legal-document-list')).toContainText('Версия 1');
  await expect(page.locator('.legal-document-list')).toContainText('Требует проверки');
  const downloaded = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Скачать DOCX', exact: true }).click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toMatch(/court_order-v1\.docx$/);
  const path = info.outputPath('court-order.docx');
  await download.saveAs(path);
  const stream = await download.createReadStream();
  expect(stream).not.toBeNull();
  const chunks: Uint8Array[] = [];
  for await (const chunk of stream!) chunks.push(chunk);
  expect(chunks[0][0]).toBe(0x50);
  expect(chunks[0][1]).toBe(0x4b);
  await page.getByRole('button', { name: 'Проверить версию', exact: true }).click();
  const review = page.getByRole('dialog', { name: 'Проверка документа', exact: true });
  await review.getByLabel('Решение проверяющего', { exact: true }).selectOption('approved');
  await review.getByLabel('Проверяющий', { exact: true }).fill('Проверяющий юрист');
  await review
    .getByLabel('Полномочия проверяющего', { exact: true })
    .fill('Тестовая доверенность № 1');
  await review
    .getByLabel('Комментарий проверяющего', { exact: true })
    .fill('Проверены расчёт, факты, документы и полномочия');
  await review
    .getByLabel('Подтверждаю полномочия и квалификацию для проверки', { exact: true })
    .check();
  await review.getByRole('button', { name: 'Зафиксировать проверку', exact: true }).click();
  await expect(page.locator('.legal-document-list')).toContainText('Согласовано');
  await page.getByRole('tab', { name: 'Ход дела', exact: true }).click();
  await page.getByLabel('Ручное действие', { exact: true }).selectOption('filed');
  await page.getByLabel('Дата действия', { exact: true }).fill(today);
  await page
    .getByLabel('Номер дела, отправления или квитанции', { exact: true })
    .fill('Тестовая квитанция Мой Арбитр');
  await page
    .getByLabel('Описание ручного действия', { exact: true })
    .fill('Юрист самостоятельно подал документы; кабинет фиксирует факт');
  await page
    .getByLabel('Версия документа', { exact: true })
    .selectOption({ label: 'Заявление о судебном приказе · версия 1' });
  for (const [, title] of proofs.slice(2)) await page.getByLabel(title, { exact: true }).check();
  await page.getByRole('button', { name: 'Записать ручное действие', exact: true }).click();
  await expect(page.locator('.legal-milestones')).toContainText('Подача в суд');
  await expect(page.locator('.legal-milestones')).toContainText('кабинет фиксирует факт');
  await page.getByRole('tab', { name: 'Гонорар', exact: true }).click();
  await expect(page.locator('.legal-fee')).toContainText('Подтверждённые поступления');
  await expect(page.locator('.legal-fee')).toContainText('0 ₽');
  await expect(
    page.locator('.legal-fee .ops-result-grid > div').filter({ hasText: 'Итого Mandato' })
  ).toContainText(/9\s?900\s?₽/);
  await expect(
    page.locator('.legal-fee .ops-result-grid > div').filter({ hasText: 'Адвокату отдельно' })
  ).toContainText('0 ₽');
  await expect(
    page.getByRole('table', { name: 'Стоимость поданных судебных пакетов' })
  ).toContainText('Заявление о судебном приказе');
  await expect(
    page.getByRole('table', { name: 'Стоимость поданных судебных пакетов' })
  ).toContainText(/9\s?900\s?₽/);
  await page
    .locator('.legal-fee')
    .screenshot({ path: info.outputPath('application-fees.png'), animations: 'disabled' });
  await page.reload();
  await expect(page.getByRole('tab', { name: 'Гонорар', exact: true })).toHaveAttribute(
    'aria-selected',
    'true'
  );
  await expect(page.locator('.ops-context')).toContainText(invoice.number);
  await page.getByRole('tab', { name: 'Документы', exact: true }).click();
  await expect(page.locator('.legal-document-list')).toContainText('Согласовано');
  await expect(page.getByRole('link', { name: 'Скачать DOCX', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(
    false
  );
  await page.screenshot({
    path: info.outputPath('legal-case.png'),
    fullPage: true,
    animations: 'disabled',
  });
});
