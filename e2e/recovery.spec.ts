import { expect, test } from './fixtures';

const password = 'Correct-horse-24!';

async function signUp(page: import('@playwright/test').Page) {
  const email = `owner-${Date.now()}-${Math.random().toString(16).slice(2)}@example.ru`;
  await page.goto('/app?mode=register');
  await page.getByLabel('Ваше имя').fill('Анна');
  await page.getByLabel('Компания', { exact: true }).fill('ООО Поставка');
  await page.getByLabel('Рабочая почта').fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  for (const box of await page.getByRole('checkbox').all()) await box.check();
  await page.locator('form').getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByRole('heading', { name: 'Главная' })).toBeVisible();
}

async function addInvoice(page: import('@playwright/test').Page) {
  const csrf = await page.evaluate(
    async () => (await (await fetch('/api/auth/me')).json()).csrf_token
  );
  const day = (offset: number) =>
    new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10);
  const response = await page.request.post('/api/invoices', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      company: 'ООО Север',
      inn: '7701234567',
      email: 'ap@example.ru',
      number: 'СЧ-1',
      issued_on: day(-40),
      due_on: day(-20),
      amount: 50000000,
      notes: '',
    },
  });
  expect(response.ok()).toBeTruthy();
}

test('new client sees setup steps and moves a debtor to work', async ({ page }) => {
  await signUp(page);
  await expect(page.getByText('Настройка: 0 из 6')).toBeVisible();
  await addInvoice(page);
  await page.goto('/app?section=debtors');
  await page.getByRole('button', { name: 'ООО Север' }).click();
  await expect(page.getByRole('heading', { name: 'ООО Север' })).toBeVisible();
  await expect(page.getByText('Готовность к суду: 0%')).toBeVisible();
  await page.getByRole('button', { name: 'Начать работу' }).click();
  await expect(page.getByText('Напоминания').first()).toBeVisible();
  await page.getByRole('button', { name: 'Финансирование' }).last().click();
  await expect(page.getByRole('heading', { name: 'Факторинг' })).toBeVisible();
});

test('debtor card holds documents, correspondence and invoice actions', async ({ page }) => {
  await signUp(page);
  await addInvoice(page);
  await expect(page.getByText('Инструменты')).toHaveCount(0);
  await page.goto('/app?section=debtors');
  await page.getByRole('button', { name: 'ООО Север' }).click();
  await page.getByRole('button', { name: 'Документы', exact: true }).click();
  await page.getByLabel('Номер и название').fill('Договор № 12 от 01.02.2026');
  await page.getByRole('button', { name: 'Добавить документ' }).click();
  await expect(page.getByText(/Договор № 12 от 01.02.2026/).first()).toBeVisible();
  await page.getByRole('button', { name: 'Обзор', exact: true }).click();
  await expect(page.getByText('Готовность к суду: 25%')).toBeVisible();
  await page.getByRole('button', { name: 'Переписка', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Переписка и события' })).toBeVisible();
  await page.getByRole('button', { name: 'Написать должнику' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
});

test('provider details and a separate consent are published', async ({ page }) => {
  await page.goto('/company');
  await expect(page.getByText('326265100166493').first()).toBeVisible();
  await page.goto('/consent');
  await expect(
    page.getByRole('heading', { level: 1, name: 'Согласие на обработку персональных данных' })
  ).toBeVisible();
  await page.goto('/app?mode=register');
  await expect(page.getByRole('checkbox')).toHaveCount(2);
  await expect(
    page.getByRole('link', { name: 'согласие на обработку персональных данных' })
  ).toHaveAttribute('href', '/consent');
});

test('the site and workspace switch to English', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Switch to English' }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('link', { name: 'Try for free' }).first()).toBeVisible();
  await signUpInEnglish(page);
});

async function signUpInEnglish(page: import('@playwright/test').Page) {
  await page.goto('/app?mode=register&lang=en');
  await page.getByLabel('Your name').fill('Anna');
  await page.getByLabel('Company', { exact: true }).fill('Supply LLC');
  await page.getByLabel('Work email').fill(`en-${Date.now()}@example.ru`);
  await page.getByLabel('Password', { exact: true }).fill(password);
  for (const box of await page.getByRole('checkbox').all()) await box.check();
  await page.locator('form').getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible();
}
